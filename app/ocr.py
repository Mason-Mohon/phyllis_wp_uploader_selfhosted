from typing import List
from pdf2image import convert_from_path
import pytesseract

def ocr_pdf_to_text(pdf_path: str) -> str:
    images = convert_from_path(pdf_path, dpi=300)
    parts: List[str] = []
    for img in images:
        t = pytesseract.image_to_string(img)
        if t: parts.append(t)
    
    # Join all pages
    raw_text = "\n".join(parts).strip()
    
    # Collapse paragraphs: split by double newlines (paragraph breaks)
    # then replace single newlines within each paragraph with spaces
    paragraphs = raw_text.split('\n\n')
    collapsed = []
    for para in paragraphs:
        # Replace single newlines with spaces within the paragraph
        collapsed_para = para.replace('\n', ' ').strip()
        if collapsed_para:
            collapsed.append(collapsed_para)
    
    return '\n\n'.join(collapsed)
