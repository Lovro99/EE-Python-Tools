import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
from PIL import Image, ImageTk
import fitz  # PyMuPDF
import json
import os

PLACEMENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'klik_pozicije.json')
LOCATION_SETS = ["Zahtjev 1.2.1", "Zahtjev 1.6.1", "Rezerva"]

class PdfCanvasPlacer:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PDF klik unos podataka")

        self.excel_path = ''
        self.pdf_path = ''
        self.pdf_doc = None
        self.current_page = 0
        self.page_image = None
        self.canvas_img = None
        self.data = []
        self.selected_row = 0
        self.fontsize = 12

        self.scale_x, self.scale_y = 1, 1

        # fiksna tri seta lokacija
        self.placements = {name: {} for name in LOCATION_SETS}
        self.active_location_set = tk.StringVar(value=LOCATION_SETS[0])

        self.mode = tk.StringVar(value='move')
        self.load_placements()
        self.setup_ui()

    def setup_ui(self):
        top_buttons_frame = tk.Frame(self.root)
        top_buttons_frame.pack(side='top', fill='x')

        tk.Button(top_buttons_frame, text="Spremi pozicije", command=self.save_placements).pack(side='left', padx=2)
        tk.Button(top_buttons_frame, text="Generiraj PDF", command=self.make_pdf).pack(side='left', padx=2)
        tk.Button(top_buttons_frame, text="Povećaj font", command=self.increase_font).pack(side='left', padx=2)
        tk.Button(top_buttons_frame, text="Smanji font", command=self.decrease_font).pack(side='left', padx=2)

        # Radio tipke za način rada
        tk.Radiobutton(top_buttons_frame, text="Dodaj podatak", variable=self.mode, value='add').pack(side='left', padx=10)
        tk.Radiobutton(top_buttons_frame, text="Ukloni podatak", variable=self.mode, value='remove').pack(side='left')
        tk.Radiobutton(top_buttons_frame, text="Pomak podataka", variable=self.mode, value='move').pack(side='left', padx=10)

        # Izbor seta lokacija
        tk.Label(top_buttons_frame, text="Set lokacija:").pack(side='left', padx=10)
        self.location_menu = tk.OptionMenu(top_buttons_frame, self.active_location_set, *LOCATION_SETS, command=self.change_location_set)
        self.location_menu.pack(side='left')

        f = tk.Frame(self.root)
        f.pack(pady=5)
        tk.Button(f, text='Excel .xlsm ili .xlsx', command=self.load_excel).grid(row=0, column=0)
        tk.Button(f, text='PDF', command=self.load_pdf).grid(row=0, column=1)
        self.l_excel = tk.Label(f, text="Excel: -", wraplength=300, border=2,borderwidth=5)
        self.l_excel.grid(row=1, column=0)
        self.l_pdf = tk.Label(f, text="PDF: -",  wraplength=300)
        self.l_pdf.grid(row=1, column=1)

        self.row_lbl = tk.Label(f, text="Redak: -")
        self.row_lbl.grid(row=2, column=0, columnspan=2)
        navf = tk.Frame(f)
        navf.grid(row=3, column=0, columnspan=2)
        tk.Button(navf, text="<<", command=self.prev_row).grid(row=0, column=0)
        tk.Button(navf, text=">>", command=self.next_row).grid(row=0, column=1)

        self.data_lbl = tk.Label(f, text="Podatak: -")
        self.data_lbl.grid(row=4, column=0, columnspan=2)

        nav_pdf_f = tk.Frame(self.root)
        nav_pdf_f.pack()
        tk.Button(nav_pdf_f, text="<< Prethodna stranica", command=self.prev_pdf_page).pack(side='left')
        tk.Button(nav_pdf_f, text="Sljedeća stranica >>", command=self.next_pdf_page).pack(side='left')
        self.page_lbl = tk.Label(nav_pdf_f, text="Stranica: -")
        self.page_lbl.pack(side='left', padx=10)

        self.canvas = tk.Canvas(self.root, width=600, height=800, bg="grey")
        self.canvas.pack(padx=5, pady=5)
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.radiotext = tk.Label(self.root, text="Kliknite na PDF prema odabranom načinu rada")
        self.radiotext.pack()

    def change_location_set(self, value=None):
        self.update_row()
        self.draw_all_positions()



    def load_excel(self):
        path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsm *.xlsx")])
        if not path:
            return
        self.excel_path = path
        self.l_excel['text'] = os.path.basename(path)
        try:
            df = pd.read_excel(self.excel_path, sheet_name='Zahtjev', usecols="A,B", engine='openpyxl', dtype=str, header=None)
            self.data = df.values.tolist()
            self.selected_row = 0
            self.update_row()
            self.try_autofill()
        except ValueError as e:
            if "Worksheet named 'Zahtjev' not found" in str(e):
                messagebox.showwarning("Upozorenje", "Di ti je sheet Zahtjev!")
                self.data = []
                self.update_row()
            else:
                raise



    def load_pdf(self):
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        self.pdf_path = path
        self.l_pdf['text'] = os.path.basename(path)
        self.pdf_doc = fitz.open(self.pdf_path)
        self.current_page = 0
        self.show_pdf_page()
        self.try_autofill()

    def show_pdf_page(self):
        if not self.pdf_path or not self.pdf_doc:
            return
        page = self.pdf_doc[self.current_page]
        zoom = 1.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        self.page_image = img
        self.canvas_img = ImageTk.PhotoImage(self.page_image)
        w, h = self.page_image.size
        self.canvas.config(width=w, height=h)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor='nw', image=self.canvas_img)
        self.page_lbl['text'] = f"Stranica: {self.current_page + 1} / {len(self.pdf_doc)}"
        page_rect = page.rect
        self.scale_x = page_rect.width / w
        self.scale_y = page_rect.height / h
        self.draw_all_positions()

    def prev_pdf_page(self):
        if self.pdf_doc and self.current_page > 0:
            self.current_page -= 1
            self.show_pdf_page()
            self.try_autofill()

    def next_pdf_page(self):
        if self.pdf_doc and self.current_page < len(self.pdf_doc) - 1:
            self.current_page += 1
            self.show_pdf_page()
            self.try_autofill()

    def prev_row(self):
        if self.data and self.selected_row > 0:
            self.selected_row -= 1
            self.update_row()

    def next_row(self):
        if self.data and self.selected_row < len(self.data) - 1:
            self.selected_row += 1
            self.update_row()

    def update_row(self):
        if not self.data:
            self.row_lbl["text"] = "Redak: -"
            self.data_lbl["text"] = "Podatak: -"
            return
        self.row_lbl["text"] = f"Redak: {self.selected_row + 1} / {len(self.data)}"
        ime, podatak = self.data[self.selected_row]
        self.data_lbl["text"] = f"{ime} = {podatak}"
        self.draw_all_positions()

    def draw_all_positions(self):
        self.canvas.delete("tag_pos")
        curr_set = self.active_location_set.get()
        if curr_set not in self.placements: return
        page = self.current_page
        if not self.data: return
        # Prikaži sve pozicije iz seta na aktivnoj stranici
        for ent in self.placements[curr_set].get(str(page), []):
            rowidx = ent['row']
            x, y = ent['x'], ent['y']
            if rowidx < len(self.data):
                podatak = self.data[rowidx][1]
                #self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="yellow", tags="tag_pos")
                self.canvas.create_text(x, y, text=f"{podatak}", fill="red", tags="tag_pos")
                if rowidx == self.selected_row:
                    self.canvas.create_rectangle(x - 20, y - 5, x + 20, y + 5, outline="red", tags="tag_pos")
                
    def on_canvas_click(self, event):
        if not self.data:
            return
        curr_set = self.active_location_set.get()
        if curr_set not in self.placements:
            return
        page = self.current_page
        x, y = event.x, event.y
        # Inicijalizacija liste ako ne postoji za stranicu
        if str(page) not in self.placements[curr_set]:
            self.placements[curr_set][str(page)] = []
        entries = self.placements[curr_set][str(page)]
        rowidx = self.selected_row

        if self.mode.get() == 'add':
            # Dodaj novu poziciju za ovaj redak (dozvoljeno više puta)
            entries.append({'row': rowidx, 'x': x, 'y': y})
        elif self.mode.get() == 'remove':
            # Ukloni najbližu poziciju (za trenutni redak)
            minidx = None
            mindist = 15
            for idx, e in enumerate(entries):
                if e['row'] == rowidx:
                    dist = abs(e['x'] - x) + abs(e['y'] - y)
                    if dist < mindist:
                        mindist = dist
                        minidx = idx
            if minidx is not None:
                entries.pop(minidx)
        elif self.mode.get() == 'move':
            # Pomakni prvu postojeću poziciju za trenutni redak (ako postoji), inače dodaj novu
            for e in entries:
                if e['row'] == rowidx:
                    e['x'] = x
                    e['y'] = y
                    break
            else:
                entries.append({'row': rowidx, 'x': x, 'y': y})
        self.draw_all_positions()

    def save_placements(self):
        with open(PLACEMENTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.placements, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Spremanje", "Pozicije i podaci su spremljeni.")

    def load_placements(self):
        if os.path.exists(PLACEMENTS_FILE):
            with open(PLACEMENTS_FILE, encoding='utf-8') as f:
                data = json.load(f)
                for loc in LOCATION_SETS:
                    if loc in data:
                        self.placements[loc] = data[loc]
                            

    def try_autofill(self):
        self.update_row()

    def increase_font(self):
        self.fontsize += 2
        if self.fontsize > 72:
            self.fontsize = 72
        messagebox.showinfo("Font size", f"Veličina fonta postavljena na {self.fontsize}")

    def decrease_font(self):
        self.fontsize -= 2
        if self.fontsize < 6:
            self.fontsize = 6
        messagebox.showinfo("Font size", f"Veličina fonta postavljena na {self.fontsize}")

    def make_pdf(self):
        if not self.pdf_path:
            messagebox.showerror("Nedostaje", "Morate odabrati PDF!")
            return
        pdf = fitz.open(self.pdf_path)
        curr_set = self.active_location_set.get()
        if curr_set not in self.placements:
            messagebox.showerror("Nema pozicija", "Niste postavili niti jednu poziciju.")
            return

        for page_index in range(len(pdf)):
            page = pdf[page_index]
            page_rect = page.rect
            w = int(page_rect.width / self.scale_x)
            h = int(page_rect.height / self.scale_y)
            for ent in self.placements[curr_set].get(str(page_index), []):
                rowidx = ent['row']
                if rowidx < len(self.data):
                    podatak = self.data[rowidx][1]
                    font_size = self.fontsize
                    text_width = fitz.get_text_length(podatak, fontsize=font_size)
                    pdf_x = ent['x'] * self.scale_x - text_width // 2
                    pdf_y = ent['y'] * self.scale_y + font_size // 2
                    page.insert_text((pdf_x, pdf_y), podatak, fontsize=self.fontsize, color=(0, 0, 0))
        dir0 = os.path.dirname(self.pdf_path)
        fname = os.path.splitext(os.path.basename(self.pdf_path))[0] + '_ispunjeno.pdf'
        outname = os.path.join(dir0, fname)
        pdf.save(outname)
        pdf.close()
        messagebox.showinfo("PDF spreman", f"PDF spremljen kao:\n{outname}")

if __name__ == "__main__":
    app = PdfCanvasPlacer()
    app.root.mainloop()
