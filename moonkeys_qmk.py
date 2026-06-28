"""QMK keymap.c parser + serializer for the Moonlander firmware.

Reads ~/montressor/moonlander/keymap/keymap.c into an in-memory model:
  - per-layer keycodes (indexed by LAYOUT_moonlander positional index 0..71)
  - per-layer per-LED HSV triplets from the `ledmap` array (indexed by LED index)
  - the human label + Hyprland action for labelled keycodes, parsed from the
    comment header table at the top of the file

Writes changes back by splicing only the bytes of changed keycode tokens and
HSV triplets, then atomic-renaming over the original. Never opens the file 'w'.

LAYOUT position -> LED index is not identity; the mapping is derived from
keyboard.json (cached at import, with an embedded fallback).
"""
import json
import os
import re

KEYMAP_PATH = os.path.expanduser('~/montressor/moonlander/keymap/keymap.c')
KEYBOARD_JSON = os.path.expanduser(
    '~/qmk_firmware/keyboards/zsa/moonlander/reva/keyboard.json')
MOONLANDER_DIR = os.path.expanduser('~/montressor/moonlander')

LAYER_ORDER = ['_DEFAULT', '_OTHER', '_APPS']
LAYER_INDEX = {'_DEFAULT': 0, '_OTHER': 1, '_APPS': 2}

# LAYOUT positional index -> RGB LED index. Derived from
# keyboard.json layouts.LAYOUT[*].matrix matched against rgb_matrix.layout.
# Embedded fallback for machines without the qmk_firmware checkout.
_LED_BY_LAYOUT_FALLBACK = [
    0, 5, 10, 15, 20, 25, 29, 65, 61, 56, 51, 46, 41, 36, 1, 6, 11, 16, 21,
    26, 30, 66, 62, 57, 52, 47, 42, 37, 2, 7, 12, 17, 22, 27, 31, 67, 63, 58,
    53, 48, 43, 38, 3, 8, 13, 18, 23, 28, 64, 59, 54, 49, 44, 39, 4, 9, 14,
    19, 24, 35, 71, 60, 55, 50, 45, 40, 32, 33, 34, 70, 69, 68,
]


def _load_led_by_layout():
    try:
        with open(KEYBOARD_JSON) as f:
            d = json.load(f)
        lay = d['layouts']['LAYOUT']['layout']
        rgb = d['rgb_matrix']['layout']
        led_by_matrix = {tuple(l['matrix']): i for i, l in enumerate(rgb)}
        out = [led_by_matrix[tuple(k['matrix'])] for k in lay]
        if len(out) == len(_LED_BY_LAYOUT_FALLBACK):
            return out
    except (OSError, KeyError, ValueError):
        pass
    return list(_LED_BY_LAYOUT_FALLBACK)


LED_BY_LAYOUT = _load_led_by_layout()
LED_COUNT = len(LED_BY_LAYOUT)


# ── span-aware C parsing helpers ───────────────────────────────────────────

_CLOSERS = {'(': ')', '{': '}'}


def _split_args(text, open_idx):
    """Split a (...) or {...} group into top-level arg spans.

    open_idx must point at the opening bracket. Returns (spans, end_idx) where
    spans is a list of (start, end) raw substrings between separators and
    end_idx is the index just past the matching closing bracket.
    """
    opener = text[open_idx]
    closer = _CLOSERS[opener]
    depth = 1
    i = open_idx + 1
    cur = i
    spans = []
    while i < len(text):
        ch = text[i]
        if ch in '({':
            depth += 1
        elif ch in ')}':
            depth -= 1
            if depth == 0:
                spans.append((cur, i))
                return spans, i + 1
        elif ch == ',' and depth == 1:
            spans.append((cur, i))
            cur = i + 1
        i += 1
    raise ValueError('unbalanced bracket from index %d' % open_idx)


def _trim(text, s, e):
    while s < e and text[s] in ' \t\r\n':
        s += 1
    while e > s and text[e - 1] in ' \t\r\n':
        e -= 1
    return s, e


def _section_start(text, decl):
    i = text.index(decl)
    return text.index('{', i)


# ── comment header table ───────────────────────────────────────────────────

# A keycode token: optional modifier wrappers around KC_*, or TD(...)/MO(...)/LT(...).
_KC_TOKEN = re.compile(
    r'(?:[A-Z]+\()*KC_[A-Z0-9_]+\)*'
    r'|TD\([A-Z0-9_]+\)'
    r'|MO\(_[A-Z]+\)'
    r'|LT\(_[A-Z]+,\s*KC_[A-Z0-9_]+\)'
)


