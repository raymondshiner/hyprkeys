"""Hotkeys list — the Hyprland side of moonkeys.

A flat, searchable, modifier-sorted registry of every hyprland.conf bind. The
friendly label is inline-editable (atomic writeback via the shared writer); the
dispatcher + params are shown read-only. Each row also shows which physical
Moonlander key sends the chord, fed from the QMK model.
"""
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk  # noqa: E402

from hyprkeys_parser import (
    parse_config, display_label, command_text, write_labels, mods_label,
)

# Modifier groups in display order; anything else sorts after, alphabetically.
_GROUP_ORDER = ['(none)', 'Super', 'Super+Shift', 'Super+Ctrl', 'Super+Alt',
                'Ctrl', 'Ctrl+Shift', 'Alt', 'Shift']

SORTS = [('Modifier', 'mods'), ('Key', 'key'), ('Label', 'label')]


class HotkeysList(Gtk.Box):
    def __init__(self, toast):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.toast = toast
        self.binds, _ = parse_config()
        self.edits = {}                 # line_no -> new_label
        self.send_index = {}            # (mods, key) -> [physical-key descriptors]
        self.search_text = ''
        self.sort_by = 'mods'
        self._count_cb = None
        self._saved_cb = None
        self._build()
        self._rebuild_rows()

    # ── external wiring ────────────────────────────────────────────────────
    def set_send_index(self, index):
        self.send_index = index
        self._rebuild_rows()

    def set_count_callback(self, cb):
        self._count_cb = cb
        self._notify_count()

    def set_saved_callback(self, cb):
        self._saved_cb = cb

    def reload(self):
        self.binds, _ = parse_config()
        self._rebuild_rows()

    def _notify_count(self):
        if self._count_cb:
            self._count_cb(len(self.edits))

    def n_edits(self):
        return len(self.edits)

    def focus_search(self):
        self.search_entry.grab_focus()

    # ── build ──────────────────────────────────────────────────────────────
    def _build(self):
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class('search-entry')
        self.search_entry.set_placeholder_text('Search hotkeys — label, key, command…')
        self.search_entry.set_hexpand(True)
        self.search_entry.connect('changed', self._on_search)
        top.pack_start(self.search_entry, True, True, 0)

        sort_lbl = Gtk.Label(label='Sort:')
        sort_lbl.get_style_context().add_class('muted')
        top.pack_start(sort_lbl, False, False, 0)
        self.sort_combo = Gtk.ComboBoxText()
        for label, _key in SORTS:
            self.sort_combo.append_text(label)
        self.sort_combo.set_active(0)
        self.sort_combo.connect('changed', self._on_sort)
        top.pack_start(self.sort_combo, False, False, 0)
        self.pack_start(top, False, False, 0)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(520)
        scroller.set_propagate_natural_height(False)
        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        scroller.add(self.list_box)
        self.pack_start(scroller, True, True, 0)

    # ── data helpers ────────────────────────────────────────────────────────
    def _label_of(self, bind):
        return self.edits.get(bind['line_no'], display_label(bind))

    def _group_of(self, bind):
        return mods_label(bind['mods'])

    def _matches(self, bind):
        if not self.search_text:
            return True
        hay = ' '.join([
            self._label_of(bind).lower(), bind['key'].lower(),
            self._group_of(bind).lower(), command_text(bind).lower(),
        ])
        return self.search_text in hay

    def _sorted_binds(self):
        binds = [b for b in self.binds if self._matches(b)]
        if self.sort_by == 'key':
            binds.sort(key=lambda b: (b['key'].lower(), self._group_of(b)))
        elif self.sort_by == 'label':
            binds.sort(key=lambda b: self._label_of(b).lower())
        else:
            def gkey(b):
                g = self._group_of(b)
                return (_GROUP_ORDER.index(g) if g in _GROUP_ORDER
                        else len(_GROUP_ORDER), g, b['key'].lower())
            binds.sort(key=gkey)
        return binds

    # ── rows ────────────────────────────────────────────────────────────────
    def _rebuild_rows(self):
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        binds = self._sorted_binds()
        grouped = (self.sort_by == 'mods')
        cur_group = None
        for b in binds:
            if grouped:
                g = self._group_of(b)
                if g != cur_group:
                    cur_group = g
                    self.list_box.pack_start(self._group_header(g), False, False, 0)
            self.list_box.pack_start(self._make_row(b), False, False, 0)
        if not binds:
            empty = Gtk.Label(label='No hotkeys match.')
            empty.get_style_context().add_class('muted')
            self.list_box.pack_start(empty, False, False, 8)
        self.list_box.show_all()

    def _group_header(self, group):
        lbl = Gtk.Label(label=group, xalign=0)
        lbl.get_style_context().add_class('group-header')
        lbl.set_margin_top(8)
        return lbl

    def _make_row(self, bind):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        row.get_style_context().add_class('hk-row')

        combo = self._combo_text(bind)
        chip = Gtk.Label(label=combo, xalign=0)
        chip.get_style_context().add_class('hk-chip')
        chip.set_size_request(150, -1)
        row.pack_start(chip, False, False, 0)

        entry = Gtk.Entry()
        entry.get_style_context().add_class('label-entry')
        entry.set_text(self._label_of(bind))
        entry.set_size_request(200, -1)
        if bind['line_no'] in self.edits:
            entry.get_style_context().add_class('unsaved')
        entry.connect('changed', self._on_label, bind)
        row.pack_start(entry, False, False, 0)

        cmd = Gtk.Label(label=command_text(bind), xalign=0)
        cmd.get_style_context().add_class('detail-cmd')
        cmd.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        cmd.set_hexpand(True)
        cmd.set_max_width_chars(48)
        row.pack_start(cmd, True, True, 0)

        senders = self.send_index.get((bind['mods'], bind['key']))
        if senders:
            send = Gtk.Label(label='⌨ ' + ', '.join(senders), xalign=1)
            send.get_style_context().add_class('xref')
            row.pack_start(send, False, False, 0)
        return row

    def _combo_text(self, bind):
        if bind['mods']:
            return '+'.join(bind['mods']) + '+' + bind['key']
        return bind['key']

    # ── events ────────────────────────────────────────────────────────────
    def _on_search(self, entry):
        self.search_text = entry.get_text().strip().lower()
        self._rebuild_rows()

    def _on_sort(self, combo):
        self.sort_by = SORTS[combo.get_active()][1]
        self._rebuild_rows()

    def _on_label(self, entry, bind):
        new = entry.get_text()
        original = display_label(bind)
        ctx = entry.get_style_context()
        if new == original or not new.strip():
            self.edits.pop(bind['line_no'], None)
            ctx.remove_class('unsaved')
        else:
            self.edits[bind['line_no']] = new
            ctx.add_class('unsaved')
        self._notify_count()

    # ── save ────────────────────────────────────────────────────────────────
    def save(self, _parent):
        if not self.edits:
            return
        edits = [{'line_no': ln, 'new_label': lbl} for ln, lbl in self.edits.items()]
        try:
            n = write_labels(edits)
        except Exception as e:
            self.toast(f'Save failed: {e}', error=True)
            return
        subprocess.Popen(['hyprctl', 'reload'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(['dots', f'relabel {n} hotkey(s)'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.toast(f'Saved {n} label{"s" if n != 1 else ""}. Reloaded.')
        self.edits.clear()
        self.binds, _ = parse_config()
        self._notify_count()
        self._rebuild_rows()
        if self._saved_cb:
            self._saved_cb()
