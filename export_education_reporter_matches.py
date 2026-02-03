import argparse
import csv
import html
import os
import sys
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

import requests
from dotenv import load_dotenv


NS = {
    "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
    "table": "urn:oasis:names:tc:opendocument:xmlns:table:1.0",
    "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
}


def build_session(username: str, app_password: str) -> requests.Session:
    session = requests.Session()
    session.auth = (username, app_password)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            ),
            "Accept": "application/json, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def read_json_response(resp: requests.Response, context: str):
    content_type = resp.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        snippet = (resp.text or "").strip()[:500]
        raise RuntimeError(
            f"{context} returned non-JSON response "
            f"(status {resp.status_code}, content-type '{content_type}'): {snippet}"
        )
    try:
        return resp.json()
    except ValueError:
        try:
            snippet = resp.content[:500].decode("utf-8", errors="replace")
        except Exception:
            snippet = (resp.text or "").strip()[:500]
        raise RuntimeError(
            f"{context} returned invalid JSON "
            f"(status {resp.status_code}, content-type '{content_type}'): {snippet}"
        )


def normalize_month(value) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        month = int(float(s))
        if 1 <= month <= 12:
            return month
    except ValueError:
        pass
    month_map = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    key = s.lower()[:3]
    return month_map.get(key)


def normalize_year(value) -> int | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        year = int(float(s))
    except ValueError:
        return None
    if 1800 <= year <= 2200:
        return year
    return None


def build_key(year, month) -> str | None:
    year_val = normalize_year(year)
    month_val = normalize_month(month)
    if not year_val or not month_val:
        return None
    return f"{year_val:04d}-{month_val:02d}"


def extract_cell_text(cell) -> str:
    parts = []
    for p in cell.findall(".//text:p", NS):
        text = "".join(p.itertext())
        if text:
            parts.append(text)
    return " ".join(parts).strip()


def read_ods_rows(path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"ODS not found: {path}")
    with zipfile.ZipFile(path) as zf:
        with zf.open("content.xml") as handle:
            tree = ET.parse(handle)
    root = tree.getroot()
    table = root.find(".//table:table", NS)
    if table is None:
        raise RuntimeError("No table found in ODS content.xml")

    rows = []
    for row in table.findall("table:table-row", NS):
        row_repeat = int(
            row.get(f"{{{NS['table']}}}number-rows-repeated", "1")
        )
        row_cells = []
        for cell in row.findall("table:table-cell", NS):
            repeat = int(
                cell.get(f"{{{NS['table']}}}number-columns-repeated", "1")
            )
            value = extract_cell_text(cell)
            row_cells.extend([value] * repeat)
        if any(cell.strip() for cell in row_cells):
            for _ in range(row_repeat):
                rows.append(row_cells[:])
    return rows


def build_headers(header_row, width: int):
    headers = []
    for idx in range(width):
        raw = header_row[idx].strip() if idx < len(header_row) else ""
        base = raw if raw else f"Col{chr(65 + idx)}"
        name = base
        suffix = 2
        while name in headers:
            name = f"{base}_{suffix}"
            suffix += 1
        headers.append(name)
    return headers


def parse_ods(path: str):
    rows = read_ods_rows(path)
    if not rows:
        raise RuntimeError("ODS has no rows")
    width = max(len(r) for r in rows)
    headers = build_headers(rows[0], width)
    data_rows = []
    for raw in rows[1:]:
        padded = raw + [""] * (width - len(raw))
        row = {headers[i]: padded[i] for i in range(width)}
        data_rows.append(row)
    return headers, data_rows


def resolve_category_id(
    session: requests.Session,
    api_base: str,
    category_slug: str,
    fallback_id: int | None,
):
    slug_params = {"slug": category_slug, "per_page": 100}
    resp = session.get(f"{api_base}/categories", params=slug_params, timeout=30)
    if resp.ok:
        cats = read_json_response(resp, "Categories (slug)")
        if cats:
            return cats[0].get("id")

    search_params = {"search": category_slug, "per_page": 100}
    resp = session.get(
        f"{api_base}/categories", params=search_params, timeout=30
    )
    if resp.ok:
        cats = read_json_response(resp, "Categories (search)")
        for cat in cats:
            if cat.get("slug") == category_slug:
                return cat.get("id")
        if cats:
            return cats[0].get("id")

    return fallback_id


def fetch_posts(session: requests.Session, api_base: str, category_id: int, status: str):
    posts = []
    page = 1
    per_page = 100
    total_pages = 1

    while page <= total_pages:
        params = {
            "categories": category_id,
            "per_page": per_page,
            "page": page,
            "status": status,
            "_fields": "id,title,date,link,author,_embedded",
            "_embed": "author",
        }
        resp = session.get(f"{api_base}/posts", params=params, timeout=45)
        resp.raise_for_status()
        total_pages = int(resp.headers.get("X-WP-TotalPages", "1"))
        page_posts = read_json_response(resp, "Posts list")
        if not page_posts:
            break
        posts.extend(page_posts)
        page += 1

    return posts


def post_author_name(post) -> str:
    embedded = post.get("_embedded") or {}
    authors = embedded.get("author") or []
    if authors and isinstance(authors, list):
        name = authors[0].get("name")
        return name or ""
    return ""


def post_date_key(date_str: str) -> str | None:
    if not date_str:
        return None
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    return f"{dt.year:04d}-{dt.month:02d}"


def links_match(post_link: str, issue_link: str) -> bool:
    if not post_link or not issue_link:
        return False
    return post_link in issue_link or issue_link in post_link


