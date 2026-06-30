"""hyprland.conf parser, label heuristics, and atomic writeback."""
import os
import re

# Resolve the symlink: os.rename onto a symlink path would replace the link
# itself with the temp file, detaching ~/.config/hypr from ~/montressor.
CONFIG_PATH = os.path.realpath(os.path.expanduser('~/.config/hypr/hyprland.conf'))

BIND_RE = re.compile(
    r'^(?P<kw>bind[melE]*)\s*=\s*'
    r'(?P<mods>[^,]*),\s*'
    r'(?P<key>[^,]+?),\s*'
    r'(?P<disp>[^,]+?)'
    r'(?:,\s*(?P<params>.*?))?'
    r'(?:\s*#\s*@label:\s*(?P<label>.+?))?'
    r'\s*$'
)

LABEL_COMMENT_RE = re.compile(r'\s*#\s*@label:\s*.+\s*$')

MOD_ALIASES = {
    '$mainmod': 'Super',
    'super': 'Super',
    'shift': 'Shift',
    'ctrl': 'Ctrl',
    'control': 'Ctrl',
    'alt': 'Alt',
    'mod1': 'Alt',
}


def norm_key(raw):
    if not raw:
        return ''
    k = raw.strip()
    if len(k) == 1 and k.isalpha():
        return k.upper()
    return k


def norm_mods(raw):
    if not raw:
        return ()
    parts = re.split(r'[\s+]+', raw.strip())
    out = []
    for p in parts:
        if not p:
            continue
        canon = MOD_ALIASES.get(p.lower())
        out.append(canon if canon else p.capitalize())
    return tuple(sorted(set(out)))


def mods_label(mods):
    return '+'.join(mods) if mods else '(none)'


def chip_for_bind(bind):
    key = bind['key']
    if key.startswith('mouse'):
        return 'Mouse'
    if (key.startswith('XF86') or bind['kw'] in ('bindl', 'bindel')) and 'Super' not in bind['mods']:
        return 'Media'
    m = bind['mods']
    if m == ('Super',):
        return 'Super'
    if m == ('Shift', 'Super'):
        return 'Super+Shift'
    if m == ('Ctrl', 'Super'):
        return 'Super+Ctrl'
    return None


HEURISTIC_PATTERNS = [
    (re.compile(r'^\$terminal\b'), 'Terminal'),
    (re.compile(r'^\$fileManager\b'), 'Files'),
    (re.compile(r'^\$menu\b'), 'Launcher'),
]


def heuristic_label(disp, params):
    disp = (disp or '').strip()
    params = (params or '').strip()
    if disp == 'exec':
        for pat, lbl in HEURISTIC_PATTERNS:
            if pat.search(params):
                return lbl
        m = re.search(r'--title\s+(?:"([^"]+)"|\'([^\']+)\'|(\S+))', params)
        if m:
            return (m.group(1) or m.group(2) or m.group(3)).strip()
        first = params.split()[0] if params else ''
        if first.startswith('/') or first.startswith('~'):
            base = os.path.basename(first).rsplit('.', 1)[0]
            return base.replace('-', ' ').replace('_', ' ').title()
        return first[:24] if first else 'Exec'
    if disp == 'workspace':
        return f'Workspace {params}'
    if disp == 'movetoworkspace':
        return f'Send → WS {params}'
    if disp == 'movefocus':
        return {'l': 'Focus ←', 'r': 'Focus →', 'u': 'Focus ↑', 'd': 'Focus ↓'}.get(params, f'Focus {params}')
    if disp == 'togglefloating':
        return 'Toggle Float'
    if disp == 'killactive':
        return 'Kill Window'
    if disp == 'togglespecialworkspace':
        return 'Scratchpad'
    if disp == 'layoutmsg':
        return 'Toggle Split' if 'togglesplit' in params else f'Layout {params}'
    if disp == 'movewindow':
        return 'Move Window'
    if disp == 'resizewindow':
        return 'Resize Window'
    return f'{disp} {params}'.strip()[:32]


def parse_config():
    with open(CONFIG_PATH) as f:
        lines = f.read().splitlines()
    binds = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or not stripped.startswith('bind'):
            continue
        m = BIND_RE.match(stripped)
        if not m:
            continue
        params = (m.group('params') or '').strip()
        label = m.group('label')
        if label:
            params = LABEL_COMMENT_RE.sub('', params).strip()
        binds.append({
            'line_no': i,
            'kw': m.group('kw'),
            'mods': norm_mods(m.group('mods')),
            'key': norm_key(m.group('key')),
            'disp': (m.group('disp') or '').strip(),
            'params': params,
            'label': label.strip() if label else None,
            'raw': line,
        })
    return binds, lines


def display_label(bind):
    return bind['label'] if bind['label'] else heuristic_label(bind['disp'], bind['params'])


def command_text(bind):
    bits = [bind['disp']]
    if bind['params']:
        bits.append(bind['params'])
    return ', '.join(bits)


def write_labels(edits):
    """edits: list of {'line_no', 'new_label'}. Atomic rewrite. Returns count changed."""
    with open(CONFIG_PATH) as f:
        lines = f.read().splitlines(keepends=False)
    changed = 0
    for ed in edits:
        i = ed['line_no']
        if i >= len(lines):
            continue
        line = lines[i]
        new = LABEL_COMMENT_RE.sub('', line).rstrip()
        new_label = ed['new_label'].strip()
        if new_label:
            new = f'{new}  # @label: {new_label}'
        if new != line:
            lines[i] = new
            changed += 1
    tmp = CONFIG_PATH + '.tmp'
    data = '\n'.join(lines)
    if not data.endswith('\n'):
        data += '\n'
    with open(tmp, 'w') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.rename(tmp, CONFIG_PATH)
    return changed
