# moonkeys upgrade plan

Owner: jarvis (built by smith; ownership moved to jarvis on completion — this is
desktop/firmware tooling, and firmware edits are Jarvis's job)
Status: DONE — shipped 2026-06-28. All phases (QMK view, swatches, keycode +
RGB drawer, layer switcher, flash gate) landed; project renamed hyprkeys →
moonkeys (repo, entry point, GitHub remote, Hyprland bind, symlinks).
Source: spec'd by jeeves 2026-06-12 in conversation with raymond

## What this is

`hyprkeys` ships today as a Hyprland-only atlas: parses `~/.config/hypr/hyprland.conf`, renders binds on a Moonlander-shaped GTK grid, inline-edits labels, atomic writeback, `hyprctl reload`.

The **moonkeys** upgrade keeps that exact UX and grows a second backend: editing the QMK firmware (`keymap.c` + RGB matrix) the same way it currently edits `hyprland.conf`. At the end of the upgrade the project is renamed `hyprkeys → moonkeys`. **Do not rename until the QMK backend is done and proven.**

This is a hyprkeys *evolution*, not a rewrite. Reuse `hyprkeys_layout.py` as-is — the grid is already correct. The parser, editor, and renderer get a second mode, not a second app.

## Hard constraints (do not violate)

- Python 3 + GTK3 + GtkLayerShell. No GTK4.
- Match the popup pattern in `~/.local/bin/battery-popup.py` / `sound-popup.py` exactly (PID file, RGBA visual, Esc-to-close, no `focus-out-event`).
- All file writes use the same atomic-rename pattern hyprkeys already uses on `hyprland.conf`. **Never `open('w')` directly** on `keymap.c` — a crash mid-write bricks the next build.
- Andromeda colors only — pulled from `hyprkeys_layout.py`. Signature glow is purple `#B084EB`.
- Flash is **gated** through the existing skill at `~/montressor-private/claude/skills/moonlander-add-hotkey.md` — exact same `AskUserQuestion` confirmation, exact same DFU-watcher bash block. Don't reinvent it; shell out or copy verbatim.

## Backend boundaries

```
hyprkeys_parser.py        # Hyprland — keep as-is
moonkeys_qmk.py           # NEW: keymap.c parser + serializer + RGB matrix
moonkeys_flash.py         # NEW: `make compile` + DFU watcher + flash gate
hyprkeys_layout.py        # shared grid — no changes
hyprkeys.py → moonkeys.py # renamed at the very end; gains a "mode toggle"
```

The QMK module owns three concerns:
1. **Read** `~/montressor/moonlander/keymap/keymap.c` → in-memory model `{ layer: 0|1|2, layout_idx: 0..71, keycode: str, hsv: (h,s,v) }[]`.
2. **Write** the same model back, preserving the file's comment headers, layer names (`_BASE`, `_OTHER`, `_APPS`), and any non-keymap functions verbatim. Diff-friendly — touch only the bytes that changed.
3. **Compile + flash** via `moonkeys_flash.py`, which calls `make compile` in `~/montressor/moonlander/` then runs the exact flash-gate block from the skill.

## UX additions (additive — Hyprland mode stays default on launch)

- **Mode toggle** in the popup header: `[ Hyprland ]  [ QMK ]` — two chip buttons, purple glow on the active one. `Ctrl+M` switches modes from anywhere.
- **Layer switcher** (QMK mode only): `[ Default ]  [ Other ]  [ Apps ]` — second row of chips. `Ctrl+1/2/3` switch layers. Hides in Hyprland mode.
- **Click a key (QMK mode)** → side drawer slides in with:
  - Keycode picker — text input with autocomplete from a curated list (modifiers, letters, layer toggles `MO()`, `LCTL(LGUI(KC_X))` chord builder for hyprland routing).
  - HSV color picker — three sliders + a swatch. Default suggestion based on the keycode's category (per the existing skill's color table).
  - "Apply to all transparent keys on this layer" checkbox for paint-the-board batches.
- **Save (Ctrl+S)** writes `keymap.c`, runs `make compile`, then prompts the flash gate. On "Not yet" the build stays staged at `~/montressor/moonlander/firmware/sirlexicon.bin`.
- **Color swatch on every key** in QMK mode — small filled rectangle in the corner of each rendered key showing its current RGB. This is the headline feature.

