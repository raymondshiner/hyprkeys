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

# QMK modifier wrappers -> Hyprland modifier names, and back to *_T() mod-tap macros.
MOD_WRAP_TO_HYPR = {
    'LGUI': 'Super', 'RGUI': 'Super', 'LSFT': 'Shift', 'RSFT': 'Shift',
    'LCTL': 'Ctrl', 'RCTL': 'Ctrl', 'LALT': 'Alt', 'RALT': 'Alt',
}
MOD_T_MACRO = {'Super': 'LGUI_T', 'Shift': 'LSFT_T', 'Ctrl': 'LCTL_T', 'Alt': 'LALT_T'}
MOD_HYPR_TO_WRAP = {'Super': 'LGUI', 'Shift': 'LSFT', 'Ctrl': 'LCTL', 'Alt': 'LALT'}
MOD_KC = {'Super': 'KC_LEFT_GUI', 'Shift': 'KC_LEFT_SHIFT',
          'Ctrl': 'KC_LEFT_CTRL', 'Alt': 'KC_LEFT_ALT'}

# LAYOUT position -> KC_ token for the arrow / space / common non-alnum keys,
# used when decoding a tap chord into a Hyprland (mods, key) pair.
_KC_TO_HYPR_KEY = {
    'KC_SPACE': 'space', 'KC_ENTER': 'return', 'KC_ESCAPE': 'escape',
    'KC_TAB': 'tab', 'KC_DELETE': 'delete', 'KC_BSPC': 'backspace',
    'KC_LEFT': 'left', 'KC_RIGHT': 'right', 'KC_UP': 'up', 'KC_DOWN': 'down',
    'KC_MINUS': 'minus', 'KC_EQUAL': 'equal', 'KC_SLASH': 'slash',
    'KC_COMMA': 'comma', 'KC_DOT': 'period', 'KC_SCLN': 'semicolon',
    'KC_QUOTE': 'apostrophe', 'KC_GRAVE': 'grave',
}


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


def _paren_args(s):
    """Top-level comma-split of the FIRST (...) group in s. 'F(A(x), B)' -> ['A(x)', 'B']."""
    i = s.index('(')
    spans, _ = _split_args(s, i)
    return [s[a:b].strip() for a, b in spans]


def _end_of_statement(text, brace_end):
    """Given the index just past a closing '}', return the index just past its ';'."""
    i = brace_end
    while i < len(text) and text[i] in ' \t\r\n':
        i += 1
    if i < len(text) and text[i] == ';':
        return i + 1
    return brace_end


# ── tap-dance section ──────────────────────────────────────────────────────

def parse_tap_dance(text):
    """Parse `enum tap_dance_codes` + `tap_dance_actions[]` into a managed model.

    Returns {names, actions, enum_span, arr_span} where actions maps a TD name
    to its raw ACTION_* initializer text, and the spans cover the full
    statements (through the trailing ';') for in-place regeneration.
    """
    names, enum_span = [], None
    m = re.search(r'enum\s+tap_dance_codes\s*\{', text)
    if m:
        brace = text.index('{', m.end() - 1)
        spans, end = _split_args(text, brace)
        for s, e in spans:
            ts, te = _trim(text, s, e)
            tok = text[ts:te]
            if tok:
                names.append(tok.split('=')[0].strip())
        enum_span = (m.start(), _end_of_statement(text, end))

    actions, arr_span = {}, None
    am = re.search(r'tap_dance_action_t\s+tap_dance_actions\s*\[\]\s*=\s*\{', text)
    if am:
        brace = text.index('{', am.end() - 1)
        spans, end = _split_args(text, brace)
        for s, e in spans:
            ts, te = _trim(text, s, e)
            tok = text[ts:te]
            em = re.match(r'\[(\w+)\]\s*=\s*(.+)', tok, re.S)
            if em:
                actions[em.group(1)] = re.sub(r'\s+', ' ', em.group(2)).strip()
        arr_span = (am.start(), _end_of_statement(text, end))

    return {'names': names, 'actions': actions,
            'enum_span': enum_span, 'arr_span': arr_span}


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

    tapdance = parse_tap_dance(text)

    managed_labels, labels_span = parse_managed_labels(text)
    for kc, lbl in managed_labels.items():
        action = header[kc]['action'] if kc in header else ''
        header[kc] = {'label': lbl, 'action': action}

    return {'text': text, 'path': path, 'layers': layers,
            'ledmap': ledmap, 'header': header, 'tapdance': tapdance,
            'labels': managed_labels, 'labels_span': labels_span}


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


