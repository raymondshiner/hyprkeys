"""QMK / Moonlander firmware view for hyprkeys — the moonkeys backend UI.

A Gtk.Box embedded in the hyprkeys popup. Renders the live keymap.c on a
Moonlander-shaped grid (cap legend + per-key RGB swatch), with a per-key side
drawer for editing the keycode and HSV color. Save writes keymap.c atomically,
commits the moonlander repo, then opens the flash gate.
"""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango  # noqa: E402

import moonkeys_qmk as q
import moonkeys_flash as flash
from hyprkeys_layout import MUTED, TEXT, CYAN, YELLOW, PURPLE, BG_ELEV

# (LAYOUT idx, grid row, grid col) per half — derived from keyboard.json geometry.
LEFT_MAIN = [
    (0, 0, 0), (1, 0, 1), (2, 0, 2), (3, 0, 3), (4, 0, 4), (5, 0, 5), (6, 0, 6),
    (14, 1, 0), (15, 1, 1), (16, 1, 2), (17, 1, 3), (18, 1, 4), (19, 1, 5), (20, 1, 6),
    (28, 2, 0), (29, 2, 1), (30, 2, 2), (31, 2, 3), (32, 2, 4), (33, 2, 5), (34, 2, 6),
    (42, 3, 0), (43, 3, 1), (44, 3, 2), (45, 3, 3), (46, 3, 4), (47, 3, 5),
    (54, 4, 0), (55, 4, 1), (56, 4, 2), (57, 4, 3), (58, 4, 4),
]
RIGHT_MAIN = [
    (7, 0, 0), (8, 0, 1), (9, 0, 2), (10, 0, 3), (11, 0, 4), (12, 0, 5), (13, 0, 6),
    (21, 1, 0), (22, 1, 1), (23, 1, 2), (24, 1, 3), (25, 1, 4), (26, 1, 5), (27, 1, 6),
    (35, 2, 0), (36, 2, 1), (37, 2, 2), (38, 2, 3), (39, 2, 4), (40, 2, 5), (41, 2, 6),
    (48, 3, 1), (49, 3, 2), (50, 3, 3), (51, 3, 4), (52, 3, 5), (53, 3, 6),
    (61, 4, 2), (62, 4, 3), (63, 4, 4), (64, 4, 5), (65, 4, 6),
]
LEFT_THUMB = [(59, 0, 1), (66, 1, 0), (67, 1, 1), (68, 1, 2)]
RIGHT_THUMB = [(60, 0, 1), (69, 1, 0), (70, 1, 1), (71, 1, 2)]

LAYER_CHIPS = [('Default', 0), ('Other', 1), ('Apps', 2)]