## Phases (ship each independently, in order)

1. **Read-only QMK view.** Add the mode toggle. In QMK mode, render the grid populated from `keymap.c` (keycodes only, no editing). Verify against the live board.
2. **Color swatches.** Parse `rgb_matrix_set_color` calls in `keyboard_post_init_user` (or wherever the per-layer RGB lives) and render the color per key.
3. **Edit drawer — keycode only.** Click → side panel → change keycode → Ctrl+S → atomic write → `make compile` → flash gate.
4. **Edit drawer — RGB.** HSV sliders write back to the matrix init block.
5. **Layer switcher.** Default / Other / Apps. Each layer's keycodes and colors render independently.
6. **Heuristic color defaults.** When a new keycode is set with no HSV, suggest from the skill's category table (apps = various per-app colors; modifiers = white; layer toggles = green; transparent = black).
7. **Rename the project.** `git mv`, sed the imports, update the README, update CLAUDE.md, update the GitHub remote (`gh repo rename`), update the symlinks in `~/.local/bin/`, update the Hyprland bind from `hyprkeys.py` to `moonkeys.py`. **Last step.**

## Source-of-truth notes (don't trip on these)

- `~/montressor/moonlander/` is a git repo, symlinked into QMK. After any keymap edit, commit + push via `git -C ~/montressor/moonlander ...` (not `dots` — `dots` doesn't manage this repo per `~/src/hyprkeys/CLAUDE.md`'s convention; verify when you get there).
- `keymap.c` layer order is `_BASE = 0`, `_OTHER = 1`, `_APPS = 2`. The LAYOUT macro is a single array — index 59 is the white inner-thumb on the right half (proven by the flash test on 2026-06-12).
- The RGB matrix uses LED indices, not LAYOUT indices. The mapping lives in `~/qmk_firmware/keyboards/zsa/moonlander/reva/keyboard.json` under `layouts.LAYOUT.layout[*].LED`. Cache it on parse.
- HSV in QMK: `H` 0–255 (not 360), `S` 0–255, `V` 0–255. White = `(0, 0, 255)`. Black/off = `(0, 0, 0)`.

## Out of scope (don't get pulled in)

- Combo / macro editing — keymap_c only, no `process_record_user` rewriting.
- Tap dance, layer-tap chords beyond `MO()` and `LCTL(LGUI(...))`.
- Live RGB preview on the board (would need `kontroll` + Keymapp running). Static color swatches in the popup only.
- Anything that talks to oryx.zsa.io.

## Done definition

- Both modes work end-to-end from `Super + /`.
- A QMK keycode + color edit ships to the board via the flash gate with zero CLI usage.
- The repo is renamed `moonkeys`, the GitHub remote is renamed, the binary on PATH is `moonkeys.py`, and `hyprctl reload` picks up the renamed bind.
- `~/src/hyprkeys/CLAUDE.md` is updated to `~/src/moonkeys/CLAUDE.md` with the new scope. The "don't use GTK4 / match popup pattern / atomic writes" rules stay verbatim.
- Smoke test passes: launch popup → QMK mode → Default layer → click white inner-thumb → confirm it's `KC_LEFT_GUI` and the swatch is white → close without changes.

## Reference paths

| Thing | Path |
|---|---|
| Current project root | `~/src/hyprkeys/` |
| Layout module (reuse) | `~/src/hyprkeys/hyprkeys_layout.py` |
| Hyprland parser (reuse) | `~/src/hyprkeys/hyprkeys_parser.py` |
| Project SPEC (v1) | `~/src/hyprkeys/SPEC.md` |
| Project CLAUDE.md | `~/src/hyprkeys/CLAUDE.md` |
| Keymap source | `~/montressor/moonlander/keymap/keymap.c` |
| Moonlander makefile | `~/montressor/moonlander/Makefile` |
| LED ↔ LAYOUT map | `~/qmk_firmware/keyboards/zsa/moonlander/reva/keyboard.json` |
| Flash gate (copy verbatim) | `~/montressor-private/claude/skills/moonlander-add-hotkey.md` §E |
| Existing GTK popup pattern | `~/.local/bin/battery-popup.py`, `~/.local/bin/sound-popup.py` |
