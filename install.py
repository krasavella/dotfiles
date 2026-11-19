#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent
HOME = Path.home()
ROOTS = {
    "home": HOME,
    "bin": HOME / ".local/bin",
    "config": Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config"),
    "data": Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share"),
    "state": Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state"),
}
BACKUPS = ROOTS["state"] / "dotfiles/backups"
SESSION = "state/dms/session.json"
NIRI = "config/niri/config.kdl"
PLACEHOLDER = re.compile(rb'"@@(?:JSON|KDL):([^@]+)@@"|@@UNIT:([^@]+)@@')


@dataclass(frozen=True)
class File:
    data: bytes
    mode: int = 0o644
    symlink: bool = False


def destination(key):
    root, relative = key.split("/", 1)
    parts = relative.split("/")
    if not all(parts) or any(part in (".", "..") for part in parts) or root not in ROOTS:
        raise ValueError(f"Недопустимый путь {key}")
    return ROOTS[root].joinpath(*parts)


def read_file(path):
    if path.is_symlink():
        return File(os.fsencode(os.readlink(path)), symlink=True)
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(mode):
        raise ValueError(f"Ожидался обычный файл по пути {path}")
    return File(path.read_bytes(), stat.S_IMODE(mode))


def check_parent(path):
    for parent in path.parents:
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            raise ValueError(f"В пути {path} родитель {parent} является ссылкой или файлом")


def write_file(path, file):
    check_parent(path)
    if file is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dotfiles-", dir=path.parent) as directory:
        temp = Path(directory) / "file"
        if file.symlink:
            temp.symlink_to(os.fsdecode(file.data))
        else:
            temp.write_bytes(file.data)
            temp.chmod(file.mode)
        temp.replace(path)


def render(data):
    def replace(match):
        quoted_key, unit_key = match.groups()
        path = str(destination((quoted_key or unit_key).decode()))
        if quoted_key:
            return json.dumps(path, ensure_ascii=False).encode()
        return path.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$").encode()

    return PLACEHOLDER.sub(replace, data)


def build_plan():
    plan = {}
    profile = REPO / "desktop"
    for path in sorted(profile.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"В комплекте обнаружена ссылка {path}")
        if path.is_file():
            key = path.relative_to(profile).as_posix()
            destination(key)
            plan[key] = File(render(path.read_bytes()), stat.S_IMODE(path.stat().st_mode))
    for key in (SESSION, "config/niri/local.kdl", "config/dms/.firstlaunch"):
        if os.path.lexists(destination(key)):
            del plan[key]
    preserve_plugin_widgets(plan)
    return plan


