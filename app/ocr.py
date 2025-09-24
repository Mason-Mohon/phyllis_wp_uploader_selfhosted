\
from typing import List
from pdf2image import convert_from_path
import pytesseract

def ocr_pdf_to_text(pdf_path: str) -> str:
    images = convert_from_path(pdf_path, dpi=300)
    parts: List[str] = []
    for img in images:
        t = pytesseract.image_to_string(img)
        if t: parts.append(t)
    return "\n".join(parts).strip()
