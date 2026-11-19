#!/usr/bin/env python3
"""Apply version-checked contrast and light-glass fixes to Dux's current UI."""
import argparse
import os
from pathlib import Path
import signal
import stat
import sys

ORIGINAL = 'readonly property color accentTrack: Theme.withAlpha(accent, 0.28)'
REPLACEMENT = 'readonly property color accentTrack: accentRail // local: readable over blurred artwork'

PATCHES = {
    'Services/MediaAccentService.qml': [(ORIGINAL, REPLACEMENT)],
    'DCommon/Widgets/DSlider.qml': [
        ('property color trackColor: Style.secondaryContainer',
         'property color trackColor: Style.withAlpha(Qt.tint(Style.outline, Style.withAlpha(Style.surfaceText, 0.25)), 1) // local: visible remaining track'),
        ('readonly property real trackAlpha: Math.max(Style.sliderTrackMinAlpha, usePopupTransparency ? Style.foregroundAlpha : Style.floatingWindowForegroundAlpha)',
         'readonly property real trackAlpha: 1 // local: slider rail is independent of glass opacity'),
    ],
    'Common/Theme.qml': [
        ('return SettingsData.popupTransparency !== undefined ? SettingsData.popupTransparency : 1.0;',
         'const opacity = SettingsData.popupTransparency !== undefined ? SettingsData.popupTransparency : 1.0;\n        return isLightMode && opacity > 0 ? Math.max(0.88, opacity) : opacity; // local: light frosted glass'),
    ],
    'Common/SettingsData.qml': [
        ('return popupTransparency;\n        return config?.transparency ?? 1.0;',
         'return Theme.popupTransparency; // local: use theme-aware glass\n        return config?.transparency ?? 1.0;'),
        ('    function barWidgetTransparency(config) {\n        if (config?.widgetFollowInterfaceStyle !== false)\n            return Theme.foregroundAlpha;\n        return config?.widgetTransparency ?? 1.0;\n    }',
         '    function barWidgetTransparency(config) {\n        const opacity = config?.widgetFollowInterfaceStyle !== false ? Theme.foregroundAlpha : (config?.widgetTransparency ?? 1.0);\n        return Theme.isLightMode && opacity > 0 ? Math.max(0.88, opacity) : opacity; // local: light frosted pills\n    }'),
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reload-pid', type=int)
    args = parser.parse_args()
    runtime = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'dms-shell'
    patched = 0
    for bundle in runtime.glob('*'):
        if not bundle.is_dir() or bundle.is_symlink() or bundle.stat().st_uid != os.getuid():
            continue
        updates = []
        for relative, pairs in PATCHES.items():
            path = bundle / relative
            if not path.is_file() or path.is_symlink() or path.stat().st_uid != os.getuid():
                break
            source = path.read_text()
            result = source
            for old, new in pairs:
                if result.count(new) == 1:
                    continue
                if result.count(old) != 1:
                    print(f'Contrast: unrecognized source, bundle left unchanged: {path}', file=sys.stderr)
                    break
                result = result.replace(old, new, 1)
            else:
                updates.append((path, source, result))
                continue
            break
        else:
            for path, source, result in updates:
                if source == result:
                    continue
                mode = stat.S_IMODE(path.stat().st_mode)
                try:
                    path.chmod(mode | stat.S_IWUSR)
                    path.write_text(result)
                finally:
                    path.chmod(mode)
                patched += 1
                print(f'Applied contrast/glass fix: {path}')
    print(f'Contrast/glass: {patched} file(s) updated')
    if patched and args.reload_pid:
        # Same signal as the packaged dms.service ExecReload. Embedded UI disables
        # file watching, so newly extracted bundles must be reloaded explicitly.
        os.kill(args.reload_pid, signal.SIGUSR1)
        print('Requested Dux UI reload after applying media contrast')


if __name__ == '__main__':
    main()
