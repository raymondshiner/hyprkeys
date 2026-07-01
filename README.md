# moonkeys

One-stop **keyboard + hotkey customizer** for [Hyprland](https://hyprland.org/) and the ZSA Moonlander, in one Moonlander-shaped GTK popup. Map physical keys to behaviours on the keyboard, and see/relabel the system hotkeys those keys drive — cross-referenced so each side shows what the other does.

**Keyboard** — a local [Oryx](https://configure.zsa.io/) for the Moonlander `keymap.c`. Click any key and edit its **Tap / Double-tap / Hold** behaviour and per-key RGB; moonkeys generates the right QMK construct (`LT`/`MT`/`MO`/tap-dance, regenerating the `tap_dance_actions[]` array — advanced tap+double+hold keys get generated finished/reset functions), writes `keymap.c` atomically, then compiles and flashes — without leaving the popup.

**Hotkeys** — a searchable, modifier-sorted registry of every `hyprland.conf` bind. Search by label/key/command, sort by modifier, and rename binds in place (written atomically back to `hyprland.conf`, then `hyprctl reload`). Each row shows which physical Moonlander key sends the chord.

**Cross-reference** — a QMK tap chord like `LGUI(KC_S)` decodes to `Super+S` and is matched against the Hyprland binds: the Keyboard drawer shows `↳ Super+S → Smith`, and the Hotkeys list shows `⌨ S` next to that bind.

Built in Python 3 + GTK3 + GtkLayerShell. Andromeda colorway, JetBrains Mono Nerd Font.

> Started life as `hyprkeys` (a Hyprland-only atlas); grew the QMK backend, was renamed `moonkeys`, then reworked into the unified keyboard+hotkey tool described here.

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
- `Ctrl+M` — switch between **Keyboard** and **Hotkeys** sections
- `Esc` — close (prompts if you have unsaved edits)
- `Ctrl+S` — save pending edits in the active section

Keyboard section:
- `Ctrl+1/2/3` — switch layer (`Default` / `Other` / `Apps`)
- Click any key → side drawer with **Tap / Double-tap / Hold** slots + HSV colour picker

Hotkeys section:
- `/` — focus the search box from anywhere in the popup
- Sort dropdown: by modifier (grouped), key, or label · click a label to rename inline

## Keyboard section

A local Oryx for the Moonlander firmware — reads `~/montressor/moonlander/keymap/keymap.c` and renders the live keymap on the Moonlander grid, one layer at a time.

- Each key cap shows its label, a small badge for double-tap/hold behaviour, and its current RGB as a swatch underneath.
- Click a key → drawer with a **Label** field, three behaviour slots, and an HSV colour picker (sliders + Andromeda palette + live preview).
- **Assign a hotkey to a key:** the **Tap** and **Double-tap** fields are searchable and populate from your labelled Hyprland hotkeys — type "Netflix" and the field resolves to the chord `LGUI(LSFT(KC_N))` that triggers it. Raw keycodes (`KC_A`, `KC_F5`, …) work too, for plain typing keys. **Hold** is none / a layer / a modifier.
- **Unified labels:** a key's label is one concept. If the key drives a labelled hotkey, editing its label renames that hotkey in `hyprland.conf` (and shows in the Hotkeys section too); otherwise the label is stored in a managed region in `keymap.c`. Workflow: label a hotkey once ("make a hotkey for this app"), then assign it to a key.
- moonkeys picks the right QMK construct on save: plain keycode, `LT(layer, kc)` / `MO(layer)` for a hold-layer, `LGUI_T(kc)` etc. for a hold-mod, `ACTION_TAP_DANCE_DOUBLE` for tap+double, and a generated `*_finished`/`*_reset` tap-dance function for the tap+double+hold combo. The `enum tap_dance_codes` + `tap_dance_actions[]` blocks are regenerated into a managed `/* moonkeys:td */` region.
- Per-key RGB is parsed from and written back to the `ledmap[layer][led][3]` HSV array; the LAYOUT→LED index map is derived from `keyboard.json`.
- `Ctrl+S` writes `keymap.c` atomically, commits the `~/montressor/moonlander` repo, then opens the **flash gate**: *Compile + Flash* / *Compile only* / *Not yet*. Build and flash run in a visible terminal — flashing waits for you to push the reset pinhole on the right half.

## Hotkeys section

A flat registry of every `hyprland.conf` bind. Labels are stored as `# @label: <text>` inline comments; the parser synthesizes a label from the dispatcher when no comment is present, so the list is useful immediately on a fresh config. Search matches label/key/modifier/command; sort groups by modifier or orders by key/label. Renames batch and write atomically, then `hyprctl reload`.

Modules: `moonkeys_qmk.py` (keymap.c parser/serializer + slot model + chord mapping), `moonkeys_view.py` (Keyboard editor), `moonkeys_hotkeys.py` (Hotkeys list), `moonkeys_flash.py` (compile + DFU flash gate). Hyprland parsing/writeback lives in `hyprkeys_parser.py`; the shared grid geometry in `hyprkeys_layout.py`.

## Layout

The physical key grid is hardcoded to the ZSA Moonlander Mark I (both halves, 6-key thumb clusters). Reskin `hyprkeys_layout.py` for other keyboards.

## Status

Single-machine tool, hand-built. Works on Arch + CachyOS + Hyprland. PRs welcome but expect opinionated styling — see `SPEC.md` for the design rationale.
