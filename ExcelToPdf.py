import fitz  # PyMuPDF
import tkinter as tk
from tkinter import filedialog

def add_text_to_pdf(input_pdf, output_pdf, text, x, y, page_number=0):
    """
    Add text to a specific page in a PDF file.

    Args:
        input_pdf (str): Path to the input PDF file.
        output_pdf (str): Path to save the modified PDF file.
        text (str): The text to add.
        x (float): X-coordinate on the page (in points).
        y (float): Y-coordinate on the page (in points).
        page_number (int): Page number where the text will be added (0-indexed).
    """
    # Open the PDF
    pdf_document = fitz.open(input_pdf)

    # Select the desired page
    if page_number < 0 or page_number >= len(pdf_document):
        raise ValueError("Invalid page number")
    page = pdf_document[page_number]

    # Add text at the specified position
    page.insert_text((x, y), text, fontsize=12, color=(0, 0, 0))  # Black color

    # Save the modified PDF
    pdf_document.save(output_pdf)
    pdf_document.close()

# Create a popup window for file selection
def select_file():
    root = tk.Tk()
    root.withdraw()  # Hide the root window
    file_path = filedialog.askopenfilename(title="Select a PDF File", filetypes=[("PDF Files", "*.pdf")])
    return file_path

# Main program
try:
    input_file = select_file()
    if not input_file:
        print("No file selected. Exiting.")
        exit()

    output_file = filedialog.asksaveasfilename(title="Save Output PDF As", defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
    if not output_file:
        print("No output file specified. Exiting.")
        exit()

    text_to_add = input("Enter the text you want to add: ")
    x_position = float(input("Enter the X-coordinate (in points): "))
    y_position = float(input("Enter the Y-coordinate (in points): "))
    page_to_edit = int(input("Enter the page number to edit (0 for first page): "))

    add_text_to_pdf(input_file, output_file, text_to_add, x_position, y_position, page_to_edit)
    print(f"Text added successfully to {output_file}")
except Exception as e:
    print(f"An error occurred: {e}")
