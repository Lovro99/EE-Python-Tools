"""
PrintOrganizer.py - Organizator ispisa projekata
Analizira PDF i razvrstava stranice: kopirka (A4/A3) vs ploter (A2/A1/A0/nestandardni)
"""

import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

try:
    from pypdf import PdfReader
    PDF_LIB = 'pypdf'
except ImportError:
    try:
        from PyPDF2 import PdfReader
        PDF_LIB = 'PyPDF2'
    except ImportError:
        PdfReader = None
        PDF_LIB = None

# 1 mm = 72/25.4 točaka
MM_TO_PT = 72.0 / 25.4
TOLERANCE_PT = 14  # ~5mm tolerancija

# Standardni formati (portret: manja x veća dimenzija), u mm
STANDARD_SIZES = {
    'A4':  (210, 297),
    'A3':  (297, 420),
    'A2':  (420, 594),
    'A1':  (594, 841),
    'A0':  (841, 1189),
}

KOPIRKA_FORMATS = {'A4', 'A3'}

# Pamti zadnju datoteku i zadanu mapu između pokretanja
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'printorganizer_config.json')


def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (OSError, ValueError):
        return {}           # nema ili oštećena konfiguracija – kreni od nule


def save_config(cfg):
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass                # nemogućnost snimanja ne smije srušiti alat


def mm_to_pt(mm):
    return mm * MM_TO_PT


def detect_paper_size(width_pt, height_pt):
    """Vrati (naziv_formata, orijentacija) za danu stranicu u točkama."""
    w = min(width_pt, height_pt)
    h = max(width_pt, height_pt)

    for name, (pw_mm, ph_mm) in STANDARD_SIZES.items():
        pw = mm_to_pt(pw_mm)
        ph = mm_to_pt(ph_mm)
        if abs(w - pw) <= TOLERANCE_PT and abs(h - ph) <= TOLERANCE_PT:
            orientation = 'Portret' if width_pt <= height_pt else 'Pejzaž'
            return name, orientation

    w_mm = width_pt / MM_TO_PT
    h_mm = height_pt / MM_TO_PT
    return f'Nestandardni ({w_mm:.0f}×{h_mm:.0f} mm)', 'Nestandardni'


def pages_to_range_string(pages):
    """Pretvori listu 1-baziranih brojeva stranica u kompaktni string raspona."""
    if not pages:
        return ''
    pages = sorted(set(pages))
    ranges = []
    start = end = pages[0]
    for p in pages[1:]:
        if p == end + 1:
            end = p
        else:
            ranges.append(str(start) if start == end else f'{start}-{end}')
            start = end = p
    ranges.append(str(start) if start == end else f'{start}-{end}')
    return ', '.join(ranges)


def group_pages(pages_info):
    """Spoji uzastopne stranice istog formata/orijentacije u jedan redak."""
    groups = []
    for info in pages_info:
        key = (info['size'], info['orientation'], info['kopirka'])
        if groups and groups[-1]['key'] == key and groups[-1]['end'] + 1 == info['page']:
            groups[-1]['end'] = info['page']
            groups[-1]['count'] += 1
        else:
            groups.append({
                'key': key,
                'start': info['page'],
                'end': info['page'],
                'count': 1,
                'size': info['size'],
                'orientation': info['orientation'],
                'kopirka': info['kopirka'],
            })
    return groups


def analyze_pdf(pdf_path):
    """Analiziraj PDF i vrati listu rječnika s info o svakoj stranici."""
    if PdfReader is None:
        raise ImportError(
            "Nedostaje pypdf biblioteka.\nInstaliraj je s: pip install pypdf"
        )
    reader = PdfReader(str(pdf_path))
    result = []
    for i, page in enumerate(reader.pages):
        w = float(page.mediabox.width)
        h = float(page.mediabox.height)
        size_name, orientation = detect_paper_size(w, h)
        result.append({
            'page': i + 1,
            'width_pt': w,
            'height_pt': h,
            'size': size_name,
            'orientation': orientation,
            'kopirka': size_name in KOPIRKA_FORMATS,
        })
    return result


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

