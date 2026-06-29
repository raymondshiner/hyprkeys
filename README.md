# moonkeys

A hotkey atlas and editor for [Hyprland](https://hyprland.org/) **and** the ZSA Moonlander's QMK firmware, in one Moonlander-shaped GTK popup.

**Hyprland mode** — press a key on your config, see a Moonlander-shaped grid light up with every keybind you have. Filter by modifier chip (`Super`, `Super+Shift`, `Super+Ctrl`, `Media`, `Mouse`), search by label or key, and rename binds in place — changes are batched and written atomically back to `hyprland.conf`, then `hyprctl reload` is fired.

**QMK mode** — a local [Oryx](https://configure.zsa.io/): view and edit `keymap.c` keycodes and per-key RGB, then compile and flash, without leaving the popup.

Built in Python 3 + GTK3 + GtkLayerShell. Andromeda colorway, JetBrains Mono Nerd Font.

> Started life as `hyprkeys` (Hyprland only); grew the QMK backend and was renamed `moonkeys`.

## Install

Arch / Hyprland — clone anywhere, symlink the entry point onto your PATH:

```bash
git clone https://github.com/raymondshiner/moonkeys.git ~/src/moonkeys
ln -s ~/src/moonkeys/moonkeys.py ~/.local/bin/moonkeys.py
```

The supporting modules (`hyprkeys_parser.py`, `hyprkeys_layout.py`, `moonkeys_*.py`) are imported from the script's own directory — no extra symlinks needed.

Dependencies (Arch):
```bash
sudo pacman -S python gtk3 gtk-layer-shell python-gobject
```

Bind it in `~/.config/hypr/hyprland.conf`:
```
bind = SUPER, slash, exec, ~/.local/bin/moonkeys.py
```

`hyprctl reload`. Hit `Super + /`.

## Use

- `Super + /` — toggle the popup (running instance is killed)
- `Ctrl+M` — switch between Hyprland and QMK mode
- `Esc` — close (prompts if you have unsaved edits)
- `Ctrl+S` — save pending edits

Hyprland mode:
- `/` — focus the search box from anywhere in the popup
- `Ctrl+1..5` — switch modifier chips
- Click any key → edit its label inline · `Ctrl+Z` — undo last label change

Labels are stored as `# @label: <text>` inline comments on each `bind = ...` line. The parser also synthesizes labels from the dispatcher when no comment is present, so the atlas is useful immediately on a fresh config.

## QMK mode

The header has a `[ Hyprland ] [ QMK ]` toggle (`Ctrl+M`). QMK mode is a local Oryx for the Moonlander firmware — it reads `~/montressor/moonlander/keymap/keymap.c` and renders the live keymap on the same grid, one layer at a time (`Default` / `Other` / `Apps`, switch with the chips or `Ctrl+1/2/3`).

- Every key cap shows its keycode (or the human label from the comment-header table), with its current RGB as a swatch underneath.
- Click a key → a side drawer opens with the keycode field, an HSV color picker (three sliders + Andromeda palette swatches + live preview), and the key's Hyprland action.
- Per-key RGB is parsed from and written back to the `ledmap[layer][led][3]` HSV array; the LAYOUT→LED index map is derived from `keyboard.json`.
- `Ctrl+S` writes `keymap.c` atomically (only the changed keycode tokens and HSV triplets are spliced), commits the `~/montressor/moonlander` repo, then opens the **flash gate**: *Compile + Flash* / *Compile only* / *Not yet*. Build and flash run in a visible terminal — flashing waits for you to push the reset pinhole on the right half.

Modules: `moonkeys_qmk.py` (parser/serializer), `moonkeys_view.py` (the GTK editor), `moonkeys_flash.py` (compile + DFU flash gate).

## Layout

The physical key grid is hardcoded to the ZSA Moonlander Mark I (both halves, 6-key thumb clusters). Reskin `hyprkeys_layout.py` for other keyboards.

## Status

Single-machine tool, hand-built. Works on Arch + CachyOS + Hyprland. PRs welcome but expect opinionated styling — see `SPEC.md` for the design rationale.