class QmkView(Gtk.Box):
    def __init__(self, toast):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.toast = toast
        self.model = q.parse_keymap()
        self.layer = 0
        self.selected = None            # LAYOUT pos
        self.kc_edits = {}              # (layer, pos) -> keycode str
        self.hsv_edits = {}             # (layer, led) -> (h, s, v)
        self.keys = {}                  # pos -> {button, cap, swatch}
        self.layer_chips = {}
        self._block_drawer = False
        self._build()
        self.refresh()

    # ── current-value accessors (edit buffer wins over disk) ───────────────
    def cur_keycode(self, pos):
        return self.kc_edits.get((self.layer, pos),
                                 self.model['layers'][self.layer][pos]['keycode'])

    def cur_hsv(self, pos):
        led = q.LED_BY_LAYOUT[pos]
        if (self.layer, led) in self.hsv_edits:
            return self.hsv_edits[(self.layer, led)]
        leds = self.model['ledmap'][self.layer]
        return leds[led]['hsv'] if led < len(leds) else (0, 0, 0)

    def n_edits(self):
        return len(self.kc_edits) + len(self.hsv_edits)

    # ── build ──────────────────────────────────────────────────────────────
    def _build(self):
        # layer chip row
        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chip_row.set_halign(Gtk.Align.CENTER)
        lbl = Gtk.Label(label='Layer:')
        lbl.get_style_context().add_class('muted')
        chip_row.pack_start(lbl, False, False, 0)
        for name, idx in LAYER_CHIPS:
            btn = Gtk.Button(label=name)
            btn.get_style_context().add_class('chip')
            if idx == 0:
                btn.get_style_context().add_class('active')
            btn.connect('clicked', self._on_layer, idx)
            self.layer_chips[idx] = btn
            chip_row.pack_start(btn, False, False, 0)
        self.pack_start(chip_row, False, False, 0)

        # body: keyboard + drawer side by side
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        body.set_halign(Gtk.Align.CENTER)
        self.pack_start(body, False, False, 0)

        kb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
        kb.set_valign(Gtk.Align.START)
        kb.pack_start(self._build_half('LEFT', LEFT_MAIN, LEFT_THUMB), False, False, 0)
        kb.pack_start(self._build_half('RIGHT', RIGHT_MAIN, RIGHT_THUMB), False, False, 0)
        body.pack_start(kb, False, False, 0)

        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_LEFT)
        self.revealer.set_transition_duration(140)
        self.revealer.add(self._build_drawer())
        body.pack_start(self.revealer, False, False, 0)

    def _build_half(self, name, main, thumb):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        hdr = Gtk.Label(label=f'— {name} —')
        hdr.get_style_context().add_class('half-label')
        box.pack_start(hdr, False, False, 0)
        grid = Gtk.Grid(row_spacing=4, column_spacing=4)
        for pos, r, c in main:
            grid.attach(self._make_key(pos), c, r, 1, 1)
        box.pack_start(grid, False, False, 0)
        tgrid = Gtk.Grid(row_spacing=4, column_spacing=4)
        tgrid.set_halign(Gtk.Align.CENTER)
        tgrid.set_margin_top(6)
        for pos, r, c in thumb:
            tgrid.attach(self._make_key(pos), c, r, 1, 1)
        box.pack_start(tgrid, False, False, 0)
        return box

    def _make_key(self, pos):
        btn = Gtk.Button()
        btn.get_style_context().add_class('qkey')
        btn.set_size_request(60, 54)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        cap = Gtk.Label()
        cap.get_style_context().add_class('qcap')
        cap.set_justify(Gtk.Justification.CENTER)
        cap.set_line_wrap(True)
        cap.set_max_width_chars(7)
        cap.set_ellipsize(Pango.EllipsizeMode.END)
        sw = Gtk.DrawingArea()
        sw.set_size_request(-1, 6)
        sw.rgb = (0, 0, 0)
        sw.connect('draw', self._draw_swatch)
        vb.pack_start(cap, True, True, 0)
        vb.pack_start(sw, False, False, 0)
        btn.add(vb)
        btn.connect('clicked', self._on_key, pos)
        self.keys[pos] = {'button': btn, 'cap': cap, 'swatch': sw}
        return btn

    @staticmethod
    def _draw_swatch(area, cr):
        r, g, b = area.rgb
        w = area.get_allocated_width()
        h = area.get_allocated_height()
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        cr.rectangle(0, 0, w, h)
        cr.fill()
        return False

    def _build_drawer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.get_style_context().add_class('drawer')
        box.set_size_request(260, -1)

        self.d_title = Gtk.Label(xalign=0)
        self.d_title.get_style_context().add_class('detail-key')
        box.pack_start(self.d_title, False, False, 0)

        kl = Gtk.Label(label='Keycode', xalign=0)
        kl.get_style_context().add_class('muted')
        box.pack_start(kl, False, False, 0)
        self.kc_entry = Gtk.Entry()
        self.kc_entry.get_style_context().add_class('label-entry')
        comp = Gtk.EntryCompletion()
        self.kc_store = Gtk.ListStore(str)
        comp.set_model(self.kc_store)
        comp.set_text_column(0)
        comp.set_inline_completion(True)
        self.kc_entry.set_completion(comp)
        self.kc_entry.connect('changed', self._on_kc_changed)
        box.pack_start(self.kc_entry, False, False, 0)

        self.d_action = Gtk.Label(xalign=0)
        self.d_action.get_style_context().add_class('detail-cmd')
        self.d_action.set_line_wrap(True)
        self.d_action.set_max_width_chars(34)
        box.pack_start(self.d_action, False, False, 0)

        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL),
                       False, False, 4)

        cl = Gtk.Label(label='Color (HSV)', xalign=0)
        cl.get_style_context().add_class('muted')
        box.pack_start(cl, False, False, 0)
        self.big_swatch = Gtk.DrawingArea()
        self.big_swatch.set_size_request(-1, 34)
        self.big_swatch.rgb = (0, 0, 0)
        self.big_swatch.connect('draw', self._draw_swatch)
        box.pack_start(self.big_swatch, False, False, 0)

        self.sliders = {}
        for ch in ('H', 'S', 'V'):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            tag = Gtk.Label(label=ch)
            tag.get_style_context().add_class('muted')
            tag.set_size_request(14, -1)
            adj = Gtk.Adjustment(value=0, lower=0, upper=255, step_increment=1)
            sld = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                            adjustment=adj)
            sld.set_draw_value(True)
            sld.set_digits(0)
            sld.set_value_pos(Gtk.PositionType.RIGHT)
            sld.set_hexpand(True)
            sld.connect('value-changed', self._on_hsv_changed)
            self.sliders[ch] = sld
            row.pack_start(tag, False, False, 0)
            row.pack_start(sld, True, True, 0)
            box.pack_start(row, False, False, 0)

        sw_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        sw_row.set_homogeneous(True)
        for name, hsv in q.PALETTE:
            b = Gtk.Button()
            b.get_style_context().add_class('swatch-btn')
            b.set_size_request(-1, 18)
            b.set_tooltip_text(name)
            self._tint(b, hsv)
            b.connect('clicked', self._on_palette, hsv)
            sw_row.pack_start(b, True, True, 0)
        box.pack_start(sw_row, False, False, 0)

        return box

    def _tint(self, widget, hsv):
        prov = Gtk.CssProvider()
        prov.load_from_data(
            ('button { background-image:none; background-color:%s; '
             'border:1px solid rgba(0,0,0,0.25); box-shadow:none; }'
             % q.hsv_hex(*hsv)).encode())
        widget.get_style_context().add_provider(
            prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    # ── refresh ──────────────────────────────────────────────────────────
    def refresh(self):
        for pos, w in self.keys.items():
            kc = self.cur_keycode(pos)
            hsv = self.cur_hsv(pos)
            ctx = w['button'].get_style_context()
            for cls in ('transparent', 'selected', 'unsaved'):
                ctx.remove_class(cls)
            if q.is_transparent(kc):
                ctx.add_class('transparent')
            w['cap'].set_text(q.cap_label(self.model, kc))
            w['swatch'].rgb = q.hsv_to_rgb(*hsv)
            w['swatch'].queue_draw()
            if pos == self.selected:
                ctx.add_class('selected')
            led = q.LED_BY_LAYOUT[pos]
            if (self.layer, pos) in self.kc_edits or \
               (self.layer, led) in self.hsv_edits:
                ctx.add_class('unsaved')

    # ── events ───────────────────────────────────────────────────────────
    def _on_layer(self, _b, idx):
        self.layer = idx
        for i, b in self.layer_chips.items():
            ctx = b.get_style_context()
            (ctx.add_class if i == idx else ctx.remove_class)('active')
        if self.selected is not None:
            self._load_drawer(self.selected)
        self.refresh()

    def _on_key(self, _b, pos):
        self.selected = pos
        self._load_drawer(pos)
        self.revealer.set_reveal_child(True)
        self.refresh()

    def _load_drawer(self, pos):
        self._block_drawer = True
        kc = self.cur_keycode(pos)
        led = q.LED_BY_LAYOUT[pos]
        self.d_title.set_text(f'pos {pos} · LED {led}')
        self.kc_entry.set_text(kc)
        self._refresh_completion()
        meta = self.model['header'].get(q._norm_kc(kc))
        self.d_action.set_text(meta['action'] if meta else '(no Hyprland action)')
        h, s, v = self.cur_hsv(pos)
        self.sliders['H'].set_value(h)
        self.sliders['S'].set_value(s)
        self.sliders['V'].set_value(v)
        self.big_swatch.rgb = q.hsv_to_rgb(h, s, v)
        self.big_swatch.queue_draw()
        self._block_drawer = False

    def _refresh_completion(self):
        self.kc_store.clear()
        seen = set()
        for layer in self.model['layers'].values():
            for k in layer:
                kc = k['keycode']
                if kc not in seen:
                    seen.add(kc)
                    self.kc_store.append([kc])

    def _on_kc_changed(self, entry):
        if self._block_drawer or self.selected is None:
            return
        pos = self.selected
        new = entry.get_text().strip()
        disk = self.model['layers'][self.layer][pos]['keycode']
        if new == disk or not new:
            self.kc_edits.pop((self.layer, pos), None)
        else:
            self.kc_edits[(self.layer, pos)] = new
        meta = self.model['header'].get(q._norm_kc(new))
        self.d_action.set_text(meta['action'] if meta else '(no Hyprland action)')
        self.refresh()
        self._notify_count()

    def _on_hsv_changed(self, _s):
        if self._block_drawer or self.selected is None:
            return
        pos = self.selected
        led = q.LED_BY_LAYOUT[pos]
        hsv = (int(self.sliders['H'].get_value()),
               int(self.sliders['S'].get_value()),
               int(self.sliders['V'].get_value()))
        disk_leds = self.model['ledmap'][self.layer]
        disk = disk_leds[led]['hsv'] if led < len(disk_leds) else (0, 0, 0)
        if hsv == disk:
            self.hsv_edits.pop((self.layer, led), None)
        else:
            self.hsv_edits[(self.layer, led)] = hsv
        self.big_swatch.rgb = q.hsv_to_rgb(*hsv)
        self.big_swatch.queue_draw()
        self.refresh()
        self._notify_count()

    def _on_palette(self, _b, hsv):
        if self.selected is None:
            return
        self._block_drawer = True
        self.sliders['H'].set_value(hsv[0])
        self.sliders['S'].set_value(hsv[1])
        self.sliders['V'].set_value(hsv[2])
        self._block_drawer = False
        self._on_hsv_changed(None)

    # ── save / flash gate ────────────────────────────────────────────────
    _count_cb = None

    def set_count_callback(self, cb):
        self._count_cb = cb
        self._notify_count()

    def _notify_count(self):
        if self._count_cb:
            self._count_cb(self.n_edits())

    def save(self, parent):
        if self.n_edits() == 0:
            return
        n = self.n_edits()
        try:
            q.write_keymap(self.model, self.kc_edits, self.hsv_edits)
        except Exception as e:
            self.toast(f'Write failed: {e}', error=True)
            return
        ok, out = flash.git_commit(f'moonlander: {n} key edit(s) via moonkeys')
        self.kc_edits.clear()
        self.hsv_edits.clear()
        self.model = q.parse_keymap()
        self.refresh()
        self._notify_count()
        self.toast(f'Saved {n} edit(s) to keymap.c, committed.')
        self._flash_gate(parent)

    def _flash_gate(self, parent):
        dlg = Gtk.MessageDialog(
            transient_for=parent, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text='Build the firmware now?',
            secondary_text='Flashing needs you at the board to push the reset '
                           'pinhole on the right half when prompted.')
        dlg.add_button('Not yet', Gtk.ResponseType.CANCEL)
        dlg.add_button('Compile only', Gtk.ResponseType.NO)
        dlg.add_button('Compile + Flash', Gtk.ResponseType.YES)
        resp = dlg.run()
        dlg.destroy()
        if resp == Gtk.ResponseType.YES:
            flash.compile_and_flash()
            self.toast('Flashing in terminal — push the reset pinhole.')
        elif resp == Gtk.ResponseType.NO:
            flash.compile_only()
            self.toast('Compiling in terminal.')