# ── per-key behaviour slots (tap / double-tap / hold) ──────────────────────

# A "slots" dict:
#   {'tap': keycode_str|None, 'double': keycode_str|None,
#    'hold': None | ('layer', '_OTHER') | ('mod', 'Super')}

_MOD_T_RE = re.compile(r'(LGUI|RGUI|LSFT|RSFT|LCTL|RCTL|LALT|RALT)_T\((.+)\)')


def decode_slots(model, keycode):
    """Resolve a layout keycode token into tap / double / hold behaviour slots."""
    kc = _norm_kc(keycode)
    m = re.fullmatch(r'MO\((_\w+)\)', kc)
    if m:
        return {'tap': None, 'double': None, 'hold': ('layer', m.group(1))}
    m = re.fullmatch(r'LT\((_\w+),(.+)\)', kc)
    if m:
        return {'tap': m.group(2), 'double': None, 'hold': ('layer', m.group(1))}
    m = _MOD_T_RE.fullmatch(kc)
    if m:
        return {'tap': m.group(2), 'double': None,
                'hold': ('mod', MOD_WRAP_TO_HYPR[m.group(1)])}
    m = re.fullmatch(r'TD\((\w+)\)', kc)
    if m:
        return _decode_td(model, m.group(1))
    if is_transparent(kc):
        return {'tap': None, 'double': None, 'hold': None}
    return {'tap': keycode.strip(), 'double': None, 'hold': None}


def _decode_td(model, name):
    act = model['tapdance']['actions'].get(name, '')
    empty = {'tap': None, 'double': None, 'hold': None}
    a = _norm_kc(act)
    m = re.match(r'ACTION_TAP_DANCE_DOUBLE\(', a)
    if m:
        args = _paren_args(act)
        return {'tap': args[0], 'double': args[1] if len(args) > 1 else None,
                'hold': None}
    m = re.match(r'ACTION_TAP_DANCE_LAYER_MOVE\(', a)
    if m:
        args = _paren_args(act)
        return {'tap': args[0], 'double': None, 'hold': ('layer', args[1])}
    # Advanced fns generated by moonkeys carry an /* mk:tap=..;dbl=..;hold=.. */ tag.
    tag = re.search(r'mk:([^*]+)', act)
    if tag:
        return _slots_from_tag(tag.group(1))
    return empty


def _slots_from_tag(s):
    out = {'tap': None, 'double': None, 'hold': None}
    for part in s.split(';'):
        part = part.strip()
        if part.startswith('tap=') and part[4:]:
            out['tap'] = part[4:]
        elif part.startswith('dbl=') and part[4:]:
            out['double'] = part[4:]
        elif part.startswith('hold=') and part[5:]:
            hv = part[5:]
            out['hold'] = (('layer', hv) if hv.startswith('_')
                           else ('mod', hv))
    return out


def _tag_for_slots(slots):
    hold = ''
    if slots.get('hold'):
        hold = slots['hold'][1]
    return 'mk:tap=%s;dbl=%s;hold=%s' % (
        slots.get('tap') or '', slots.get('double') or '', hold)


def slots_equal(a, b):
    return (a.get('tap') == b.get('tap')
            and a.get('double') == b.get('double')
            and a.get('hold') == b.get('hold'))


