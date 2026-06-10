# hyprkeys — Hotkey Cheatsheet & Editor

A hand-built, keyboard-shaped hotkey reference and label editor for Hyprland on
sirlexicon-laptop. Triggered globally, parses the live config, lets the user
search, relabel, and write changes back to disk in batches.

Part of the **Montressor** system (the umbrella name for this whole desktop).
`hyprkeys` is the specific tool that catalogues and edits keybind labels.

---

## Why

`grep ^bind ~/.config/hypr/hyprland.conf` works, but:
- No visual map of which physical key triggers what
- No way to distinguish modifier variants at a glance (Super+M vs Super+Shift+M)
- Labels live in comments or memory, not in a searchable index
- Renaming a bind's *meaning* requires hunting through 300+ lines of config

`hyprkeys` solves all four in one Andromeda-styled GTK popup.

---

## Stack

- **Language:** Python 3 + GTK3 + GtkLayerShell (matches existing popup pattern in `~/.local/bin/`)
- **Trigger:** Hyprland bind → `Super + /` → `exec, /home/sirlexicon/.local/bin/hyprkeys.py`
- **Install path:** `~/.local/bin/hyprkeys.py` (symlinked from `~/montressor/local-bin/hyprkeys.py`)
- **Reference popups:** `~/.local/bin/battery-popup.py`, `~/.local/bin/sound-popup.py` — match their pattern exactly

Single-file Python preferred. If it grows past ~600 lines, split into:
```
~/src/hyprkeys/
  hyprkeys.py          # entry point + GTK app
  parser.py            # hyprland.conf parse/serialize
  keyboard_layout.py   # Moonlander key grid + position lookup
  edit_buffer.py       # pending label edits, commit/discard
```

---

## Data Model

### Source of truth
- `~/.config/hypr/hyprland.conf` — for `bind`, `bindm`, `bindl`, `bindel`, `binde` lines
- Future: ZSA Moonlander layer config (out of scope v1)

### Bind label storage
Hyprland has no native label field. Labels are stored as inline trailing comments
with a sentinel:

```
bind = $mainMod, Q, exec, $terminal  # @label: Terminal
bind = $mainMod, J, exec, kitty ... -e jeeves  # @label: Jeeves
```

Parser rule:
- If `# @label: <text>` is present, use it.
- Else fall back to a heuristic label derived from the dispatcher + params
  (e.g. `exec $terminal` → "Terminal"; `workspace, 3` → "Workspace 3").

This keeps the config file the single source of truth and survives `dots` syncs.

### Modifier filter
Top-of-window chip row: `[ All ] [ Super ] [ Super+Shift ] [ Super+Ctrl ] [ Media ] [ Mouse ]`
- Clicking a chip filters the keyboard view to highlight ONLY binds matching that
  modifier set (exact match, not subset).
- "All" shows every bound key. Modifier badges in corner of each key.
- Multi-modifier binds (e.g. `Super+Shift+M`) appear under their exact chip, not
  under `Super`.

---

## Layout

### Window

