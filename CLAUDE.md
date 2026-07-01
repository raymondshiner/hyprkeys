# moonkeys — Jarvis Notes

**Jarvis' domain.** This is desktop + Moonlander-firmware tooling, not app code —
route work here to Jarvis, not Smith. (It was built by Smith and renamed from
`hyprkeys`; ownership moved to Jarvis once the QMK/firmware backend landed, since
firmware edits are always Jarvis's job per the `moonlander-hotkey` skill.)

Hand-built GTK popup — a one-stop keyboard + hotkey customizer with two sections:

- **Keyboard** — a local-Oryx editor for the Moonlander `keymap.c`. Per-key
  **Tap / Double-tap / Hold** behaviour + per-key RGB. moonkeys picks the QMK
  construct (`LT`/`MO`/`*_T`/tap-dance) and regenerates the `enum tap_dance_codes`
  + `tap_dance_actions[]` blocks into a managed `/* moonkeys:td */` region;
  tap+double+hold keys get generated `*_finished`/`*_reset` functions. Always
  `make compile` after a write (via the flash gate) to prove the generated C
  builds before flashing.
- **Hotkeys** — a searchable, modifier-sorted registry of every `hyprland.conf`
  bind; inline label editing (writeback + `hyprctl reload`), command read-only.

The two are cross-referenced: a QMK tap chord like `LGUI(KC_S)` decodes to
`Super+S` (via `chord_to_hypr`) and is matched against the Hyprland binds, so the
Keyboard drawer shows the bind a key drives and the Hotkeys list shows the
physical key that sends each bind.

Part of the **Montressor** system (the desktop's umbrella name). Read `SPEC.md`
and `MOONKEYS-UPGRADE.md` for history before writing any code.

## Stack constraints (non-negotiable)

- Python 3 + GTK3 + GtkLayerShell. Do NOT use GTK4 — the rest of the popup
  ecosystem on this machine is GTK3 and shares CSS conventions.
- Match the pattern of `~/.local/bin/battery-popup.py` and `sound-popup.py`
  exactly — same PID file convention, same CSS template structure, same
  Esc-to-close handler, same RGBA visual setup.
- No `focus-out-event` close handler. Esc only.

## Andromeda

All colors and the font come from `~/CLAUDE.md`. Do not invent new accents.
moonkeys's signature accent is purple `#B084EB` — use it for the popup glow
and the "selected key" highlight.

## File writes

Editing `~/.config/hypr/hyprland.conf` is destructive, and the path is a
**symlink into `~/montressor/hypr/`**. Always `os.path.realpath()` it first so the
temp file and the atomic rename land on the real montressor file — renaming over the
symlink path itself replaces the link with a standalone file, detaching
`~/.config/hypr` from `~/montressor` and breaking `dots` sync. Then:
1. Resolve: `CONFIG_PATH = os.path.realpath('~/.config/hypr/hyprland.conf')`
2. Read the full resolved file
3. Write to `CONFIG_PATH + '.tmp'` (same montressor dir → rename stays on one fs)
4. `fsync` the temp file
5. `os.rename` over the resolved original (atomic on the same filesystem)

Never use `open(path, 'w')` directly on the real config, and never rename over the
symlink path. A crash mid-write would brick the user's WM session. Same
atomic-rename discipline applies to `keymap.c` (already a real path in
`~/montressor/moonlander/`, no symlink to resolve).

## Reload + dots

After a successful save:
1. `subprocess.run(['hyprctl', 'reload'], check=False)` — non-fatal if it
   complains; the file is already written
2. `subprocess.Popen(['dots', f'relabel {n} hotkey(s)'])` — fire and forget;
   `dots` handles repo detection and pushes the `~/montressor` repo since
   `hyprland.conf` is symlinked from there

## Moonlander layout reference

ZSA's official layout SVG: https://configure.zsa.io/moonlander/layouts
The user has a Moonlander Mark I. Hardcode the physical key grid. Don't try to
query firmware at runtime.

Both halves split, including the 6-key thumb clusters on each side and the
red/yellow thumb keys. Approximately 72 keys total.

## Heuristic labels

When seeding labels on first launch (the "Optional" deliverable in the spec),
the rule is: **only write a `# @label:` comment if the heuristic produces a
non-trivial label.** Don't pollute the config with auto-labels like
"Workspace 3" — those are obvious from the bind itself. Save the labels for
binds where the dispatcher hides the meaning (e.g. `exec, /opt/google/chrome/...
--app-id=dfmohblocfmbgckfbldmimjbjomogdom` desperately needs a label).

## Testing

No automated tests. Smoke test:
1. Launch via `Super + /`
2. Search "jeeves" → only the J key stays bright
3. Click Super+Shift chip → J dims (no Super+Shift+J), M brightens
4. Edit Super+M label to "Spotify", edit Super+Shift+M label to "MPV", save
5. Reopen — labels persist
6. `git -C ~/montressor log -1` shows the auto-commit

## What lives where

- Project source + git remote: `~/src/moonkeys/` → `github.com/raymondshiner/moonkeys`
- Deployed script: `~/.local/bin/moonkeys.py` (symlink to `~/src/moonkeys/moonkeys.py`)
- Supporting modules (`hyprkeys_{parser,layout}.py`,
  `moonkeys_{qmk,view,hotkeys,flash}.py`) are imported from the script's own
  resolved directory (`~/src/moonkeys/`) — no separate bin symlinks needed.
- Hyprland bind: `~/.config/hypr/hyprland.conf` → `Super + /` → `moonkeys.py`
  (symlinked from `~/montressor/hypr/`)
- QMK firmware it edits: `~/montressor/moonlander/keymap/keymap.c` (+ `make
  compile` / `make flash` in `~/montressor/moonlander/`)

Source lives in `~/src/moonkeys/`, NOT `~/montressor/`. After edits there,
commit + push directly with `git -C ~/src/moonkeys ...` — `dots` does not
manage this repo. Note the two *other* repos this tool writes to on save:
`~/montressor` (hyprland.conf, via `dots`) and `~/montressor/moonlander`
(keymap.c, via `git -C ~/montressor/moonlander`).

Don't add comments unless the WHY is non-obvious. Don't add error handling for
scenarios that can't happen (e.g. the file always exists; the user always has
hyprctl on PATH).