def cap_from_slots(model, slots):
    """Two-line legend for a key from its slots: tap on top, badges below."""
    tap = slots.get('tap')
    top = cap_label(model, tap) if tap else ''
    if not top and slots.get('hold') and slots['hold'][0] == 'layer':
        top = 'L:' + slots['hold'][1].lstrip('_')[:3].title()
    badges = []
    if slots.get('double'):
        badges.append('··' + cap_label(model, slots['double']))
    if tap and slots.get('hold'):
        hk, hv = slots['hold']
        badges.append('⤓' + (('L:' + hv.lstrip('_')[:3].title())
                             if hk == 'layer' else hv[:2]))
    sub = ' '.join(badges)
    return top, sub


# ── QMK chord <-> Hyprland (mods, key) ─────────────────────────────────────

def _kc_to_hypr_key(kc):
    kc = _norm_kc(kc)
    if kc in _KC_TO_HYPR_KEY:
        return _KC_TO_HYPR_KEY[kc]
    m = re.fullmatch(r'KC_([A-Z])', kc)
    if m:
        return m.group(1)
    m = re.fullmatch(r'KC_(\d)', kc)
    if m:
        return m.group(1)
    m = re.fullmatch(r'KC_F(\d{1,2})', kc)
    if m:
        return 'F' + m.group(1)
    return None


def chord_to_hypr(keycode):
    """A tap keycode like LGUI(LSFT(KC_P)) -> (('Shift','Super'), 'P'), else None."""
    if not keycode:
        return None
    kc = _norm_kc(keycode)
    mods = []
    while True:
        m = re.fullmatch(r'([LR](?:GUI|SFT|CTL|ALT))\((.+)\)', kc)
        if not m:
            break
        mods.append(MOD_WRAP_TO_HYPR[m.group(1)])
        kc = m.group(2)
    key = _kc_to_hypr_key(kc)
    if key is None:
        return None
    return (tuple(sorted(set(mods))), key)


_HYPR_KEY_TO_KC = {v: k for k, v in _KC_TO_HYPR_KEY.items()}
_MOD_NEST_ORDER = ['Super', 'Ctrl', 'Alt', 'Shift']  # outer -> inner


def hypr_key_to_kc(key):
    if key in _HYPR_KEY_TO_KC:
        return _HYPR_KEY_TO_KC[key]
    if len(key) == 1 and key.isalpha():
        return 'KC_' + key.upper()
    if len(key) == 1 and key.isdigit():
        return 'KC_' + key
    m = re.fullmatch(r'[Ff](\d{1,2})', key)
    if m:
        return 'KC_F' + m.group(1)
    return None


def hypr_to_chord(mods, key):
    """Inverse of chord_to_hypr: (('Shift','Super'), 'P') -> 'LGUI(LSFT(KC_P))'."""
    kc = hypr_key_to_kc(key)
    if kc is None:
        return None
    ordered = [m for m in _MOD_NEST_ORDER if m in mods]
    if any(m not in _MOD_NEST_ORDER for m in mods):
        return None
    for m in reversed(ordered):
        kc = '%s(%s)' % (MOD_HYPR_TO_WRAP[m], kc)
    return kc


# ── managed per-key labels (keymap.c header, for keys with no Hyprland bind) ─

LBL_BEGIN = 'moonkeys:labels BEGIN'
LBL_END = 'moonkeys:labels END'
_LBL_LINE = re.compile(r'\s*\*\s*(\S.*?)\s*=\s*(.+?)\s*$')


def parse_managed_labels(text):
    """Read the ` * moonkeys:labels BEGIN … END` region -> ({keycode: label}, span)."""
    b = text.find(LBL_BEGIN)
    if b == -1:
        return {}, None
    e = text.find(LBL_END, b)
    if e == -1:
        return {}, None
    line_start = text.rfind('\n', 0, b) + 1
    line_end = text.find('\n', e)
    if line_end == -1:
        line_end = len(text)
    labels = {}
    for raw in text[b:e].splitlines():
        if LBL_BEGIN in raw:
            continue
        m = _LBL_LINE.match(raw)
        if m:
            labels[_norm_kc(m.group(1))] = m.group(2).strip()
    return labels, (line_start, line_end)


