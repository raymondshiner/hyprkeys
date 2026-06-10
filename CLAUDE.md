# hyprkeys — Smith Notes

Hand-built GTK popup. Part of the **Montressor** system (the desktop's umbrella
name). Read `SPEC.md` end-to-end before writing any code.

## Stack constraints (non-negotiable)

- Python 3 + GTK3 + GtkLayerShell. Do NOT use GTK4 — the rest of the popup
  ecosystem on this machine is GTK3 and shares CSS conventions.
- Match the pattern of `~/.local/bin/battery-popup.py` and `sound-popup.py`
  exactly — same PID file convention, same CSS template structure, same
  Esc-to-close handler, same RGBA visual setup.
- No `focus-out-event` close handler. Esc only.

## Andromeda

All colors and the font come from `~/CLAUDE.md`. Do not invent new accents.
hyprkeys's signature accent is purple `#B084EB` — use it for the popup glow
and the "selected key" highlight.

## File writes

Editing `~/.config/hypr/hyprland.conf` is destructive. Always:
1. Read the full file
2. Write to `hyprland.conf.tmp` in the same dir
3. `fsync` the temp file
4. `os.rename` over the original (atomic on the same filesystem)

Never use `open(path, 'w')` directly on the real config. A crash mid-write would
brick the user's WM session.

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

- Project source: `~/src/hyprkeys/`
- Deployed script: `~/.local/bin/hyprkeys.py` (symlink to `montressor/local-bin/`)
- Config touched: `~/.config/hypr/hyprland.conf` (symlinked from `montressor/hypr/`)

Don't add comments unless the WHY is non-obvious. Don't add error handling for
scenarios that can't happen (e.g. the file always exists; the user always has
hyprctl on PATH).
