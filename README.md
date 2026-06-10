# hyprkeys

A hotkey atlas and inline label editor for [Hyprland](https://hyprland.org/), styled to match a ZSA Moonlander keyboard.

Press a key on your config, see a Moonlander-shaped grid light up with every keybind you have. Filter by modifier chip (`Super`, `Super+Shift`, `Super+Ctrl`, `Media`, `Mouse`), search by label or key, and rename binds in place — changes are batched and written atomically back to `hyprland.conf`, then `hyprctl reload` is fired.

Built in Python 3 + GTK3 + GtkLayerShell. Andromeda colorway, JetBrains Mono Nerd Font.

## Install

Arch / Hyprland — clone anywhere, symlink the entry point onto your PATH:

```bash
git clone https://github.com/raymondshiner/hyprkeys.git ~/src/hyprkeys
ln -s ~/src/hyprkeys/hyprkeys.py        ~/.local/bin/hyprkeys.py
ln -s ~/src/hyprkeys/hyprkeys_parser.py ~/.local/bin/hyprkeys_parser.py
ln -s ~/src/hyprkeys/hyprkeys_layout.py ~/.local/bin/hyprkeys_layout.py
```

Dependencies (Arch):
```bash
sudo pacman -S python gtk3 gtk-layer-shell python-gobject
```

Bind it in `~/.config/hypr/hyprland.conf`:
```
bind = SUPER, slash, exec, ~/.local/bin/hyprkeys.py
```

`hyprctl reload`. Hit `Super + /`.

## Use

- `Super + /` — toggle the atlas (running instance is killed)
- `Esc` — close (prompts if you have unsaved edits)
- `/` — focus the search box from anywhere in the popup
- `Ctrl+1..5` — switch chips
- Click any key → edit its label inline
- `Ctrl+S` — save all pending edits, reload Hyprland
- `Ctrl+Z` — undo last label change

Labels are stored as `# @label: <text>` inline comments on each `bind = ...` line. The parser also synthesizes labels from the dispatcher when no comment is present, so the atlas is useful immediately on a fresh config.

## Layout

The physical key grid is hardcoded to the ZSA Moonlander Mark I (both halves, 6-key thumb clusters). Reskin `hyprkeys_layout.py` for other keyboards.

## Status

Single-machine tool, hand-built. Works on Arch + CachyOS + Hyprland. PRs welcome but expect opinionated styling — see `SPEC.md` for the design rationale.