def _gen_labels_region(labels):
    lines = [' * ' + LBL_BEGIN + ' — managed by moonkeys, edit via the popup']
    for kc in sorted(labels):
        lines.append(' *   %s = %s' % (kc, labels[kc]))
    lines.append(' * ' + LBL_END)
    return '\n'.join(lines)


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


# ── slot-aware serialization (tap / double / hold + tap-dance regen) ───────

TD_BEGIN = '/* moonkeys:td BEGIN — generated; edit keys via moonkeys */'
TD_END = '/* moonkeys:td END */'

_MK_TD_HELPER = """typedef enum { MK_NONE, MK_UNKNOWN, MK_TAP, MK_HOLD, MK_DOUBLE } mk_td_state_t;
static mk_td_state_t mk_cur_dance(tap_dance_state_t *state) {
  if (state->count == 1) return (state->interrupted || !state->pressed) ? MK_TAP : MK_HOLD;
  if (state->count == 2) return MK_DOUBLE;
  return MK_UNKNOWN;
}"""

_ADV_FN_TMPL = """static mk_td_state_t {name}_state;
void {name}_finished(tap_dance_state_t *state, void *user_data) {{
  {name}_state = mk_cur_dance(state);
  switch ({name}_state) {{
    case MK_TAP:    register_code16({tap}); break;
    case MK_HOLD:   {hold_on} break;
    case MK_DOUBLE: register_code16({double}); break;
    default: break;
  }}
}}
void {name}_reset(tap_dance_state_t *state, void *user_data) {{
  switch ({name}_state) {{
    case MK_TAP:    unregister_code16({tap}); break;
    case MK_HOLD:   {hold_off} break;
    case MK_DOUBLE: unregister_code16({double}); break;
    default: break;
  }}
  {name}_state = MK_NONE;
}}"""


def _advanced_td(name, slots):
    tap = slots.get('tap') or 'KC_NO'
    double = slots.get('double') or 'KC_NO'
    hk, hv = slots['hold']
    if hk == 'layer':
        hold_on, hold_off = 'layer_on(%s);' % hv, 'layer_off(%s);' % hv
    else:
        modkc = MOD_KC[hv]
        hold_on = 'register_mods(MOD_BIT(%s));' % modkc
        hold_off = 'unregister_mods(MOD_BIT(%s));' % modkc
    fn = _ADV_FN_TMPL.format(name=name, tap=tap, double=double,
                             hold_on=hold_on, hold_off=hold_off)
    action = ('ACTION_TAP_DANCE_FN_ADVANCED(NULL, %s_finished, %s_reset) /* %s */'
              % (name, name, _tag_for_slots(slots)))
    return {'action': action, 'fn': fn}


def _slots_to_token(slots, layer, pos, registry):
    tap = slots.get('tap') or None
    double = slots.get('double') or None
    hold = slots.get('hold')
    if double:
        name = 'TD_L%d_P%d' % (layer, pos)
        if hold:
            registry[name] = _advanced_td(name, slots)
        else:
            registry[name] = {
                'action': 'ACTION_TAP_DANCE_DOUBLE(%s, %s)' % (tap or 'KC_NO', double),
                'fn': None,
            }
        return 'TD(%s)' % name
    if hold:
        hk, hv = hold
        if hk == 'layer':
            return 'LT(%s, %s)' % (hv, tap) if tap else 'MO(%s)' % hv
        return '%s(%s)' % (MOD_T_MACRO[hv], tap) if tap else MOD_KC[hv]
    return tap or 'KC_TRANSPARENT'


def _td_region_span(text, arr_span):
    b = text.find(TD_BEGIN)
    if b != -1:
        e = text.find(TD_END, b)
        if e != -1:
            return (b, e + len(TD_END))
    return arr_span


