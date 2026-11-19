# Dux dotfiles

An Arch Linux setup with Niri and Dux Modular Shell. It includes Gruvbox, the Dux bar and island, a wallpaper, a contrast tweak, and Ghostty as the terminal.

## Installation

Run the installer as a regular user, preferably from a TTY.

~~~bash
./install.sh --dry-run
./install.sh
~~~

If any packages are missing, the installer runs `sudo pacman -Syu --needed`. If the dependencies are already installed, use `./install.sh --files-only`. After installation, select **Niri** on the login screen or run `niri-session` from a TTY.

| Shortcut | Action |
| --- | --- |
| `Super+T` | Ghostty |
| `Super+D` | Open the app launcher |
| `Super+F1` | Show keyboard shortcuts |
| `Super+Shift+T` | Open Dux appearance settings |
| `Super+Alt+L` | Lock the screen |
| `Super+Ctrl+C` | Open Control Center |
| `Super+Ctrl+V` | Open clipboard history |
| `Print` / `Ctrl+Print` / `Alt+Print` | Capture a region / screen / window |
| `Shift+Print` | Copy the original PNG as a file |

Add your monitor settings to `~/.config/niri/local.kdl`. When installing over an existing Dux setup, the installer preserves the wallpaper and other session data in `session.json`. Configuration updates also preserve widgets from installed local plugins.

The installer backs up affected files to `$XDG_STATE_HOME/dotfiles/backups/` before writing any changes. The default location is `~/.local/state/dotfiles/backups/`. The installer prints the exact backup path.


~~~bash
./install.sh --restore /path/to/backup --dry-run
./install.sh --restore /path/to/backup
~~~

# Screenshots
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/ec6d4b84-08db-4769-9da7-f54622e405f7" />
<img width="1920" height="1080" alt="1795103359675638330" src="https://github.com/user-attachments/assets/58e41aa5-a14a-4f8e-897f-7a0a9b8cae91" />
<img width="1920" height="1080" alt="1795103365563997733" src="https://github.com/user-attachments/assets/5f06998a-ce2e-4f72-b0db-e68faafbca4b" />


