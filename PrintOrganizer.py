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

ACCENT = '#2563EB'
ACCENT_DARK = '#1D4ED8'
BG = '#F1F5F9'
CARD_BG = '#FFFFFF'
SUCCESS = '#16A34A'
WARNING = '#D97706'
ROW_EVEN = '#F8FAFC'
ROW_ODD = '#FFFFFF'


class PrintOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Print Organizer – Projekt')
        self.geometry('900x680')
        self.minsize(750, 500)
        self.configure(bg=BG)
        self.resizable(True, True)

        self._pages_info = []
        self._pdf_path = tk.StringVar()

        self._build_ui()

    # ------------------------------------------------------------------
    def _build_ui(self):
        # ── Zaglavlje ──────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=ACCENT, pady=10)
        hdr.pack(fill='x')
        tk.Label(hdr, text='Print Organizer', font=('Segoe UI', 16, 'bold'),
                 bg=ACCENT, fg='white').pack()
        tk.Label(hdr, text='Razvrstaj stranice projekta – kopirka vs. ploter',
                 font=('Segoe UI', 9), bg=ACCENT, fg='#BFDBFE').pack()

        # ── Odabir datoteke ────────────────────────────────────────────
        file_frame = tk.Frame(self, bg=BG, padx=16, pady=10)
        file_frame.pack(fill='x')

        tk.Label(file_frame, text='PDF datoteka:', font=('Segoe UI', 9, 'bold'),
                 bg=BG).grid(row=0, column=0, sticky='w', pady=2)

        path_entry = tk.Entry(file_frame, textvariable=self._pdf_path,
                              font=('Segoe UI', 9), relief='flat',
                              bg=CARD_BG, width=65)
        path_entry.grid(row=1, column=0, sticky='ew', padx=(0, 8), ipady=4)

        btn_browse = tk.Button(file_frame, text='Odaberi datoteku…',
                               font=('Segoe UI', 9, 'bold'),
                               bg=ACCENT, fg='white', relief='flat',
                               activebackground=ACCENT_DARK, activeforeground='white',
                               cursor='hand2', padx=12, pady=4,
                               command=self._browse)
        btn_browse.grid(row=1, column=1)

        btn_analyze = tk.Button(file_frame, text='Analiziraj ▶',
                                font=('Segoe UI', 9, 'bold'),
                                bg=SUCCESS, fg='white', relief='flat',
                                activebackground='#15803D', activeforeground='white',
                                cursor='hand2', padx=12, pady=4,
                                command=self._analyze)
        btn_analyze.grid(row=1, column=2, padx=(8, 0))

        file_frame.columnconfigure(0, weight=1)

        # ── Kartica rezultata ──────────────────────────────────────────
        results_outer = tk.Frame(self, bg=BG, padx=16)
        results_outer.pack(fill='both', expand=True)

        # Sažetak (dva okvira: kopirka i ploter)
        summary_row = tk.Frame(results_outer, bg=BG)
        summary_row.pack(fill='x', pady=(0, 8))
        summary_row.columnconfigure(0, weight=1)
        summary_row.columnconfigure(1, weight=1)

        self._kopirka_card = self._make_summary_card(
            summary_row, 'KOPIRKA', 'A4 i A3 stranice', '#EFF6FF', '#2563EB', 0)
        self._ploter_card = self._make_summary_card(
            summary_row, 'PLOTER', 'A2, A1, A0 i nestandardni', '#FFF7ED', '#C2410C', 1)

        # Rasponi za kopiranje
        ranges_frame = tk.LabelFrame(results_outer, text='Rasponi stranica za ispis',
                                     font=('Segoe UI', 9, 'bold'),
                                     bg=BG, fg='#334155', padx=10, pady=8, relief='flat',
                                     bd=1)
        ranges_frame.pack(fill='x', pady=(0, 8))
        ranges_frame.columnconfigure(1, weight=1)

        self._kopirka_range_var = tk.StringVar(value='–')
        self._ploter_range_var = tk.StringVar(value='–')

        self._make_range_row(ranges_frame, 'Kopirka (A4/A3):', self._kopirka_range_var,
                             '#EFF6FF', '#2563EB', 0)
        self._make_range_row(ranges_frame, 'Ploter:', self._ploter_range_var,
                             '#FFF7ED', '#C2410C', 1)

        # Tablica stranica
        table_frame = tk.LabelFrame(results_outer, text='Popis stranica',
                                    font=('Segoe UI', 9, 'bold'),
                                    bg=BG, fg='#334155', padx=4, pady=4, relief='flat',
                                    bd=1)
        table_frame.pack(fill='both', expand=True)

        cols = ('stranica', 'format', 'orijentacija', 'ispis')
        self._tree = ttk.Treeview(table_frame, columns=cols, show='headings',
                                  height=12)

        self._tree.heading('stranica', text='Stranica')
        self._tree.heading('format', text='Format')
        self._tree.heading('orijentacija', text='Orijentacija')
        self._tree.heading('ispis', text='Uređaj za ispis')

        self._tree.column('stranica', width=80, anchor='center', stretch=False)
        self._tree.column('format', width=200, anchor='w')
        self._tree.column('orijentacija', width=120, anchor='center', stretch=False)
        self._tree.column('ispis', width=160, anchor='center', stretch=False)

        self._tree.tag_configure('kopirka', background='#EFF6FF', foreground='#1D4ED8')
        self._tree.tag_configure('ploter', background='#FFF7ED', foreground='#C2410C')
        self._tree.tag_configure('kopirka_alt', background='#DBEAFE', foreground='#1D4ED8')
        self._tree.tag_configure('ploter_alt', background='#FFEDD5', foreground='#C2410C')

        vsb = ttk.Scrollbar(table_frame, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        self._tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')

        self._apply_treeview_style()

        # Status bar
        self._status_var = tk.StringVar(value='Odaberi PDF datoteku i pritisni Analiziraj.')
        tk.Label(self, textvariable=self._status_var, font=('Segoe UI', 8),
                 bg='#CBD5E1', fg='#334155', anchor='w', padx=8, pady=3
                 ).pack(fill='x', side='bottom')

    # ------------------------------------------------------------------
    def _make_summary_card(self, parent, title, subtitle, bg, color, col):
        card = tk.Frame(parent, bg=bg, bd=1, relief='flat', padx=16, pady=10)
        card.grid(row=0, column=col, sticky='nsew', padx=(0, 6) if col == 0 else (6, 0))

        tk.Label(card, text=title, font=('Segoe UI', 11, 'bold'),
                 bg=bg, fg=color).pack(anchor='w')
        tk.Label(card, text=subtitle, font=('Segoe UI', 8),
                 bg=bg, fg='#64748B').pack(anchor='w')

        count_label = tk.Label(card, text='0 stranica', font=('Segoe UI', 20, 'bold'),
                               bg=bg, fg=color)
        count_label.pack(anchor='w', pady=(4, 0))
        return count_label

    def _make_range_row(self, parent, label_text, var, bg, color, row):
        tk.Label(parent, text=label_text, font=('Segoe UI', 9, 'bold'),
                 bg=BG, fg=color, width=18, anchor='e'
                 ).grid(row=row, column=0, padx=(0, 6), pady=3, sticky='e')

        entry = tk.Entry(parent, textvariable=var, font=('Courier New', 9),
                         bg=bg, fg='#1E293B', relief='flat', state='readonly',
                         readonlybackground=bg)
        entry.grid(row=row, column=1, sticky='ew', ipady=3, pady=3)

        btn = tk.Button(parent, text='Kopiraj',
                        font=('Segoe UI', 8, 'bold'),
                        bg=color, fg='white', relief='flat', padx=8,
                        activebackground=ACCENT_DARK, activeforeground='white',
                        cursor='hand2',
                        command=lambda v=var: self._copy_to_clipboard(v.get()))
        btn.grid(row=row, column=2, padx=(6, 0), pady=3)

    def _apply_treeview_style(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Treeview', rowheight=22, font=('Segoe UI', 9),
                        background=CARD_BG, fieldbackground=CARD_BG)
        style.configure('Treeview.Heading', font=('Segoe UI', 9, 'bold'),
                        background='#E2E8F0', foreground='#334155')
        style.map('Treeview', background=[('selected', ACCENT)],
                  foreground=[('selected', 'white')])

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
        # Očisti tablicu
        for row in self._tree.get_children():
            self._tree.delete(row)

        kopirka_pages = []
        ploter_pages = []

        for idx, info in enumerate(pages_info):
            tag_base = 'kopirka' if info['kopirka'] else 'ploter'
            tag = tag_base if idx % 2 == 0 else f'{tag_base}_alt'
            device = 'Kopirka' if info['kopirka'] else 'Ploter'

            self._tree.insert('', 'end', values=(
                info['page'],
                info['size'],
                info['orientation'],
                device,
            ), tags=(tag,))

            if info['kopirka']:
                kopirka_pages.append(info['page'])
            else:
                ploter_pages.append(info['page'])

        # Ažuriraj sažetak
        self._kopirka_card.config(text=f"{len(kopirka_pages)} stranica")
        self._ploter_card.config(text=f"{len(ploter_pages)} stranica")

        # Ažuriraj raspone
        k_range = pages_to_range_string(kopirka_pages) or '(nema)'
        p_range = pages_to_range_string(ploter_pages) or '(nema)'
        self._kopirka_range_var.set(k_range)
        self._ploter_range_var.set(p_range)

        total = len(pages_info)
        fname = Path(self._pdf_path.get()).name
        self._status_var.set(
            f'Analizirano: {fname}  |  Ukupno: {total} str.  |  '
            f'Kopirka: {len(kopirka_pages)}  |  Ploter: {len(ploter_pages)}'
        )

    def _copy_to_clipboard(self, text):
        if text and text != '(nema)':
            self.clipboard_clear()
            self.clipboard_append(text)
            self._status_var.set(f'Kopirano: {text}')


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
