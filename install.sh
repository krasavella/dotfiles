#!/usr/bin/env bash
set -euo pipefail
if ! command -v python3 >/dev/null; then
    for argument in "$@"; do
        case "$argument" in
            --dry-run|--files-only|--restore|-h|--help)
                printf 'Установщику нужен Python 3. Установи пакет python и повтори команду.\n' >&2
                exit 1
                ;;
        esac
    done
    if (( EUID == 0 )); then
        printf 'Запускай скрипт от обычного пользователя.\n' >&2
        exit 1
    fi
    sudo pacman -Syu --needed python
fi
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
exec python3 -B "$repo_dir/install.py" "$@"
