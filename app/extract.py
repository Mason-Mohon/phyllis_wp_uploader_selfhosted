\
import fitz, docx, mammoth

def extract_pdf_text(pdf_path: str) -> str:
    parts = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            t = page.get_text("text")
            if t: parts.append(t)
    return "\n".join(parts).strip()

def extract_docx_text(docx_path: str) -> str:
    d = docx.Document(docx_path)
    return "\n".join(p.text for p in d.paragraphs).strip()

def docx_to_html(docx_path: str) -> str:
    with open(docx_path, "rb") as f:
        return mammoth.convert_to_html(f).value
