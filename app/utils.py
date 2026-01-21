\
import os, re, csv, time
from datetime import datetime, timedelta, timezone

DATE_RE = re.compile(r'^PSC_(\d{4})_(\d{2})_(\d{2})')

def iso_local_noon(date_str: str) -> str:
    y, m, d = map(int, date_str.split('-'))
    dt = datetime(y, m, d, 12, 0, 0)
    offset = (datetime.now().astimezone().utcoffset() or timedelta(0))
    return dt.replace(tzinfo=timezone(offset)).isoformat(timespec="seconds")

def parse_basename(stem: str):
    m = DATE_RE.match(stem)
    if not m: return None
    y, mo, da = m.groups()
    try: return f"{int(y):04d}-{int(mo):02d}-{int(da):02d}"
    except: return None

def ensure_csv(path: str):
    if not os.path.exists(path):
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(["timestamp","year_folder","basename","has_pdf","has_docx","date_parsed",
                        "title","status","ocr_used","cleanup_applied",
                        "wp_post_id","wp_url","author_set","error_message"])

def append_log(path: str, row: dict):
    ensure_csv(path)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow([
            row.get("timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
            row.get("year_folder",""), row.get("basename",""),
            str(row.get("has_pdf", False)), str(row.get("has_docx", False)),
            row.get("date_parsed",""), row.get("title",""), row.get("status",""),
            str(row.get("ocr_used", False)), str(row.get("cleanup_applied", False)),
            row.get("wp_post_id",""), row.get("wp_url",""),
            str(row.get("author_set", False)), row.get("error_message",""),
        ])

def read_done_set(path: str):
    done = set()
    if not os.path.exists(path): return done
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("status") in ("published","draft","skipped"):
                done.add(r.get("basename",""))
    return done

def list_items(source_root: str):
    items = []
    source_root = os.path.abspath(source_root)
    if not os.path.isdir(source_root): return items
    for entry in sorted(os.listdir(source_root)):
        year_dir = os.path.join(source_root, entry)
        if not os.path.isdir(year_dir): continue
        if not entry.isdigit(): continue
        for fname in sorted(os.listdir(year_dir)):
            p = os.path.join(year_dir, fname)
            if not os.path.isfile(p): continue
            stem, ext = os.path.splitext(fname)
            if not stem.startswith("PSC_"): continue
            if ext.lower() not in (".pdf",".docx"): continue
            iso = parse_basename(stem)
            if not iso: continue
            rec = next((x for x in items if x["basename"] == stem), None)
            if not rec:
                rec = {"year_folder": entry, "basename": stem, "pdf_path": None, "docx_path": None, "date_parsed": iso}
                items.append(rec)
            if ext.lower() == ".pdf": rec["pdf_path"] = p
            else: rec["docx_path"] = p
    items.sort(key=lambda x: x["date_parsed"])
    return items
