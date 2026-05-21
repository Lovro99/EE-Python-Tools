import tkinter as tk
from tkinter import filedialog
import shutil
import os
from datetime import datetime
import win32com.client as win32
import openpyxl

def select_file(title, filetypes):
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(title=title, filetypes=filetypes)
    return file_path

def read_excel_properties(filepath):
    wb = openpyxl.load_workbook(filepath, data_only=True)
    ws = wb["Podaci"]  # Točno list "Podaci"
    props = {}
    for row in ws.iter_rows(min_row=1, max_col=2, values_only=True):
        prop_name, prop_value = row
        if prop_name:
            props[str(prop_name)] = prop_value if prop_value is not None else ""
    return props

# Odaberi Excel i Word datoteke
excel_path = select_file("Odaberite Excel datoteku", [("Excel files", "*.xlsx *.xls"), ("All files", "*.*")])
print("Odabrani Excel:", excel_path)

word_path = select_file("Odaberite Word datoteku", [("Word files", "*.docm *.docx"), ("All files", "*.*")])
print("Odabrani Word:", word_path)

# Kreiraj kopiju Word dokumenta s vremenskim žigom
dir_name = os.path.dirname(word_path)
base_name = os.path.basename(word_path)
name, ext = os.path.splitext(base_name)
timestamp = datetime.now().strftime("%d_%m_%y--%H_%M")
new_word_name = f"{name}_Nova_kopija_{timestamp}{ext}"
new_word_path = os.path.join(dir_name, new_word_name)

shutil.copy2(word_path, new_word_path)
print("Kreirana kopija:", new_word_path)

# Start Word COM aplikaciju
word_app = win32.gencache.EnsureDispatch('Word.Application')
word_app.Visible = False

# Otvori kopiranu datoteku
doc = word_app.Documents.Open(new_word_path)

# Učitaj svojstva iz Excela samo Sheet "Podaci"
custom_properties = read_excel_properties(excel_path)

# Ažuriraj ili dodaj prilagođena svojstva u Word dokumentu
for prop_name, prop_value in custom_properties.items():
    props = doc.CustomDocumentProperties
    exists = False
    for i in range(1, props.Count + 1):
        if props.Item(i).Name == prop_name:
            props.Item(i).Value = prop_value
            exists = True
            print(f"Ažurirano svojstvo: {prop_name} = {prop_value}")
            break
    if not exists:
        props.Add(Name=prop_name, LinkToContent=False, Type=4, Value=prop_value)  # Type=4 for string

# Ažuriraj polja u dokumentu, zaglavljima i podnožjima
doc.Fields.Update()
for section in doc.Sections:
    for header in section.Headers:
        header.Range.Fields.Update()
    for footer in section.Footers:
        footer.Range.Fields.Update()

# Spremi i zatvori dokument
doc.Save()
doc.Close()

# Zatvori Word aplikaciju
word_app.Quit()

print("Dokument je spremljen i Word zatvoren.")
