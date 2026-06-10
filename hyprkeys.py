#!/usr/bin/env python3
"""hyprkeys — Hotkey cheatsheet + label editor for Hyprland. See SPEC.md."""
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell, Pango

import os
import signal
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from hyprkeys_parser import (  # noqa: E402
    parse_config, display_label, command_text, write_labels,
    mods_label, chip_for_bind,
)
from hyprkeys_layout import (  # noqa: E402
    LEFT_KEYS, LEFT_THUMB, RIGHT_KEYS, RIGHT_THUMB, CHIPS,
    BG, BG_ELEV, MUTED, TEXT, CYAN, YELLOW, RED, PURPLE,
)

PID_FILE = '/tmp/hyprkeys.pid'


CSS = f"""
window {{ background: transparent; }}
.popup-inner {{
    background-color: {BG};
    border-radius: 14px;
    margin: 16px;
    padding: 20px;
    box-shadow: 0 0 0 1px {PURPLE}, 0 0 32px {PURPLE};
}}
.app-title {{ color: {PURPLE}; font-family: "JetBrainsMono Nerd Font"; font-size: 16px; font-weight: bold; }}
.muted {{ color: {MUTED}; font-family: "JetBrainsMono Nerd Font"; font-size: 11px; }}
.search-entry {{
    background-color: {BG_ELEV}; color: {TEXT};
    border-radius: 8px; padding: 6px 10px;
    border: 1px solid {MUTED};
    font-family: "JetBrainsMono Nerd Font"; font-size: 13px;
}}
.search-entry:focus {{ border-color: {PURPLE}; }}
.chip {{
    background-color: {BG_ELEV}; color: {MUTED};
    border-radius: 999px; padding: 4px 12px; border: none;
    font-family: "JetBrainsMono Nerd Font"; font-size: 11px;
    box-shadow: none; text-shadow: none;
}}
.chip:hover {{ color: {TEXT}; }}
.chip.active {{ background-color: {PURPLE}; color: {BG}; }}
.key {{
    background-color: {BG_ELEV}; color: {MUTED};
    border-radius: 6px; border: 1px solid transparent; padding: 4px;
    font-family: "JetBrainsMono Nerd Font"; font-size: 12px;
    box-shadow: none; text-shadow: none;
}}
.key.bound {{ background-color: {BG}; color: {TEXT}; border: 1px solid {CYAN}; }}
.key.bound.dimmed {{ color: {MUTED}; border-color: {MUTED}; }}
.key.selected {{ border: 2px solid {PURPLE}; background-color: {BG}; color: {TEXT}; }}
.key.unsaved {{ border-color: {YELLOW}; }}
.key-cap {{ font-family: "JetBrainsMono Nerd Font"; font-size: 13px; font-weight: bold; }}
.key-sub {{ font-family: "JetBrainsMono Nerd Font"; font-size: 9px; color: {MUTED}; }}
.key.bound .key-sub {{ color: {TEXT}; }}
.detail-key {{ color: {PURPLE}; font-family: "JetBrainsMono Nerd Font"; font-size: 13px; font-weight: bold; }}
.detail-cmd {{ color: {MUTED}; font-family: "JetBrainsMono Nerd Font"; font-size: 11px; }}
.label-entry {{
    background-color: {BG_ELEV}; color: {TEXT};
    border-radius: 6px; padding: 6px 10px;
    border: 1px solid {MUTED};
    font-family: "JetBrainsMono Nerd Font"; font-size: 13px;
}}
.label-entry:focus {{ border-color: {PURPLE}; }}
.save-btn {{
    background-color: {CYAN}; color: {BG};
    border-radius: 8px; padding: 6px 14px;
    font-family: "JetBrainsMono Nerd Font"; font-size: 12px; font-weight: bold;
    border: none; box-shadow: none; text-shadow: none;
}}
.save-btn:disabled {{ background-color: {BG_ELEV}; color: {MUTED}; }}
.close-btn {{
    background: transparent; color: {MUTED}; border: none; padding: 2px 8px;
    font-family: "JetBrainsMono Nerd Font"; font-size: 16px;
    box-shadow: none; text-shadow: none;
}}
.close-btn:hover {{ color: {RED}; }}
.reset-btn {{
    background-color: {BG_ELEV}; color: {MUTED};
    border-radius: 6px; padding: 4px 10px;
    font-family: "JetBrainsMono Nerd Font"; font-size: 11px;
    border: none; box-shadow: none; text-shadow: none;
}}
.reset-btn:hover {{ color: {TEXT}; }}
.toast {{ color: {CYAN}; font-family: "JetBrainsMono Nerd Font"; font-size: 11px; }}
.half-label {{ color: {MUTED}; font-family: "JetBrainsMono Nerd Font"; font-size: 10px; }}
.media-row {{ color: {MUTED}; font-family: "JetBrainsMono Nerd Font"; font-size: 11px; }}
"""


