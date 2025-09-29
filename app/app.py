import os
import traceback
from urllib.parse import quote
from flask import Flask, jsonify, request, send_file, render_template
from dotenv import load_dotenv
load_dotenv()

from . import utils, extract, ocr as ocrmod, cleanup as cleanupmod, wp_client

app = Flask(__name__)

SOURCE_ROOT = os.getenv("SOURCE_ROOT", "").strip()
PROGRESS_LOG = os.getenv("PROGRESS_LOG")
if not PROGRESS_LOG:
    # Default to progress_log.csv in project root
    PROGRESS_LOG = os.path.join(os.path.dirname(os.path.dirname(__file__)), "progress_log.csv")
PROGRESS_LOG = PROGRESS_LOG.strip()
CATEGORY_NAME = os.getenv("WP_CATEGORY_NAME", "Phyllis Schlafly Report Column")  # Default to hardcoded name
AUTHOR_NAME = os.getenv("WP_AUTHOR_NAME", "")

# Debug: Print configuration
print(f"DEBUG - SOURCE_ROOT: '{SOURCE_ROOT}'")
print(f"DEBUG - SOURCE_ROOT exists: {os.path.exists(SOURCE_ROOT) if SOURCE_ROOT else False}")
print(f"DEBUG - PROGRESS_LOG: '{PROGRESS_LOG}'")

CATALOG = utils.list_items(SOURCE_ROOT)
print(f"DEBUG - CATALOG length: {len(CATALOG)}")
if CATALOG:
    print(f"DEBUG - First item: {CATALOG[0]}")
else:
    print("DEBUG - No items found in catalog")

@app.route("/")
def index(): return render_template("index.html")

@app.get("/api/next")
def api_next():
    global CATALOG
    print(f"DEBUG /api/next - SOURCE_ROOT: '{SOURCE_ROOT}'")
    if not SOURCE_ROOT: return jsonify({"error":"SOURCE_ROOT not configured in .env"}), 500
    if not CATALOG: 
        CATALOG = utils.list_items(SOURCE_ROOT)
        print(f"DEBUG /api/next - Reloaded CATALOG length: {len(CATALOG)}")
    done = utils.read_done_set(PROGRESS_LOG)
    print(f"DEBUG /api/next - Done set size: {len(done)}")
    print(f"DEBUG /api/next - Total CATALOG size: {len(CATALOG)}")
    next_item = next((it for it in CATALOG if it["basename"] not in done), None)
    print(f"DEBUG /api/next - Next item: {next_item}")
    if not next_item: return jsonify({"message":"All done!", "finished": True})

    initial_text = ""
    if next_item.get("pdf_path"):
        try: initial_text = extract.extract_pdf_text(next_item["pdf_path"])
        except Exception: initial_text = ""
    if not initial_text and next_item.get("docx_path"):
        try: initial_text = extract.extract_docx_text(next_item["docx_path"])
        except Exception: initial_text = initial_text or ""

    pdf_url = f"/source/pdf?path={quote(next_item['pdf_path'])}" if next_item.get("pdf_path") else None
    docx_html_url = f"/source/docx_html?path={quote(next_item['docx_path'])}" if next_item.get("docx_path") else None

    return jsonify({
        "year_folder": next_item["year_folder"],
        "basename": next_item["basename"],
        "date_parsed": next_item["date_parsed"],
        "has_pdf": bool(next_item.get("pdf_path")),
        "has_docx": bool(next_item.get("docx_path")),
        "pdf_url": pdf_url, "docx_html_url": docx_html_url,
        "initial_text": initial_text,
        "category": CATEGORY_NAME, "author": AUTHOR_NAME
    })

@app.post("/api/cleanup")
def api_cleanup():
    text = request.get_json(force=True).get("text","")
    return jsonify({"text": cleanupmod.cleanup_text(text)})

@app.post("/api/ocr")
def api_ocr():
    basename = request.get_json(force=True).get("basename")
    item = next((x for x in CATALOG if x["basename"] == basename), None)
    if not item or not item.get("pdf_path"): return jsonify({"error":"PDF not found"}), 404
    return jsonify({"text": ocrmod.ocr_pdf_to_text(item["pdf_path"])})

def _post_common(kind: str):
    data = request.get_json(force=True)
    basename = data.get("basename"); year_folder = data.get("year_folder")
    title = data.get("title","").strip(); date_iso = data.get("date","").strip()
    content = data.get("content","")

    item = next((x for x in CATALOG if x["basename"] == basename), None)
    has_pdf = bool(item and item.get("pdf_path")); has_docx = bool(item and item.get("docx_path"))

    if kind == "skip":
        utils.append_log(PROGRESS_LOG, {
            "year_folder": year_folder, "basename": basename, "has_pdf": has_pdf, "has_docx": has_docx,
            "date_parsed": date_iso, "title": title, "status": "skipped",
            "ocr_used": False, "cleanup_applied": False, "author_set": False, "wp_post_id": "", "wp_url": ""
        })
        return jsonify({"message":"Skipped."})

    if not title or not date_iso: return jsonify({"error":"Title and date required"}), 400
    status = "publish" if kind=="publish" else "draft"
    try:
        res = wp_client.create_post(title=title, content=content, date_iso=utils.iso_local_noon(date_iso), status=status)
        utils.append_log(PROGRESS_LOG, {
            "year_folder": year_folder, "basename": basename, "has_pdf": has_pdf, "has_docx": has_docx,
            "date_parsed": date_iso, "title": title, "status": "published" if status=="publish" else "draft",
            "ocr_used": False, "cleanup_applied": False, "author_set": res.get("author_set", False),
            "wp_post_id": res.get("id",""), "wp_url": res.get("URL","")
        })
        return jsonify({"message": f"{status.title()}ed.", "id": res.get("id"), "url": res.get("URL")})
    except Exception as e:
        print(f"ERROR in _post_common: {str(e)}")
        traceback.print_exc()
        utils.append_log(PROGRESS_LOG, {
            "year_folder": year_folder, "basename": basename, "has_pdf": has_pdf, "has_docx": has_docx,
            "date_parsed": date_iso, "title": title, "status": "error",
            "ocr_used": False, "cleanup_applied": False, "author_set": False, "wp_post_id": "", "wp_url": "", "error_message": str(e)
        })
        return jsonify({"error": str(e)}), 500

@app.post("/api/publish")
def api_publish(): return _post_common("publish")

@app.post("/api/draft")
def api_draft(): return _post_common("draft")

@app.post("/api/skip")
def api_skip(): return _post_common("skip")

@app.get("/api/log")
def api_log():
    utils.ensure_csv(PROGRESS_LOG)
    return send_file(PROGRESS_LOG, as_attachment=True, download_name=os.path.basename(PROGRESS_LOG))

@app.get("/source/pdf")
def source_pdf():
    path = request.args.get("path")
    if not path or not os.path.exists(path): return f"Not found: {path}", 404
    return send_file(path, mimetype="application/pdf")

@app.get("/source/docx_html")
def source_docx_html():
    path = request.args.get("path")
    if not path or not os.path.exists(path): return f"Not found: {path}", 404
    html = extract.docx_to_html(path)
    doc = f"<!doctype html><meta charset='utf-8'><style>body{{font-family:serif;line-height:1.6;padding:16px;max-width:800px;margin:auto}}</style>{html}"
    return doc

if __name__ == "__main__":
    app.run(debug=True)