def parse_header(text):
    """Parse the ' *  Label  KEYCODE  action' table into {keycode: {label, action}}."""
    out = {}
    block = text.split('LABELED KEYS', 1)
    if len(block) < 2:
        return out
    body = block[1].split('Skill for adding', 1)[0]
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith('*'):
            continue
        line = line[1:].strip()
        m = _KC_TOKEN.search(line)
        if not m:
            continue
        kc = _norm_kc(m.group(0))
        label = line[:m.start()].strip()
        action = line[m.end():].strip()
        if label and kc not in out:
            out[kc] = {'label': label, 'action': action}
    return out


def _norm_kc(s):
    """Collapse internal whitespace so 'LT(_APPS, KC_DELETE)' == 'LT(_APPS,KC_DELETE)'."""
    return re.sub(r'\s+', '', s)


# ── keymap + ledmap parsing ────────────────────────────────────────────────

def parse_keymap(path=None):
    path = path or KEYMAP_PATH
    with open(path) as f:
        text = f.read()

    header = parse_header(text)

    # keymaps section
    km_open = _section_start(text, 'keymaps[][MATRIX_ROWS][MATRIX_COLS]')
    layers = {}
    for name in LAYER_ORDER:
        decl = re.compile(r'\[' + name + r'\]\s*=\s*LAYOUT_moonlander\s*\(')
        m = decl.search(text, km_open)
        if not m:
            continue
        paren = text.index('(', m.end() - 1)
        spans, _ = _split_args(text, paren)
        keys = []
        for idx, (s, e) in enumerate(spans):
            ts, te = _trim(text, s, e)
            keys.append({'idx': idx, 'keycode': text[ts:te],
                         'span': (ts, te)})
        layers[LAYER_INDEX[name]] = keys

    # ledmap section
    lm_open = _section_start(text, 'ledmap[][RGB_MATRIX_LED_COUNT][3]')
    ledmap = {}
    for name in LAYER_ORDER:
        decl = re.compile(r'\[' + name + r'\]\s*=\s*\{')
        m = decl.search(text, lm_open)
        if not m:
            continue
        brace = text.index('{', m.end() - 1)
        spans, _ = _split_args(text, brace)
        leds = []
        for idx, (s, e) in enumerate(spans):
            ts, te = _trim(text, s, e)
            tok = text[ts:te]
            tm = re.match(r'\{\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\}', tok)
            if not tm:
                continue
            hsv = (int(tm.group(1)), int(tm.group(2)), int(tm.group(3)))
            leds.append({'idx': idx, 'hsv': hsv, 'span': (ts, te)})
        ledmap[LAYER_INDEX[name]] = leds

    return {'text': text, 'path': path, 'layers': layers,
            'ledmap': ledmap, 'header': header}


def key_view(model, layer, pos):
    """Unified per-key view for the UI at a given layer + LAYOUT position."""
    kc = model['layers'][layer][pos]['keycode']
    led = LED_BY_LAYOUT[pos]
    leds = model['ledmap'].get(layer, [])
    hsv = leds[led]['hsv'] if led < len(leds) else (0, 0, 0)
    meta = model['header'].get(_norm_kc(kc))
    return {'keycode': kc, 'led': led, 'hsv': hsv,
            'label': meta['label'] if meta else None,
            'action': meta['action'] if meta else None}


# ── serialization ──────────────────────────────────────────────────────────

def apply_changes(model, kc_edits, hsv_edits):
    """Return new file text with edits spliced in.

    kc_edits:  {(layer, pos): new_keycode_str}
    hsv_edits: {(layer, led): (h, s, v)}
    """
    text = model['text']
    repl = []  # (start, end, new_text)
    for (layer, pos), new_kc in kc_edits.items():
        span = model['layers'][layer][pos]['span']
        repl.append((span[0], span[1], new_kc))
    for (layer, led), hsv in hsv_edits.items():
        entry = next(e for e in model['ledmap'][layer] if e['idx'] == led)
        repl.append((entry['span'][0], entry['span'][1],
                     '{%d,%d,%d}' % tuple(hsv)))
    repl.sort(key=lambda r: r[0], reverse=True)
    for s, e, new in repl:
        text = text[:s] + new + text[e:]
    return text


