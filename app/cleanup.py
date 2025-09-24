\
import re, unicodedata
LIGATURES = {"\ufb01":"fi","\ufb02":"fl"}
GUILLEMETS = {"«":"\"","»":"\"","‹":"'", "›":"'"}

def fix_hyphenation(text: str) -> str:
    return re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)

def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    for k,v in LIGATURES.items(): text = text.replace(k,v)
    for k,v in GUILLEMETS.items(): text = text.replace(k,v)
    text = text.replace("^^", "^")
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.replace('\r\n','\n').replace('\r','\n')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text

def cleanup_text(text: str) -> str: return normalize_unicode(fix_hyphenation(text))