- GTK popup, `Gtk.Window` with `GtkLayerShell.Layer.OVERLAY`
- Centered on screen (anchor top + left + right + bottom, equal margins)
- Approx 1100×600
- Background `#1C1E26`, 12px rounded, glow `#B084EB` (purple — hyprkeys's accent)
- Esc closes; click outside does NOT close (consistent with battery-popup pattern)

### Structure (top to bottom)

```
┌────────────────────────────────────────────────────────────────┐
│  hyprkeys                                [Save 3 changes] [✕]  │
├────────────────────────────────────────────────────────────────┤
│  🔍 Search by label or key…                                    │
│  [All] [Super] [Super+Shift] [Super+Ctrl] [Media] [Mouse]      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│              [ KEYBOARD GRID — Moonlander ]                    │
│                                                                │
├────────────────────────────────────────────────────────────────┤
│  Selected: Super+M → Music launcher                            │
│  Label: [ Music launcher                              ] [Reset]│
│  Command: kitty ... ~/.local/bin/music-launch.sh   (read-only) │
└────────────────────────────────────────────────────────────────┘
```

### Keyboard grid — ZSA Moonlander split layout

Render the Moonlander's actual key positions, both halves, including thumb
clusters. Each key is a `Gtk.Button`-styled box:

- **Empty / no bind:** background `#23262E`, muted text `#677691`
- **Has bind matching filter:** background `#1C1E26`, cyan border, label below key
- **Has bind, filter excludes it:** dimmed (alpha 0.3), no label
- **Currently selected:** purple border + soft glow

Key cell contents:
```
┌──────┐
│  M   │   ← physical key cap
│ Music│   ← truncated label (12 char max)
│  ●   │   ← modifier dot: cyan=Super, yellow=Shift combo, etc.
└──────┘
```

Keys with multiple binds (Super+M and Super+Shift+M both on M) get **two dots**,
each colored by modifier set. Clicking the key opens a small disambiguation
popover listing all binds on that physical key.

Moonlander grid coordinates: use ZSA's official layout SVG as reference. Hardcode
a `KEYS: list[tuple[label, row, col, half]]` table. ~72 keys total.

---

## Features

### 1. Search by label
- Top search field, focused on open
- Fuzzy match against label text (case-insensitive substring is fine for v1)
- Matching keys stay full-opacity; non-matches dim to 0.3
- `Enter` selects first match
- `↑/↓` cycles through matches; selected key gets purple border

### 2. Filter by modifier
- Chip row beneath search
- Chips are mutually exclusive (radio-style)
- "All" is default
- Chip click re-renders the keyboard with filter applied
- Hotkeys: `Ctrl+1` through `Ctrl+6` jump to each chip

### 3. Relabel a single bind
- Click a key → it becomes "selected", details panel populates
- Label entry field is editable
- Editing the field stages the change in an in-memory edit buffer (does NOT touch
  disk yet)
- The key's label text in the grid updates live to preview
- A subtle yellow dot appears on the key to indicate "unsaved"

### 4. Batch editing
- Edit buffer accumulates multiple label changes per session
- Header button shows `[Save N changes]` with live count
- Switching between keys preserves staged edits
- `[Reset]` button per-field reverts that single bind to its on-disk label
- `[✕]` close button: if unsaved edits exist, GTK confirm dialog
  ("Discard 3 unsaved changes?" / "Save and close" / "Cancel")

### 5. Save → write to disk
- `[Save N changes]` triggers atomic config rewrite:
  1. Read `~/.config/hypr/hyprland.conf`
  2. For each staged edit, locate the matching `bind` line by `(modifier_set, key)`
     tuple — NOT by line number (config may have shifted)
  3. Replace or append the `# @label: <text>` trailing comment
  4. Preserve all other whitespace, comments, ordering exactly
  5. Write to `hyprland.conf.tmp`, `fsync`, `rename` over original
  6. Call `hyprctl reload`
  7. Show toast: "Saved 3 labels. Reloaded Hyprland."
- Then `subprocess.Popen(['dots', f'relabel {N} hotkey(s)'])` fires the commit
  in the background (no blocking)

### 6. Modifier disambiguation
- If a physical key has >1 bind (e.g. M has Super+M and Super+Shift+M), the key
  cell shows two colored dots
- Clicking opens a small inline popover listing each bind with its modifier set
  and current label
- Selecting one in the popover populates the details panel

---

## Bind line parsing

Regex (loose, capture-rich):
```python
BIND_RE = re.compile(
    r'^(bind[melE]*)\s*=\s*'
    r'([^,]*),\s*'           # mods (may be empty for media keys)
    r'([^,]+),\s*'           # key
    r'([^,]+)'               # dispatcher
    r'(?:,\s*(.+?))?'        # optional params
    r'(?:\s*#\s*@label:\s*(.+?))?'   # optional label comment
    r'\s*$'
)
```

Normalize modifier sets to a sorted tuple:
- `$mainMod` → `Super`
- `$mainMod SHIFT` → `('Super', 'Shift')`
- `,XF86AudioRaiseVolume` → `()` (no mod)

Key normalization:
- Uppercase letters
- `grave` → backtick visual
- `Print`, `XF86*` → media keys (live in a sidebar, not the keyboard grid)

### Heuristic fallback labels

| Pattern | Label |
|---|---|
| `exec, $terminal` | Terminal |
| `exec, $fileManager` | Files |
| `exec, $menu` | Launcher |
| `exec, /path/to/foo` | Foo (basename, title-cased) |
| `exec, kitty --title "X" ...` | X |
| `workspace, N` | Workspace N |
| `movetoworkspace, N` | Send → WS N |
| `movefocus, l/r/u/d` | Focus ← → ↑ ↓ |
| `togglefloating` | Toggle Float |
| `killactive` | Kill Window |
| `togglespecialworkspace, magic` | Scratchpad |
| `layoutmsg, togglesplit` | Toggle Split |
| `exec, swayosd-client --output-volume raise` | Volume + |
| (everything else) | dispatcher + first param |

---

## Andromeda styling

```css
window { background: transparent; }
.popup-inner {
    background: #1C1E26;
    border-radius: 12px;
    margin: 8px;
    padding: 20px;
    box-shadow: 0 0 0 1px #B084EB40, 0 0 24px #B084EB30;
}
.search-entry {
    background: #23262E;
    color: #D5CED9;
    border-radius: 8px;
    padding: 8px 12px;
    border: 1px solid #677691;
}
.chip {
    background: #23262E;
    color: #677691;
    border-radius: 999px;
    padding: 4px 12px;
    margin: 0 4px;
}
.chip.active {
    background: #B084EB;
    color: #1C1E26;
}
.key {
    background: #23262E;
    color: #677691;
    border-radius: 6px;
    min-width: 56px;
    min-height: 56px;
    padding: 4px;
}
.key.bound {
    background: #1C1E26;
    color: #D5CED9;
    border: 1px solid #00E8C6;
}
.key.bound.dimmed { opacity: 0.3; }
.key.selected { border: 2px solid #B084EB; box-shadow: 0 0 12px #B084EB60; }
.key.unsaved::after { content: ""; /* yellow dot rendered manually */ }
.key-label { font-size: 9px; color: #677691; }
.key.bound .key-label { color: #D5CED9; }
.save-button {
    background: #00E8C6;
    color: #1C1E26;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
}
.save-button.disabled { background: #23262E; color: #677691; }
```

Font: JetBrains Mono Nerd Font everywhere.

---

## Keybindings inside hyprkeys

| Key | Action |
|---|---|
| `/` | Focus search |
| `Esc` | Close (with confirm if unsaved) |
| `Enter` | Select first matching key / commit current label edit |
| `Ctrl+S` | Save all pending edits |
| `Ctrl+Z` | Undo last label edit (within session) |
| `Ctrl+1..6` | Jump to modifier chip |
| `Tab` | Cycle through visible keys |

---

## Out of scope (v1)

- Editing the command/dispatcher of a bind (label only)
- Adding new binds (label-only editor for now)
- Deleting binds
- Moonlander firmware editing (separate project; possibly v2)
- macOS / AeroSpace support
- Importing labels from a JSON file

---

## Deliverables

1. `~/src/hyprkeys/hyprkeys.py` (or split files per stack rules above)
2. Symlinked into `~/.local/bin/hyprkeys.py`, executable
3. Hyprland bind added to `~/.config/hypr/hyprland.conf`:
   ```
   bind = $mainMod, slash, exec, /home/sirlexicon/.local/bin/hyprkeys.py  # @label: hyprkeys
   ```
4. Optional: pre-seed `# @label:` comments on the existing ~50 binds based on the
   heuristic table, so first-launch already shows meaningful labels.
5. README in `~/src/hyprkeys/` covering: launch key, search, filter, edit flow,
   save flow, where labels are stored.

---

## Acceptance

- Pressing `Super + /` opens hyprkeys centered, with all bound keys visible
- Typing "music" in search dims everything except the M key (Super+M → Music launcher)
- Clicking the "Super+Shift" chip hides Super+M but reveals Super+Shift+M
- Clicking M while Super filter is active selects Super+M; editing its label
  changes the on-screen text live without writing to disk
- Repeating for two more keys, then `Ctrl+S` writes all three label comments to
  `hyprland.conf`, reloads Hyprland, and pushes via `dots`
- Reopening hyprkeys shows the new labels persisted
