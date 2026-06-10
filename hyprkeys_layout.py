"""Hardcoded ZSA Moonlander key grid + chip names + Andromeda color tokens."""

# (display_label, normalized_key, row, col) — cols increase left-to-right per half.
LEFT_KEYS = [
    ('`', 'grave', 0, 0), ('1', '1', 0, 1), ('2', '2', 0, 2), ('3', '3', 0, 3), ('4', '4', 0, 4), ('5', '5', 0, 5),
    ('Tab', 'Tab', 1, 0), ('Q', 'Q', 1, 1), ('W', 'W', 1, 2), ('E', 'E', 1, 3), ('R', 'R', 1, 4), ('T', 'T', 1, 5),
    ('Esc', 'Escape', 2, 0), ('A', 'A', 2, 1), ('S', 'S', 2, 2), ('D', 'D', 2, 3), ('F', 'F', 2, 4), ('G', 'G', 2, 5),
    ('Shift', 'Shift_L', 3, 0), ('Z', 'Z', 3, 1), ('X', 'X', 3, 2), ('C', 'C', 3, 3), ('V', 'V', 3, 4), ('B', 'B', 3, 5),
    ('Ctrl', 'Control_L', 4, 0), ('Super', 'Super_L', 4, 1), ('Alt', 'Alt_L', 4, 2),
    ('←', 'left', 4, 3), ('→', 'right', 4, 4),
]

LEFT_THUMB = [
    ('Space', 'space', 0, 0),
    ('Back', 'BackSpace', 0, 1),
    ('Hyper', 'hyper', 1, 1),
]

RIGHT_KEYS = [
    ('6', '6', 0, 0), ('7', '7', 0, 1), ('8', '8', 0, 2), ('9', '9', 0, 3), ('0', '0', 0, 4), ('-', 'minus', 0, 5),
    ('Y', 'Y', 1, 0), ('U', 'U', 1, 1), ('I', 'I', 1, 2), ('O', 'O', 1, 3), ('P', 'P', 1, 4), ('\\', 'backslash', 1, 5),
    ('H', 'H', 2, 0), ('J', 'J', 2, 1), ('K', 'K', 2, 2), ('L', 'L', 2, 3), (';', 'semicolon', 2, 4), ("'", 'apostrophe', 2, 5),
    ('N', 'N', 3, 0), ('M', 'M', 3, 1), (',', 'comma', 3, 2), ('.', 'period', 3, 3), ('/', 'slash', 3, 4), ('Shift', 'Shift_R', 3, 5),
    ('↑', 'up', 4, 0), ('↓', 'down', 4, 1), ('[', 'bracketleft', 4, 2), (']', 'bracketright', 4, 3), ('Ctrl', 'Control_R', 4, 4),
]

RIGHT_THUMB = [
    ('Enter', 'Return', 0, 0),
    ('Space', 'space', 0, 1),
    ('Meh', 'meh', 1, 0),
]

CHIPS = ['Super', 'Super+Shift', 'Super+Ctrl', 'Media', 'Mouse']

# Andromeda
BG = '#1C1E26'
BG_ELEV = '#23262E'
MUTED = '#677691'
TEXT = '#D5CED9'
CYAN = '#00E8C6'
YELLOW = '#FFE66D'
RED = '#EE5D43'
PURPLE = '#B084EB'
