import fitz  # PyMuPDF

def extract_text_with_coordinates(pdf_path, page_number=0):
    """
    Extract text and its coordinates from a specific page in a PDF.

    Args:
        pdf_path (str): Path to the PDF file.
        page_number (int): Page number to inspect (0-indexed).

    Returns:
        List of tuples containing text and its coordinates.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_number]

    # Extract text with bounding boxes
    text_instances = page.get_text("blocks")  # Returns list of blocks (x0, y0, x1, y1, text)
    
    for block in text_instances:
        x0, y0, x1, y1, text = block[:5]
        print(f"Text: {text.strip()} | Coordinates: ({x0}, {y0}) to ({x1}, {y1})")
    
    doc.close()

# Example usage
pdf_file = "//192.168.30.150/Projekti/2_Radno/Solari/kuća Lehner/PM-1.6.1.Zahtjev_za_provjeru_mogucnosti_prikljucenja_kucanstva_s_vlastitom_proizvodnjom_Vugec.pdf"  # Replace with your PDF file path
page_to_inspect = 0  # First page (0-indexed)

extract_text_with_coordinates(pdf_file, page_to_inspect)