def write_keymap(model, kc_edits, hsv_edits, path=None):
    """Atomically write the edited keymap. Returns the number of edits applied."""
    path = path or model['path']
    new_text = apply_changes(model, kc_edits, hsv_edits)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(new_text)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    return len(kc_edits) + len(hsv_edits)


# ── display helpers ────────────────────────────────────────────────────────

_BASIC = {
    'KC_TRANSPARENT': '', 'KC_NO': '', 'KC_TAB': 'Tab', 'KC_ESCAPE': 'Esc',
    'KC_ENTER': 'Ent', 'KC_DELETE': 'Del', 'KC_BSPC': 'Bsp', 'KC_SPACE': 'Spc',
    'KC_EQUAL': '=', 'KC_MINUS': '-', 'KC_QUOTE': "'", 'KC_SCLN': ';',
    'KC_BSLS': '\\', 'KC_COMMA': ',', 'KC_DOT': '.', 'KC_SLASH': '/',
    'KC_GRAVE': '`', 'KC_PIPE': '|', 'KC_LCBR': '{', 'KC_RCBR': '}',
    'KC_LBRC': '[', 'KC_RBRC': ']', 'KC_LPRN': '(', 'KC_RPRN': ')',
    'KC_LEFT': '←', 'KC_RIGHT': '→', 'KC_UP': '↑', 'KC_DOWN': '↓',
    'KC_LEFT_SHIFT': 'Shift', 'KC_RIGHT_SHIFT': 'Shift', 'KC_LEFT_CTRL': 'Ctrl',
    'KC_LEFT_ALT': 'Alt', 'KC_LEFT_GUI': 'Super', 'KC_RIGHT_GUI': 'Super',
    'KC_PC_CUT': 'Cut', 'KC_PC_COPY': 'Copy', 'KC_PC_PASTE': 'Paste',
}

_MOD_SHORT = {'LGUI': '◆', 'RGUI': '◆', 'LSFT': '⇧', 'RSFT': '⇧',
              'LCTL': '⌃', 'RCTL': '⌃', 'LALT': '⌥', 'RALT': '⌥'}


def is_transparent(kc):
    return _norm_kc(kc) in ('KC_TRANSPARENT', 'KC_NO')


def cap_label(model, kc):
    """Short legend for a key cap. Prefers the human label from the header."""
    norm = _norm_kc(kc)
    meta = model['header'].get(norm)
    if meta:
        return meta['label']
    if norm in _BASIC:
        return _BASIC[norm]
    m = re.fullmatch(r'KC_([A-Z0-9])', norm)
    if m:
        return m.group(1)
    m = re.fullmatch(r'KC_F(\d{1,2})', norm)
    if m:
        return 'F' + m.group(1)
    m = re.fullmatch(r'MO\(_([A-Z]+)\)', norm)
    if m:
        return 'L:' + m.group(1)[:3].title()
    m = re.fullmatch(r'LT\(_([A-Z]+),(KC_[A-Z0-9_]+)\)', norm)
    if m:
        return cap_label(model, m.group(2)) + '\nL:' + m.group(1)[:3].title()
    m = re.fullmatch(r'TD\(([A-Z0-9_]+)\)', norm)
    if m:
        return 'TD'
    # modifier-wrapped: LGUI(KC_S) -> ◆S
    m = re.fullmatch(r'([LR][A-Z]{3})\((.+)\)', norm)
    if m and m.group(1) in _MOD_SHORT:
        return _MOD_SHORT[m.group(1)] + cap_label(model, m.group(2))
    return norm.replace('KC_', '')


def hsv_to_rgb(h, s, v):
    """QMK HSV (each 0-255) -> (r, g, b) ints 0-255."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h / 255.0, s / 255.0, v / 255.0)
    return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))


def hsv_hex(h, s, v):
    return '#%02X%02X%02X' % hsv_to_rgb(h, s, v)


# Andromeda palette -> QMK HSV, mirrors the moonlander-hotkey skill color table.
PALETTE = [
    ('Cyan (active)', (121, 255, 232)),
    ('Green (good)', (68, 158, 255)),
    ('Yellow (warn)', (35, 146, 255)),
    ('Red (critical)', (6, 183, 237)),
    ('Purple (media)', (187, 113, 234)),
    ('White', (0, 0, 255)),
    ('Muted', (155, 74, 145)),
    ('Off', (0, 0, 0)),
]