def match_posts_to_issues(posts, issue_rows, issue_link_key: str):
    matches = []
    unmatched_posts = []
    unmatched_issues = []

    posts_by_key = {}
    for post in posts:
        key = post_date_key(post.get("date", ""))
        posts_by_key.setdefault(key, []).append(post)

    issues_by_key = {}
    for issue in issue_rows:
        key = build_key(issue.get("year"), issue.get("month"))
        issues_by_key.setdefault(key, []).append(issue)

    all_keys = set(posts_by_key) | set(issues_by_key)
    for key in sorted(all_keys):
        key_posts = posts_by_key.get(key, [])
        key_issues = issues_by_key.get(key, [])
        if not key_posts:
            unmatched_issues.extend(key_issues)
            continue
        if not key_issues:
            unmatched_posts.extend(key_posts)
            continue

        remaining_issues = key_issues[:]
        for post in key_posts:
            post_link = post.get("link", "")
            match_idx = None
            for idx, issue in enumerate(remaining_issues):
                if links_match(post_link, issue.get(issue_link_key, "")):
                    match_idx = idx
                    break
            if match_idx is None:
                unmatched_posts.append(post)
            else:
                matches.append((post, remaining_issues.pop(match_idx)))
        if remaining_issues:
            unmatched_issues.extend(remaining_issues)

    return matches, unmatched_posts, unmatched_issues


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Match education-reporter WordPress posts to edreporter.ods."
    )
    parser.add_argument(
        "--ods-path",
        default="edreporter.ods",
        help="Path to edreporter.ods (default: edreporter.ods).",
    )
    parser.add_argument(
        "--category-slug",
        default="education-reporter",
        help="WordPress category slug to filter (default: education-reporter).",
    )
    parser.add_argument(
        "--status",
        default="publish",
        help="Post status to query (default: publish).",
    )
    parser.add_argument(
        "--matched-output",
        default="education_reporter_matched.csv",
        help="Output CSV path for matched rows.",
    )
    parser.add_argument(
        "--unmatched-output",
        default="education_reporter_unmatched.csv",
        help="Output CSV path for unmatched rows.",
    )
    args = parser.parse_args()

    wp_base = os.getenv("WP_BASE", "").rstrip("/")
    username = os.getenv("WP_USERNAME", "")
    app_password = os.getenv("WP_APP_PASSWORD", "")
    fallback_category_id = os.getenv("WP_CATEGORY_ID", "").strip()
    fallback_category_id = int(fallback_category_id) if fallback_category_id else None

    if not wp_base or not username or not app_password:
        print(
            "Missing WP_BASE, WP_USERNAME, or WP_APP_PASSWORD in environment.",
            file=sys.stderr,
        )
        return 1

    api_base = f"{wp_base}/wp-json/wp/v2"
    session = build_session(username, app_password)
    category_id = resolve_category_id(
        session, api_base, args.category_slug, fallback_category_id
    )
    if not category_id:
        print(
            f"Could not resolve category '{args.category_slug}'.",
            file=sys.stderr,
        )
        return 1

    posts = fetch_posts(session, api_base, category_id, args.status)

    ods_headers, ods_rows = parse_ods(args.ods_path)
    if len(ods_headers) < 9:
        print(
            "ODS appears to have fewer than 9 columns; expected link in column I.",
            file=sys.stderr,
        )
    issue_rows = []
    for row in ods_rows:
        issue_rows.append(
            {
                "year": row.get(ods_headers[0], ""),
                "month": row.get(ods_headers[1], ""),
                "link": row.get(ods_headers[8], ""),
                "row": row,
            }
        )

    matches, unmatched_posts, unmatched_issues = match_posts_to_issues(
        posts, issue_rows, "link"
    )

    ods_prefixed_headers = [f"ods_{h}" for h in ods_headers]
    matched_fields = [
        "wp_title",
        "wp_date",
        "wp_permalink",
        "wp_author",
    ] + ods_prefixed_headers

    with open(args.matched_output, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=matched_fields)
        writer.writeheader()
        for post, issue in matches:
            row = {
                "wp_title": html.unescape(
                    (post.get("title") or {}).get("rendered", "")
                ).strip(),
                "wp_date": post.get("date", ""),
                "wp_permalink": post.get("link", ""),
                "wp_author": post_author_name(post),
            }
            ods_row = issue.get("row", {})
            for key in ods_headers:
                row[f"ods_{key}"] = ods_row.get(key, "")
            writer.writerow(row)

    unmatched_fields = ["unmatched_type"] + matched_fields
    with open(args.unmatched_output, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=unmatched_fields)
        writer.writeheader()
        for post in unmatched_posts:
            writer.writerow(
                {
                    "unmatched_type": "post",
                    "wp_title": html.unescape(
                        (post.get("title") or {}).get("rendered", "")
                    ).strip(),
                    "wp_date": post.get("date", ""),
                    "wp_permalink": post.get("link", ""),
                    "wp_author": post_author_name(post),
                }
            )
        for issue in unmatched_issues:
            ods_row = issue.get("row", {})
            row = {
                "unmatched_type": "issue",
                "wp_title": "",
                "wp_date": "",
                "wp_permalink": "",
                "wp_author": "",
            }
            for key in ods_headers:
                row[f"ods_{key}"] = ods_row.get(key, "")
            writer.writerow(row)

    print(f"Wrote {len(matches)} matched rows to {args.matched_output}")
    print(
        f"Wrote {len(unmatched_posts) + len(unmatched_issues)} unmatched rows "
        f"to {args.unmatched_output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