BG = '#FFFFFF'          # pozadina
LINE = '#E3E6EA'        # tanke crte i rubovi
TEXT = '#111827'        # osnovni tekst
MUTED = '#6B7280'       # sporedni tekst
FIELD = '#F7F8FA'       # polja / zebra retci
BLUE = '#2563EB'        # kopirka
BLUE_DARK = '#1D4ED8'
ORANGE = '#EA580C'      # ploter
FONT = 'Segoe UI'
MONO = 'Consolas'


class PrintOrganizerApp(tk.Tk):
    PAD = 24

    def __init__(self):
        super().__init__()
        self.title('Print Organizer')
        self.geometry('880x780')
        self.minsize(720, 520)
        self.configure(bg=BG)

        self._pages_info = []
        self._pdf_path = tk.StringVar()
        self._group_var = tk.BooleanVar(value=True)
        self._config = load_config()
        self._analyzed_path = None   # PDF čiji su rezultati trenutno prikazani

        self._build_ui()

        last = self._config.get('zadnja_datoteka', '')
        if last and os.path.isfile(last):
            self._pdf_path.set(last)
            self._path_entry.xview_moveto(1.0)
            self._status_var.set('Učitana zadnja datoteka – pritisni Analiziraj.')

        self._pdf_path.trace_add('write', lambda *_: self._update_stale_warning())
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    # ------------------------------------------------------------------
    # Male pomoćne komponente
    # ------------------------------------------------------------------
    def _label(self, parent, text, size=9, bold=False, fg=TEXT, bg=BG):
        return tk.Label(parent, text=text, bg=bg, fg=fg,
                        font=(FONT, size, 'bold' if bold else 'normal'))

    def _button(self, parent, text, command, primary=False):
        """Gumb s tankim rubom – vraća okvir koji pozivatelj slaže u raspored."""
        border = BLUE if primary else LINE
        wrap = tk.Frame(parent, bg=border, padx=1, pady=1)
        btn = tk.Button(wrap, text=text, command=command,
                        font=(FONT, 9, 'bold' if primary else 'normal'),
                        bg=BLUE if primary else BG,
                        fg='white' if primary else TEXT,
                        activebackground=BLUE_DARK if primary else FIELD,
                        activeforeground='white' if primary else TEXT,
                        relief='flat', bd=0, highlightthickness=0,
                        padx=16, pady=6, cursor='hand2')
        btn.pack(fill='both', expand=True)

        hover = BLUE_DARK if primary else FIELD
        rest = BLUE if primary else BG
        btn.bind('<Enter>', lambda _e: btn.config(bg=hover))
        btn.bind('<Leave>', lambda _e: btn.config(bg=rest))
        return wrap

    def _entry(self, parent, textvariable, mono=False, readonly=False):
        """Polje s tankim rubom – vraća (okvir, entry)."""
        wrap = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        entry = tk.Entry(wrap, textvariable=textvariable,
                         font=(MONO if mono else FONT, 9),
                         bg=FIELD, fg=TEXT, insertbackground=TEXT, relief='flat',
                         state='readonly' if readonly else 'normal',
                         readonlybackground=FIELD)
        entry.pack(fill='x', ipady=6, ipadx=8)
        return wrap, entry

    def _rule(self):
        tk.Frame(self, bg=LINE, height=1).pack(fill='x')

    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = self.PAD

        # ── Naslov ─────────────────────────────────────────────────────
        head = tk.Frame(self, bg=BG, padx=pad)
        head.pack(fill='x', pady=(18, 16))
        self._label(head, 'Print Organizer', size=16, bold=True).pack(anchor='w')
        self._label(head, 'Razvrstavanje stranica projekta na kopirku i ploter',
                    size=9, fg=MUTED).pack(anchor='w', pady=(3, 0))

        self._rule()

        # ── Odabir datoteke ────────────────────────────────────────────
        file_row = tk.Frame(self, bg=BG, padx=pad)
        file_row.pack(fill='x', pady=14)
        file_row.columnconfigure(0, weight=1)

        wrap, self._path_entry = self._entry(file_row, self._pdf_path)
        wrap.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self._path_entry.bind('<Return>', lambda _e: self._analyze())

        self._button(file_row, 'Odaberi PDF', self._browse).grid(row=0, column=1)
        self._button(file_row, 'Analiziraj', self._analyze, primary=True
                     ).grid(row=0, column=2, padx=(8, 0))

        self._default_dir_var = tk.StringVar()
        dir_row = tk.Frame(file_row, bg=BG)
        dir_row.grid(row=1, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        tk.Label(dir_row, textvariable=self._default_dir_var, font=(FONT, 8),
                 bg=BG, fg=MUTED, anchor='w').pack(side='left', fill='x', expand=True)
        for text, cmd in (('Ukloni', self._clear_default_dir),
                          ('Zadana mapa…', self._choose_default_dir)):
            tk.Button(dir_row, text=text, command=cmd, font=(FONT, 8, 'underline'),
                      bg=BG, fg=BLUE, activebackground=BG, activeforeground=BLUE_DARK,
                      relief='flat', bd=0, highlightthickness=0, padx=4,
                      cursor='hand2').pack(side='right')
        self._update_default_dir_label()

        self._stale_label = tk.Label(
            file_row, font=(FONT, 9, 'bold'), bg='#FFF7ED', fg=ORANGE,
            anchor='w', padx=10, pady=6,
            text='⚠  Odabran je novi PDF – prikazani podaci su od prethodne '
                 'datoteke. Pritisni Analiziraj.')
        self._stale_label.grid(row=2, column=0, columnspan=3, sticky='ew', pady=(8, 0))
        self._stale_label.grid_remove()

        self._rule()

        # ── Sažetak ────────────────────────────────────────────────────
        stats = tk.Frame(self, bg=BG, padx=pad)
        stats.pack(fill='x', pady=(20, 22))
        for c in range(3):
            stats.columnconfigure(c, weight=1, uniform='stat')

        self._total_count = self._make_stat(stats, 'Ukupno', 'stranica u dokumentu',
                                            TEXT, 0)
        self._kopirka_count = self._make_stat(stats, 'Kopirka', 'A4 · A3', BLUE, 1)
        self._ploter_count = self._make_stat(stats, 'Ploter',
                                             'A2 · A1 · A0 · nestandardni', ORANGE, 2)

        # ── Rasponi ────────────────────────────────────────────────────
        ranges = tk.Frame(self, bg=BG, padx=pad)
        ranges.pack(fill='x')
        ranges.columnconfigure(1, weight=1)

        self._label(ranges, 'RASPONI ZA ISPIS', size=8, bold=True, fg=MUTED
                    ).grid(row=0, column=0, columnspan=3, sticky='w', pady=(0, 8))

        self._kopirka_range_var = tk.StringVar(value='–')
        self._ploter_range_var = tk.StringVar(value='–')
        self._make_range_row(ranges, 'Kopirka', self._kopirka_range_var, BLUE, 1)
        self._make_range_row(ranges, 'Ploter', self._ploter_range_var, ORANGE, 2)

        # ── Statusna traka ─────────────────────────────────────────────
        self._status_var = tk.StringVar(value='Odaberi PDF datoteku i pritisni Analiziraj.')
        status = tk.Frame(self, bg=BG)
        status.pack(fill='x', side='bottom')
        tk.Frame(status, bg=LINE, height=1).pack(fill='x')
        tk.Label(status, textvariable=self._status_var, font=(FONT, 8), bg=BG,
                 fg=MUTED, anchor='w', padx=pad).pack(fill='x', pady=(9, 11))

        # ── Tablica ────────────────────────────────────────────────────
        table_head = tk.Frame(self, bg=BG, padx=pad)
        table_head.pack(fill='x', pady=(22, 8))
        self._label(table_head, 'PREGLED STRANICA', size=8, bold=True, fg=MUTED
                    ).pack(side='left')
        tk.Checkbutton(table_head, text='Prikaži svaku stranicu',
                       variable=self._group_var, onvalue=False, offvalue=True,
                       command=self._refresh_table, font=(FONT, 9),
                       bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
                       selectcolor=BG, relief='flat', bd=0, highlightthickness=0,
                       cursor='hand2').pack(side='right')

        table_wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        table_wrap.pack(fill='both', expand=True, padx=pad)

        cols = ('stranice', 'format', 'orijentacija', 'ispis', 'broj', 'udio')
        self._tree = ttk.Treeview(table_wrap, columns=cols, show='headings',
                                  selectmode='browse')
        headings = {
            'stranice': 'Stranice', 'format': 'Format', 'orijentacija': 'Orijentacija',
            'ispis': 'Ispis', 'broj': 'Str.', 'udio': '',
        }
        widths = {
            'stranice': 130, 'format': 150, 'orijentacija': 120,
            'ispis': 100, 'broj': 70, 'udio': 170,
        }
        for col in cols:
            anchor = 'e' if col == 'broj' else 'w'
            self._tree.heading(col, text=headings[col], anchor=anchor)
            self._tree.column(col, width=widths[col], anchor=anchor,
                              stretch=(col == 'udio'), minwidth=50)

        self._tree.tag_configure('kopirka', foreground=BLUE, background=BG)
        self._tree.tag_configure('kopirka_alt', foreground=BLUE, background=FIELD)
        self._tree.tag_configure('ploter', foreground=ORANGE, background=BG)
        self._tree.tag_configure('ploter_alt', foreground=ORANGE, background=FIELD)
        self._tree.tag_configure('prazno', foreground=MUTED, background=BG)

        vsb = ttk.Scrollbar(table_wrap, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self._apply_style()
        self._show_placeholder()


    # ------------------------------------------------------------------
    def _make_stat(self, parent, title, subtitle, color, col):
        box = tk.Frame(parent, bg=BG)
        box.grid(row=0, column=col, sticky='w')

        self._label(box, title.upper(), size=8, bold=True, fg=MUTED).pack(anchor='w')
        value = tk.Label(box, text='–', font=(FONT, 28), bg=BG, fg=color)
        value.pack(anchor='w', pady=(2, 0))
        self._label(box, subtitle, size=8, fg=MUTED).pack(anchor='w', pady=(2, 0))
        return value

    def _make_range_row(self, parent, label_text, var, color, row):
        tk.Label(parent, text=label_text, font=(FONT, 9), bg=BG, fg=color,
                 width=9, anchor='w').grid(row=row, column=0, pady=4, sticky='w')

        wrap, _ = self._entry(parent, var, mono=True, readonly=True)
        wrap.grid(row=row, column=1, sticky='ew', pady=4)

        self._button(parent, 'Kopiraj', lambda v=var: self._copy_to_clipboard(v.get())
                     ).grid(row=row, column=2, padx=(10, 0), pady=4)

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', rowheight=28, font=(FONT, 9),
                        background=BG, fieldbackground=BG, foreground=TEXT,
                        borderwidth=0, relief='flat')
        style.configure('Treeview.Heading', font=(FONT, 8, 'bold'),
                        background=BG, foreground=MUTED, relief='flat',
                        padding=(10, 10), borderwidth=0)
        style.map('Treeview.Heading', background=[('active', FIELD)])
        style.map('Treeview', background=[('selected', '#E6EDFD')],
                  foreground=[('selected', TEXT)])
        style.configure('Vertical.TScrollbar', background=FIELD, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, relief='flat', width=12)
        style.map('Vertical.TScrollbar', background=[('active', '#D1D5DB')])

    # ------------------------------------------------------------------
    def _initial_dir(self):
        """Zadana mapa → mapa zadnje datoteke → Desktop."""
        last = self._pdf_path.get().strip().strip('"')
        for d in (self._config.get('zadana_mapa', ''),
                  os.path.dirname(last) if last else ''):
            if d and os.path.isdir(d):
                return d
        return str(Path.home() / 'Desktop')

    def _update_default_dir_label(self):
        d = self._config.get('zadana_mapa', '')
        self._default_dir_var.set(f'Zadana mapa: {d}' if d
                                  else 'Zadana mapa: nije postavljena')

    def _choose_default_dir(self):
        d = filedialog.askdirectory(title='Odaberi zadanu mapu za PDF-ove',
                                    initialdir=self._initial_dir())
        if d:
            self._config['zadana_mapa'] = os.path.normpath(d)
            save_config(self._config)
            self._update_default_dir_label()

    def _clear_default_dir(self):
        if self._config.pop('zadana_mapa', None) is not None:
            save_config(self._config)
        self._update_default_dir_label()

    def _update_stale_warning(self):
        """Prikaži upozorenje ako rezultati nisu od PDF-a upisanog u polje."""
        current = self._pdf_path.get().strip().strip('"')
        stale = (self._analyzed_path is not None and
                 os.path.normcase(os.path.normpath(current)) !=
                 os.path.normcase(os.path.normpath(self._analyzed_path)))
        if stale:
            self._stale_label.grid()
        else:
            self._stale_label.grid_remove()

    def _remember_file(self, path):
        self._config['zadnja_datoteka'] = os.path.normpath(path)
        save_config(self._config)

    def _on_close(self):
        path = self._pdf_path.get().strip().strip('"')
        if path and os.path.isfile(path):
            self._remember_file(path)
        self.destroy()

    def _browse(self):
        path = filedialog.askopenfilename(
            title='Odaberi PDF datoteku projekta',
            filetypes=[('PDF datoteke', '*.pdf'), ('Sve datoteke', '*.*')],
            initialdir=self._initial_dir(),
        )
        if path:
            self._pdf_path.set(path)
            self._path_entry.xview_moveto(1.0)   # prikaži kraj puta (naziv datoteke)
            self._remember_file(path)

    def _analyze(self):
        path = self._pdf_path.get().strip().strip('"')
        if not path:
            messagebox.showwarning('Nema datoteke', 'Odaberi PDF datoteku.')
            return
        if not os.path.isfile(path):
            messagebox.showerror('Greška', f'Datoteka ne postoji:\n{path}')
            return

        self._status_var.set('Analiziram PDF…')
        self.update_idletasks()

        try:
            pages_info = analyze_pdf(path)
        except ImportError as e:
            messagebox.showerror('Nedostaje biblioteka', str(e))
            self._status_var.set('Greška – instaliraj pypdf.')
            return
        except Exception as e:
            messagebox.showerror('Greška pri čitanju PDF-a', str(e))
            self._status_var.set('Greška pri čitanju PDF-a.')
            return

        self._remember_file(path)
        self._analyzed_path = path
        self._populate_results(pages_info)
        self._update_stale_warning()

    def _populate_results(self, pages_info):
        self._pages_info = pages_info
        kopirka_pages = [i['page'] for i in pages_info if i['kopirka']]
        ploter_pages = [i['page'] for i in pages_info if not i['kopirka']]

        self._refresh_table()

        self._total_count.config(text=str(len(pages_info)))
        self._kopirka_count.config(text=str(len(kopirka_pages)))
        self._ploter_count.config(text=str(len(ploter_pages)))

        self._kopirka_range_var.set(pages_to_range_string(kopirka_pages) or '–')
        self._ploter_range_var.set(pages_to_range_string(ploter_pages) or '–')

        self._status_var.set(f'{Path(self._pdf_path.get()).name}  ·  '
                             f'{len(group_pages(pages_info))} skupina formata')

    def _show_placeholder(self):
        self._tree.insert('', 'end', tags=('prazno',), values=(
            'Odaberi PDF i pritisni Analiziraj', '', '', '', '', ''))

    def _refresh_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        if not self._pages_info:
            self._show_placeholder()
            return

        grouped = self._group_var.get()
        if grouped:
            rows = [(
                f'{g["start"]}–{g["end"]}' if g['start'] != g['end'] else str(g['start']),
                g['size'], g['orientation'], g['kopirka'], g['count'],
            ) for g in group_pages(self._pages_info)]
        else:
            rows = [(str(i['page']), i['size'], i['orientation'], i['kopirka'], 1)
                    for i in self._pages_info]

        self._tree.heading('stranice', text='Stranice' if grouped else 'Stranica')
        self._tree.heading('broj', text='Str.' if grouped else '')

        max_count = max(r[4] for r in rows)
        for idx, (pages, size, orientation, is_kopirka, count) in enumerate(rows):
            tag = 'kopirka' if is_kopirka else 'ploter'
            if idx % 2:
                tag += '_alt'
            bar = '█' * max(1, round(count / max_count * 14)) if grouped else ''
            self._tree.insert('', 'end', tags=(tag,), values=(
                pages, size, orientation,
                'Kopirka' if is_kopirka else 'Ploter',
                count if grouped else '', bar,
            ))

    def _copy_to_clipboard(self, text):
        if text and text != '–':
            self.clipboard_clear()
            self.clipboard_append(text)
            self._status_var.set(f'Kopirano u međuspremnik: {text}')


# ---------------------------------------------------------------------------

def main():
    if PDF_LIB is None:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            'Nedostaje biblioteka',
            'pypdf nije instaliran.\n\nPokreni u terminalu:\n  pip install pypdf'
        )
        root.destroy()
        return

    app = PrintOrganizerApp()
    app.mainloop()


if __name__ == '__main__':
    main()