def _gen_td_blocks(referenced, existing_actions, registry):
    if not referenced:
        enum_text = 'enum tap_dance_codes {\n  TD_UNUSED,\n};'
        region = (TD_BEGIN + '\ntap_dance_action_t tap_dance_actions[] = {};\n' + TD_END)
        return enum_text, region
    enum_text = ('enum tap_dance_codes {\n'
                 + ',\n'.join('  ' + n for n in referenced) + ',\n};')
    parts = [TD_BEGIN]
    advanced = [(n, registry[n]['fn']) for n in referenced
                if n in registry and registry[n].get('fn')]
    if advanced:
        parts.append(_MK_TD_HELPER)
        parts.extend(fn for _n, fn in advanced)
    entries = []
    for n in referenced:
        if n in registry:
            act = registry[n]['action']
        else:
            act = existing_actions.get(n, 'ACTION_TAP_DANCE_DOUBLE(KC_NO, KC_NO)')
        entries.append('  [%s] = %s,' % (n, act))
    parts.append('tap_dance_action_t tap_dance_actions[] = {\n'
                 + '\n'.join(entries) + '\n};')
    parts.append(TD_END)
    return enum_text, '\n'.join(parts)


def serialize_full(model, slot_edits, hsv_edits, header_label_edits=None):
    """Return new keymap.c text with slot + HSV + label edits + regenerated tap dance."""
    text = model['text']
    td = model['tapdance']
    header_label_edits = header_label_edits or {}
    registry = {}
    repl = []
    final_tokens = {}
    for layer, keys in model['layers'].items():
        for k in keys:
            pos = k['idx']
            if (layer, pos) in slot_edits:
                tok = _slots_to_token(slot_edits[(layer, pos)], layer, pos, registry)
                final_tokens[(layer, pos)] = tok
                if tok != k['keycode']:
                    repl.append((k['span'][0], k['span'][1], tok))
            else:
                final_tokens[(layer, pos)] = k['keycode']

    used = set()
    for tok in final_tokens.values():
        used.update(re.findall(r'TD\((\w+)\)', tok))
    referenced, seen = [], set()
    for name in td['names'] + sorted(registry):
        if name in used and name not in seen:
            seen.add(name)
            referenced.append(name)
    for name in used:
        if name not in seen:
            seen.add(name)
            referenced.append(name)

    enum_text, region_text = _gen_td_blocks(referenced, td['actions'], registry)

    for (layer, led), hsv in hsv_edits.items():
        entry = next(e for e in model['ledmap'][layer] if e['idx'] == led)
        repl.append((entry['span'][0], entry['span'][1], '{%d,%d,%d}' % tuple(hsv)))
    if td['enum_span']:
        repl.append((td['enum_span'][0], td['enum_span'][1], enum_text))
    region_span = _td_region_span(text, td['arr_span'])
    if region_span:
        repl.append((region_span[0], region_span[1], region_text))

    if header_label_edits:
        labels = dict(model.get('labels', {}))
        for kc, lbl in header_label_edits.items():
            nk = _norm_kc(kc)
            if lbl and lbl.strip():
                labels[nk] = lbl.strip()
            else:
                labels.pop(nk, None)
        labels_text = _gen_labels_region(labels)
        span = model.get('labels_span')
        if span:
            repl.append((span[0], span[1], labels_text))
        elif labels:
            anchor = text.find('Skill for adding')
            if anchor != -1:
                ins = text.rfind('\n', 0, anchor) + 1
                repl.append((ins, ins, labels_text + '\n'))

    repl.sort(key=lambda r: r[0], reverse=True)
    for s, e, new in repl:
        text = text[:s] + new + text[e:]
    return text


def write_full(model, slot_edits, hsv_edits, header_label_edits=None, path=None):
    """Atomically write slot + HSV + label edits (regen tap dance). Returns edit count."""
    path = path or model['path']
    new_text = serialize_full(model, slot_edits, hsv_edits, header_label_edits)
    tmp = path + '.tmp'
    with open(tmp, 'w') as f:
        f.write(new_text)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, path)
    return len(slot_edits) + len(hsv_edits) + len(header_label_edits or {})


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
