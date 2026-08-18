"""
PrintOrganizer.py - Organizator ispisa projekata
Analizira PDF i razvrstava stranice: kopirka (A4/A3) vs ploter (A2/A1/A0/nestandardni)
"""

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
LINE = '#E5E7EB'        # tanke crte
TEXT = '#111827'        # osnovni tekst
MUTED = '#6B7280'       # sporedni tekst
FIELD = '#F9FAFB'       # polja / zebra retci
BLUE = '#2563EB'        # kopirka
ORANGE = '#EA580C'      # ploter
FONT = 'Segoe UI'


class PrintOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Print Organizer')
        self.geometry('820x620')
        self.minsize(700, 480)
        self.configure(bg=BG)

        self._pages_info = []
        self._pdf_path = tk.StringVar()
        self._group_var = tk.BooleanVar(value=True)

        self._build_ui()

    # ------------------------------------------------------------------
    # Male pomoćne komponente
    # ------------------------------------------------------------------
    def _label(self, parent, text, size=9, bold=False, fg=TEXT, bg=BG):
        return tk.Label(parent, text=text, bg=bg, fg=fg,
                        font=(FONT, size, 'bold' if bold else 'normal'))

    def _button(self, parent, text, command, primary=False):
        if primary:
            return tk.Button(parent, text=text, command=command,
                             font=(FONT, 9, 'bold'), bg=BLUE, fg='white',
                             activebackground='#1D4ED8', activeforeground='white',
                             relief='flat', bd=0, padx=14, pady=5, cursor='hand2')
        return tk.Button(parent, text=text, command=command,
                         font=(FONT, 9), bg=BG, fg=TEXT,
                         activebackground=FIELD, activeforeground=TEXT,
                         highlightbackground=LINE, highlightthickness=1,
                         relief='flat', bd=0, padx=14, pady=5, cursor='hand2')

    def _separator(self, parent, pady=0):
        tk.Frame(parent, bg=LINE, height=1).pack(fill='x', pady=pady)

    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = 22

        # ── Naslov ─────────────────────────────────────────────────────
        head = tk.Frame(self, bg=BG, padx=pad, pady=16)
        head.pack(fill='x')
        self._label(head, 'Print Organizer', size=15, bold=True).pack(anchor='w')
        self._label(head, 'Razvrstavanje stranica projekta na kopirku i ploter',
                    size=9, fg=MUTED).pack(anchor='w', pady=(2, 0))

        self._separator(self)

        # ── Odabir datoteke ────────────────────────────────────────────
        file_row = tk.Frame(self, bg=BG, padx=pad, pady=14)
        file_row.pack(fill='x')
        file_row.columnconfigure(0, weight=1)

        entry_wrap = tk.Frame(file_row, bg=LINE, padx=1, pady=1)
        entry_wrap.grid(row=0, column=0, sticky='ew', padx=(0, 8))
        tk.Entry(entry_wrap, textvariable=self._pdf_path, font=(FONT, 9),
                 relief='flat', bg=FIELD, fg=TEXT, insertbackground=TEXT
                 ).pack(fill='x', ipady=6, ipadx=6)

        self._button(file_row, 'Odaberi PDF', self._browse).grid(row=0, column=1)
        self._button(file_row, 'Analiziraj', self._analyze, primary=True
                     ).grid(row=0, column=2, padx=(8, 0))

        self._separator(self)

        # ── Sažetak ────────────────────────────────────────────────────
        stats = tk.Frame(self, bg=BG, padx=pad, pady=16)
        stats.pack(fill='x')
        stats.columnconfigure(0, weight=1)
        stats.columnconfigure(1, weight=1)

        self._kopirka_count = self._make_stat(stats, 'Kopirka', 'A4 · A3', BLUE, 0)
        self._ploter_count = self._make_stat(stats, 'Ploter', 'A2 · A1 · A0 · nestandardni',
                                             ORANGE, 1)

        # ── Rasponi ────────────────────────────────────────────────────
        ranges = tk.Frame(self, bg=BG, padx=pad)
        ranges.pack(fill='x')
        ranges.columnconfigure(1, weight=1)

        self._kopirka_range_var = tk.StringVar(value='–')
        self._ploter_range_var = tk.StringVar(value='–')
        self._make_range_row(ranges, 'Kopirka', self._kopirka_range_var, BLUE, 0)
        self._make_range_row(ranges, 'Ploter', self._ploter_range_var, ORANGE, 1)

        # ── Tablica ────────────────────────────────────────────────────
        table_head = tk.Frame(self, bg=BG, padx=pad)
        table_head.pack(fill='x', pady=(18, 6))
        self._label(table_head, 'Pregled stranica', size=9, bold=True).pack(side='left')
        tk.Checkbutton(table_head, text='Prikaži svaku stranicu',
                       variable=self._group_var, onvalue=False, offvalue=True,
                       command=self._refresh_table, font=(FONT, 9),
                       bg=BG, fg=MUTED, activebackground=BG, activeforeground=TEXT,
                       selectcolor=BG, relief='flat', bd=0, highlightthickness=0,
                       cursor='hand2').pack(side='right')

        table_wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        table_wrap.pack(fill='both', expand=True, padx=pad)

        cols = ('stranice', 'format', 'orijentacija', 'ispis')
        self._tree = ttk.Treeview(table_wrap, columns=cols, show='headings',
                                  selectmode='browse')
        self._tree.heading('stranice', text='Stranice')
        self._tree.heading('format', text='Format')
        self._tree.heading('orijentacija', text='Orijentacija')
        self._tree.heading('ispis', text='Ispis')

        self._tree.column('stranice', width=140, anchor='w', stretch=False)
        self._tree.column('format', width=200, anchor='w')
        self._tree.column('orijentacija', width=120, anchor='w', stretch=False)
        self._tree.column('ispis', width=100, anchor='w', stretch=False)

        self._tree.tag_configure('kopirka', foreground=BLUE, background=BG)
        self._tree.tag_configure('kopirka_alt', foreground=BLUE, background=FIELD)
        self._tree.tag_configure('ploter', foreground=ORANGE, background=BG)
        self._tree.tag_configure('ploter_alt', foreground=ORANGE, background=FIELD)

        vsb = ttk.Scrollbar(table_wrap, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self._apply_style()

        # ── Statusna traka ─────────────────────────────────────────────
        self._status_var = tk.StringVar(value='Odaberi PDF datoteku i pritisni Analiziraj.')
        status = tk.Frame(self, bg=BG)
        status.pack(fill='x', side='bottom')
        tk.Frame(status, bg=LINE, height=1).pack(fill='x')
        tk.Label(status, textvariable=self._status_var, font=(FONT, 8), bg=BG,
                 fg=MUTED, anchor='w', padx=pad).pack(fill='x', pady=(8, 10))

    # ------------------------------------------------------------------
    def _make_stat(self, parent, title, subtitle, color, col):
        box = tk.Frame(parent, bg=BG)
        box.grid(row=0, column=col, sticky='w', padx=(0, 40) if col == 0 else 0)

        self._label(box, title.upper(), size=8, bold=True, fg=MUTED).pack(anchor='w')

        value = tk.Label(box, text='0', font=(FONT, 26), bg=BG, fg=color)
        value.pack(anchor='w')

        self._label(box, subtitle, size=8, fg=MUTED).pack(anchor='w')
        return value

    def _make_range_row(self, parent, label_text, var, color, row):
        tk.Label(parent, text=label_text, font=(FONT, 9), bg=BG, fg=color,
                 width=8, anchor='w').grid(row=row, column=0, pady=3, sticky='w')

        wrap = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        wrap.grid(row=row, column=1, sticky='ew', pady=3)
        tk.Entry(wrap, textvariable=var, font=('Consolas', 9), bg=FIELD, fg=TEXT,
                 relief='flat', state='readonly', readonlybackground=FIELD
                 ).pack(fill='x', ipady=5, ipadx=6)

        self._button(parent, 'Kopiraj', lambda v=var: self._copy_to_clipboard(v.get())
                     ).grid(row=row, column=2, padx=(8, 0), pady=3)

    def _apply_style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', rowheight=26, font=(FONT, 9),
                        background=BG, fieldbackground=BG, foreground=TEXT,
                        borderwidth=0, relief='flat')
        style.configure('Treeview.Heading', font=(FONT, 8, 'bold'),
                        background=BG, foreground=MUTED, relief='flat', padding=(6, 8))
        style.map('Treeview.Heading', background=[('active', FIELD)])
        style.map('Treeview', background=[('selected', '#E5EDFF')],
                  foreground=[('selected', TEXT)])
        style.configure('Vertical.TScrollbar', background=FIELD, troughcolor=BG,
                        bordercolor=BG, arrowcolor=MUTED, relief='flat')

    # ------------------------------------------------------------------
    def _browse(self):
        path = filedialog.askopenfilename(
            title='Odaberi PDF datoteku projekta',
            filetypes=[('PDF datoteke', '*.pdf'), ('Sve datoteke', '*.*')],
            initialdir=str(Path.home() / 'Desktop'),
        )
        if path:
            self._pdf_path.set(path)

    def _analyze(self):
        path = self._pdf_path.get().strip()
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

        self._pages_info = pages_info
        self._populate_results(pages_info)

    def _populate_results(self, pages_info):
        self._pages_info = pages_info
        kopirka_pages = [i['page'] for i in pages_info if i['kopirka']]
        ploter_pages = [i['page'] for i in pages_info if not i['kopirka']]

        self._refresh_table()

        self._kopirka_count.config(text=str(len(kopirka_pages)))
        self._ploter_count.config(text=str(len(ploter_pages)))

        self._kopirka_range_var.set(pages_to_range_string(kopirka_pages) or '–')
        self._ploter_range_var.set(pages_to_range_string(ploter_pages) or '–')

        fname = Path(self._pdf_path.get()).name
        self._status_var.set(
            f'{fname}  ·  ukupno {len(pages_info)} stranica'
        )

    def _refresh_table(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        if not self._pages_info:
            return

        if self._group_var.get():
            rows = [
                (
                    f'{g["start"]}–{g["end"]}' if g['start'] != g['end'] else str(g['start']),
                    g['size'],
                    g['orientation'],
                    'Kopirka' if g['kopirka'] else 'Ploter',
                    g['kopirka'],
                    g['count'],
                )
                for g in group_pages(self._pages_info)
            ]
        else:
            rows = [
                (str(i['page']), i['size'], i['orientation'],
                 'Kopirka' if i['kopirka'] else 'Ploter', i['kopirka'], 1)
                for i in self._pages_info
            ]

        self._tree.heading('stranice', text='Stranice' if self._group_var.get() else 'Stranica')

        for idx, (pages, size, orientation, device, is_kopirka, count) in enumerate(rows):
            label = f'{pages}   ({count} str.)' if count > 1 else pages
            tag = 'kopirka' if is_kopirka else 'ploter'
            if idx % 2:
                tag += '_alt'
            self._tree.insert('', 'end', values=(label, size, orientation, device),
                              tags=(tag,))

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