class HyprKeys(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.binds, _ = parse_config()
        self.by_key = {}
        for b in self.binds:
            self.by_key.setdefault(b['key'], []).append(b)
        self.edits = {}          # line_no -> new_label
        self.undo_stack = []     # list of (line_no, prev_value or None)
        self.active_chip = 'All'
        self.search_text = ''
        self.selected_bind = None
        self.key_widgets = {}    # norm_key -> [ {button, cap, sub} ]
        self.chip_buttons = {}

        self._setup_window()
        self._build_ui()
        self._refresh_keys()
        self.show_all()
        self.search_entry.grab_focus()

    # ---- window setup
    def _setup_window(self):
        self.set_decorated(False)
        self.set_app_paintable(True)
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, edge, True)
        GtkLayerShell.set_exclusive_zone(self, -1)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        prov = Gtk.CssProvider()
        prov.load_from_data(CSS.encode())
        Gtk.StyleContext.add_provider_for_screen(
            screen, prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self.connect('key-press-event', self._on_key)
        self.connect('destroy', self._on_destroy)

    def _build_ui(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)
        self.add(outer)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.get_style_context().add_class('popup-inner')
        inner.set_size_request(1100, -1)
        outer.add(inner)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = Gtk.Label(label='hyprkeys')
        title.get_style_context().add_class('app-title')
        title.set_xalign(0)
        header.pack_start(title, False, False, 0)
        sub = Gtk.Label(label='hotkey atlas + label editor')
        sub.get_style_context().add_class('muted')
        sub.set_xalign(0)
        header.pack_start(sub, False, False, 0)
        header.pack_start(Gtk.Box(), True, True, 0)
        self.toast_lbl = Gtk.Label(label='')
        self.toast_lbl.get_style_context().add_class('toast')
        header.pack_start(self.toast_lbl, False, False, 0)
        self.save_btn = Gtk.Button(label='Save 0 changes')
        self.save_btn.get_style_context().add_class('save-btn')
        self.save_btn.set_sensitive(False)
        self.save_btn.connect('clicked', lambda _b: self._save())
        header.pack_start(self.save_btn, False, False, 0)
        close = Gtk.Button(label='✕')
        close.get_style_context().add_class('close-btn')
        close.connect('clicked', lambda _b: self._request_close())
        header.pack_start(close, False, False, 0)
        inner.pack_start(header, False, False, 0)

        # Search
        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class('search-entry')
        self.search_entry.set_placeholder_text('Search by label or key…')
        self.search_entry.connect('changed', self._on_search)
        self.search_entry.connect('activate', self._on_search_activate)
        inner.pack_start(self.search_entry, False, False, 0)

        # Chips
        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for name in CHIPS:
            btn = Gtk.Button(label=name)
            btn.get_style_context().add_class('chip')
            if name == 'All':
                btn.get_style_context().add_class('active')
            btn.connect('clicked', self._on_chip, name)
            self.chip_buttons[name] = btn
            chip_row.pack_start(btn, False, False, 0)
        inner.pack_start(chip_row, False, False, 0)

        # Keyboard
        kb_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        kb_row.set_halign(Gtk.Align.CENTER)
        kb_row.pack_start(self._build_half('LEFT', LEFT_KEYS, LEFT_THUMB), False, False, 0)
        kb_row.pack_start(self._build_half('RIGHT', RIGHT_KEYS, RIGHT_THUMB), False, False, 0)
        inner.pack_start(kb_row, False, False, 0)

        # Media / mouse strip
        self.media_label = Gtk.Label(label='')
        self.media_label.get_style_context().add_class('media-row')
        self.media_label.set_xalign(0.5)
        self.media_label.set_line_wrap(True)
        self.media_label.set_max_width_chars(120)
        inner.pack_start(self.media_label, False, False, 0)

        inner.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL), False, False, 0)

        # Detail
        self.detail_top = Gtk.Label(label='Click a key to edit its label')
        self.detail_top.get_style_context().add_class('detail-key')
        self.detail_top.set_xalign(0)
        inner.pack_start(self.detail_top, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_lbl = Gtk.Label(label='Label:')
        lbl_lbl.get_style_context().add_class('muted')
        row.pack_start(lbl_lbl, False, False, 0)
        self.label_entry = Gtk.Entry()
        self.label_entry.get_style_context().add_class('label-entry')
        self.label_entry.set_hexpand(True)
        self.label_entry.set_sensitive(False)
        self.label_entry.connect('changed', self._on_label_changed)
        row.pack_start(self.label_entry, True, True, 0)
        self.reset_btn = Gtk.Button(label='Reset')
        self.reset_btn.get_style_context().add_class('reset-btn')
        self.reset_btn.set_sensitive(False)
        self.reset_btn.connect('clicked', lambda _b: self._reset_current())
        row.pack_start(self.reset_btn, False, False, 0)
        inner.pack_start(row, False, False, 0)

        self.cmd_label = Gtk.Label(label='')
        self.cmd_label.get_style_context().add_class('detail-cmd')
        self.cmd_label.set_xalign(0)
        self.cmd_label.set_max_width_chars(140)
        self.cmd_label.set_ellipsize(Pango.EllipsizeMode.END)
        inner.pack_start(self.cmd_label, False, False, 0)

        self.variant_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        inner.pack_start(self.variant_row, False, False, 0)

    def _build_half(self, name, keys, thumb):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hdr = Gtk.Label(label=f'— {name} —')
        hdr.get_style_context().add_class('half-label')
        box.pack_start(hdr, False, False, 0)
        grid = Gtk.Grid()
        grid.set_row_spacing(4)
        grid.set_column_spacing(4)
        for cap, nk, r, c in keys:
            grid.attach(self._make_key_button(cap, nk), c, r, 1, 1)
        box.pack_start(grid, False, False, 0)
        tgrid = Gtk.Grid()
        tgrid.set_row_spacing(4)
        tgrid.set_column_spacing(4)
        tgrid.set_margin_top(4)
        tgrid.set_halign(Gtk.Align.CENTER)
        for cap, nk, r, c in thumb:
            tgrid.attach(self._make_key_button(cap, nk), c, r, 1, 1)
        box.pack_start(tgrid, False, False, 0)
        return box

    def _make_key_button(self, cap, norm):
        btn = Gtk.Button()
        btn.get_style_context().add_class('key')
        btn.set_size_request(64, 56)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        cap_lbl = Gtk.Label(label=cap)
        cap_lbl.get_style_context().add_class('key-cap')
        sub_lbl = Gtk.Label(label='')
        sub_lbl.get_style_context().add_class('key-sub')
        sub_lbl.set_max_width_chars(10)
        sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        vb.pack_start(cap_lbl, False, False, 0)
        vb.pack_start(sub_lbl, False, False, 0)
        btn.add(vb)
        btn.connect('clicked', self._on_key_click, norm)
        self.key_widgets.setdefault(norm, []).append({
            'button': btn, 'cap': cap_lbl, 'sub': sub_lbl,
        })
        return btn

    # ---- refresh
    def _refresh_keys(self):
        for norm, widgets in self.key_widgets.items():
            binds = self.by_key.get(norm, [])
            visible = self._visible_binds_for_key(norm)
            primary = visible[0] if visible else (binds[0] if binds else None)
            for w in widgets:
                ctx = w['button'].get_style_context()
                for cls in ('bound', 'dimmed', 'selected', 'unsaved'):
                    ctx.remove_class(cls)
                if not binds:
                    w['sub'].set_text('')
                    continue
                ctx.add_class('bound')
                if not visible:
                    ctx.add_class('dimmed')
                if (self.selected_bind and self.selected_bind['key'] == norm
                        and self.selected_bind in visible):
                    ctx.add_class('selected')
                if any(b['line_no'] in self.edits for b in binds):
                    ctx.add_class('unsaved')
                if primary is not None:
                    txt = self._effective_label(primary)
                    if len(binds) > 1:
                        txt = f'{txt} (+{len(binds)-1})'
                    w['sub'].set_text(txt[:14])
        self._refresh_media()
        self._refresh_save_btn()

    def _refresh_media(self):
        bits = []
        for b in self.binds:
            chip = chip_for_bind(b)
            if chip not in ('Media', 'Mouse'):
                continue
            if self.active_chip != 'All' and self.active_chip != chip:
                continue
            if self.search_text:
                hay = (self._effective_label(b).lower() + ' ' + b['key'].lower())
                if self.search_text not in hay:
                    continue
            bits.append(f"{b['key']} → {self._effective_label(b)}")
        self.media_label.set_text('  ·  '.join(bits) if bits else '')

    def _refresh_save_btn(self):
        n = len(self.edits)
        self.save_btn.set_label(f'Save {n} change{"s" if n != 1 else ""}')
        self.save_btn.set_sensitive(n > 0)

    def _effective_label(self, bind):
        return self.edits.get(bind['line_no'], display_label(bind))

    def _visible_binds_for_key(self, norm):
        out = []
        for b in self.by_key.get(norm, []):
            chip = chip_for_bind(b)
            if self.active_chip != 'All' and chip != self.active_chip:
                continue
            if self.search_text:
                hay = (self._effective_label(b).lower() + ' ' + b['key'].lower()
                       + ' ' + mods_label(b['mods']).lower())
                if self.search_text not in hay:
                    continue
            out.append(b)
        return out

    # ---- search / chips
    def _on_search(self, entry):
        self.search_text = entry.get_text().strip().lower()
        self._refresh_keys()

    def _on_search_activate(self, _entry):
        for b in self.binds:
            if b in self._visible_binds_for_key(b['key']):
                self._select_bind(b)
                return

    def _on_chip(self, _btn, name):
        self.active_chip = name
        for n, b in self.chip_buttons.items():
            ctx = b.get_style_context()
            (ctx.add_class if n == name else ctx.remove_class)('active')
        self._refresh_keys()

    # ---- selection / edit
    def _on_key_click(self, _btn, norm):
        visible = self._visible_binds_for_key(norm)
        all_binds = self.by_key.get(norm, [])
        if not all_binds:
            return
        self._select_bind(visible[0] if visible else all_binds[0])

    def _select_bind(self, bind):
        self.selected_bind = bind
        self.detail_top.set_text(
            f'{mods_label(bind["mods"])} + {bind["key"]}  →  {self._effective_label(bind)}'
        )
        self.label_entry.set_sensitive(True)
        self.reset_btn.set_sensitive(True)
        self.label_entry.handler_block_by_func(self._on_label_changed)
        self.label_entry.set_text(self._effective_label(bind))
        self.label_entry.handler_unblock_by_func(self._on_label_changed)
        self.cmd_label.set_text(command_text(bind))
        self._refresh_variants(bind)
        self._refresh_keys()
        self.label_entry.grab_focus()

    def _refresh_variants(self, bind):
        for child in self.variant_row.get_children():
            self.variant_row.remove(child)
        siblings = [b for b in self.by_key.get(bind['key'], []) if b is not bind]
        if not siblings:
            return
        hdr = Gtk.Label(label='Also on this key:')
        hdr.get_style_context().add_class('muted')
        self.variant_row.pack_start(hdr, False, False, 0)
        for sib in siblings:
            btn = Gtk.Button(
                label=f'{mods_label(sib["mods"])} → {self._effective_label(sib)}'
            )
            btn.get_style_context().add_class('chip')
            btn.connect('clicked', lambda _b, s=sib: self._select_bind(s))
            self.variant_row.pack_start(btn, False, False, 0)
        self.variant_row.show_all()

    def _on_label_changed(self, entry):
        if not self.selected_bind:
            return
        b = self.selected_bind
        new = entry.get_text()
        original = b['label'] if b['label'] else display_label(b)
        prev = self.edits.get(b['line_no'])
        if new == original or new.strip() == '':
            if b['line_no'] in self.edits:
                self.undo_stack.append((b['line_no'], prev))
                del self.edits[b['line_no']]
        else:
            self.undo_stack.append((b['line_no'], prev))
            self.edits[b['line_no']] = new
        self.detail_top.set_text(
            f'{mods_label(b["mods"])} + {b["key"]}  →  {new or original}'
        )
        self._refresh_keys()

    def _reset_current(self):
        if not self.selected_bind:
            return
        b = self.selected_bind
        original = b['label'] if b['label'] else display_label(b)
        if b['line_no'] in self.edits:
            self.undo_stack.append((b['line_no'], self.edits[b['line_no']]))
            del self.edits[b['line_no']]
        self.label_entry.handler_block_by_func(self._on_label_changed)
        self.label_entry.set_text(original)
        self.label_entry.handler_unblock_by_func(self._on_label_changed)
        self.detail_top.set_text(
            f'{mods_label(b["mods"])} + {b["key"]}  →  {original}'
        )
        self._refresh_keys()

    def _undo(self):
        if not self.undo_stack:
            return
        line_no, prev = self.undo_stack.pop()
        if prev is None:
            self.edits.pop(line_no, None)
        else:
            self.edits[line_no] = prev
        if self.selected_bind and self.selected_bind['line_no'] == line_no:
            self._select_bind(self.selected_bind)
        else:
            self._refresh_keys()

    # ---- save
    def _save(self):
        if not self.edits:
            return
        edits = [{'line_no': ln, 'new_label': lbl} for ln, lbl in self.edits.items()]
        try:
            n = write_labels(edits)
        except Exception as e:
            self._toast(f'Save failed: {e}', error=True)
            return
        subprocess.Popen(['hyprctl', 'reload'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(['dots', f'relabel {n} hotkey(s)'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._toast(f'Saved {n} label{"s" if n != 1 else ""}. Reloaded.')
        self.edits.clear()
        self.undo_stack.clear()
        self.binds, _ = parse_config()
        self.by_key = {}
        for b in self.binds:
            self.by_key.setdefault(b['key'], []).append(b)
        if self.selected_bind:
            sk, sm = self.selected_bind['key'], self.selected_bind['mods']
            self.selected_bind = next(
                (b for b in self.by_key.get(sk, []) if b['mods'] == sm), None,
            )
            if self.selected_bind:
                self._select_bind(self.selected_bind)
        self._refresh_keys()

    def _toast(self, text, error=False):
        self.toast_lbl.set_text(text)
        if error:
            rgba = Gdk.RGBA()
            rgba.parse(RED)
            self.toast_lbl.override_color(Gtk.StateFlags.NORMAL, rgba)
        GLib.timeout_add(3500, lambda: self.toast_lbl.set_text('') or False)

    # ---- close
    def _request_close(self):
        if not self.edits:
            self.destroy()
            return
        n = len(self.edits)
        dlg = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text=f'Discard {n} unsaved change{"s" if n != 1 else ""}?',
        )
        dlg.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dlg.add_button('Discard', Gtk.ResponseType.NO)
        dlg.add_button('Save and close', Gtk.ResponseType.YES)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            self._save()
            self.destroy()
        elif resp == Gtk.ResponseType.NO:
            self.destroy()

    def _on_key(self, _w, ev):
        kv = ev.keyval
        ctrl = bool(ev.state & Gdk.ModifierType.CONTROL_MASK)
        if kv == Gdk.KEY_Escape:
            self._request_close()
            return True
        if ctrl and kv in (Gdk.KEY_s, Gdk.KEY_S):
            self._save()
            return True
        if ctrl and kv in (Gdk.KEY_z, Gdk.KEY_Z):
            self._undo()
            return True
        if ctrl and Gdk.KEY_1 <= kv <= Gdk.KEY_6:
            self._on_chip(None, CHIPS[kv - Gdk.KEY_1])
            return True
        if kv == Gdk.KEY_slash and not self.search_entry.is_focus():
            self.search_entry.grab_focus()
            return True
        return False

    def _on_destroy(self, _w):
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        Gtk.main_quit()


def main():
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE).read().strip())
            os.kill(pid, signal.SIGTERM)
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
            return
        except (ProcessLookupError, ValueError, OSError):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    HyprKeys()
    Gtk.main()


if __name__ == '__main__':
    main()