def json_text(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode()


def preserve_plugin_widgets(plan):
    settings_key = "config/dms/settings.json"
    plugins_path = destination("config/dms/plugins")
    settings_path = destination(settings_key)
    if not settings_path.is_file() or not plugins_path.is_dir():
        return
    current = json.loads(settings_path.read_bytes())
    settings = json.loads(plan[settings_key].data)
    plugin_ids = {path.parent.name for path in plugins_path.glob("*/plugin.json")}
    previous_bars = {bar["id"]: bar for bar in current.get("barConfigs", []) if "id" in bar}
    for bar in settings["barConfigs"]:
        previous = previous_bars.get(bar["id"], {})
        for group in ("leftWidgets", "centerWidgets", "rightWidgets"):
            for position, widget in enumerate(previous.get(group, [])):
                widget_id = widget.get("id") if isinstance(widget, dict) else widget
                if widget_id in plugin_ids:
                    bar[group].insert(position, widget)
    tiles = settings["controlCenterWidgets"]
    for tile in current.get("controlCenterWidgets", []):
        if tile.get("id", "").removeprefix("plugin_") in plugin_ids:
            tiles.append(tile)
    plan[settings_key] = File(json_text(settings))


def package_names():
    return [
        name for line in (REPO / "packages.txt").read_text().splitlines()
        for name in line.partition("#")[0].split()
    ]


def install_packages(args, packages):
    if args.files_only:
        return
    if not shutil.which("pacman") or not shutil.which("sudo"):
        raise ValueError("Для установки пакетов нужны pacman и sudo. Копирование доступно через --files-only.")
    missing = subprocess.run(
        ["pacman", "-T", *packages], capture_output=True, text=True,
    )
    if missing.returncode == 0:
        return
    # A full upgrade avoids partial Arch upgrades against newly synced repositories.
    subprocess.run(["sudo", "pacman", "-Syu", "--needed", *packages], check=True)


def validate(plan):
    commands = (
        ("niri", ["validate", "--config"], NIRI),
        ("ghostty", ["+validate-config"], "config/ghostty/config"),
    )
    with tempfile.TemporaryDirectory(prefix="dotfiles-check-") as directory:
        stage = Path(directory)
        for key, file in plan.items():
            if key.startswith(("config/niri/", "config/ghostty/")):
                path = stage / key
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(file.data)
        for executable, options, key in commands:
            if key in plan and shutil.which(executable):
                path = str(stage / key)
                if executable == "ghostty":
                    subprocess.run([executable, *options, f"--config-file={path}"], check=True)
                else:
                    subprocess.run([executable, *options, path], check=True)


def snapshot(previous):
    check_parent(BACKUPS / "manifest.json")
    BACKUPS.mkdir(parents=True, mode=0o700, exist_ok=True)
    prefix = datetime.now().strftime("%Y%m%d-%H%M%S-")
    archive = Path(tempfile.mkdtemp(prefix=prefix, dir=BACKUPS))
    records = []
    for number, (key, file) in enumerate(previous.items()):
        if file is None:
            records.append({"key": key})
        else:
            blob = str(number)
            (archive / blob).write_bytes(file.data)
            records.append({"key": key, "blob": blob, "mode": file.mode, "symlink": file.symlink})
    (archive / "manifest.json").write_bytes(json_text({
        "version": 1, "roots": {key: str(path) for key, path in ROOTS.items()}, "files": records,
    }))
    return archive


def read_snapshot(archive):
    manifest = json.loads((archive / "manifest.json").read_bytes())
    if manifest["version"] != 1 or manifest["roots"] != {key: str(path) for key, path in ROOTS.items()}:
        raise ValueError("Резервная копия создана для другого HOME или набора путей XDG")
    files = {}
    for record in manifest["files"]:
        key = record["key"]
        destination(key)
        blob = record.get("blob")
        if blob is not None and not blob.isdecimal():
            raise ValueError("Неверное имя файла в резервной копии")
        files[key] = None if blob is None else File(
            (archive / blob).read_bytes(), record["mode"], record["symlink"],
        )
    return files


def apply(plan, dry_run, restoring=False):
    updates = {}
    before = {}
    for key, desired in plan.items():
        path = destination(key)
        check_parent(path)
        current = read_file(path)
        if current == desired:
            continue
        if not restoring and current and desired and not current.symlink and (
            current.data == desired.data and current.mode & 0o111 == desired.mode & 0o111
        ):
            continue
        updates[key] = desired
        before[key] = current
        action = "удалить" if desired is None else "заменить" if current else "создать"
        print(f"{action}  {path}")
    if not updates:
        print("Все файлы уже на месте.")
    if dry_run or not updates:
        return

    archive = snapshot(before)
    print(f"Резервная копия → {archive}", flush=True)
    written = []
    try:
        for key, desired in updates.items():
            write_file(destination(key), desired)
            written.append(key)
        if not restoring and NIRI in plan and shutil.which("niri"):
            subprocess.run(["niri", "validate", "--config", str(destination(NIRI))], check=True)
    except (Exception, KeyboardInterrupt):
        for key in reversed(written):
            try:
                write_file(destination(key), before[key])
            except (OSError, ValueError) as error:
                print(f"Откат {key}: {error}. Копия сохранена в {archive}", file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description="Установить конфиги Niri, Dux и Gruvbox")
    parser.add_argument("--dry-run", action="store_true", help="показать файлы и пакеты без записи")
    parser.add_argument("--files-only", action="store_true", help="пропустить pacman")
    parser.add_argument("--restore", type=Path, metavar="BACKUP", help="восстановить файлы из указанной копии")
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("Запускай скрипт от пользователя. Для pacman он сам вызовет sudo.")
    if any(not path.is_absolute() for path in ROOTS.values()):
        parser.error("Пути HOME и XDG должны быть абсолютными.")
    if args.restore and args.files_only:
        parser.error("Для --restore доступна опция --dry-run.")
    if args.dry_run:
        if args.restore:
            apply(read_snapshot(args.restore), dry_run=True, restoring=True)
        else:
            if not args.files_only:
                print("Пакеты → " + " ".join(package_names()))
            plan = build_plan()
            apply(plan, dry_run=True)
        return

    lock_dir = ROOTS["state"] / "dms"
    check_parent(lock_dir / "install.lock")
    lock_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(lock_dir / "install.lock", os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if args.restore:
            apply(read_snapshot(args.restore), dry_run=False, restoring=True)
            return
        plan = build_plan()
        # Detect destination conflicts before installing packages or building dependencies.
        for key in plan:
            path = destination(key)
            check_parent(path)
            read_file(path)
        install_packages(args, package_names())
        validate(plan)
        apply(plan, dry_run=False)
        print("Готово. Войди в сеанс Niri заново или запусти niri-session из TTY.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        sys.exit(f"Установка прервана. {error}")
    except KeyboardInterrupt:
        sys.exit(130)
