import argparse
import csv
import html
import io
import os
import sys

import requests
from dotenv import load_dotenv


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


def chunked(seq, size: int):
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


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
            "_fields": "id,title,date,categories,link",
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


def fetch_category_map(session: requests.Session, api_base: str, category_ids):
    if not category_ids:
        return {}
    cat_map = {}
    for group in chunked(list(category_ids), 100):
        params = {
            "include": ",".join(str(cid) for cid in group),
            "per_page": 100,
            "_fields": "id,name",
        }
        resp = session.get(f"{api_base}/categories", params=params, timeout=30)
        resp.raise_for_status()
        for cat in read_json_response(resp, "Categories list"):
            cat_map[cat.get("id")] = cat.get("name", "")
    return cat_map


def build_csv(posts, category_id: int, cat_map) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "post_id",
            "title",
            "published_date",
            "permalink",
            "additional_category_ids",
            "additional_category_names",
        ]
    )
    for post in posts:
        other_cat_ids = [
            cid for cid in post.get("categories", []) if cid != category_id
        ]
        other_cat_names = [cat_map.get(cid, "") for cid in other_cat_ids]
        title = html.unescape((post.get("title") or {}).get("rendered", "")).strip()
        writer.writerow(
            [
                post.get("id", ""),
                title,
                post.get("date", ""),
                post.get("link", ""),
                ",".join(str(cid) for cid in other_cat_ids),
                ",".join(name for name in other_cat_names if name),
            ]
        )
    return output.getvalue()


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Export WordPress posts by category to CSV."
    )
    parser.add_argument(
        "--category-id",
        type=int,
        default=int(os.getenv("WP_CATEGORY_ID", "72")),
        help="WordPress category ID to filter posts (default: WP_CATEGORY_ID or 72).",
    )
    parser.add_argument(
        "--status",
        default="publish",
        help="Post status to query (default: publish).",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Output CSV path (default: wp_posts_category_<id>.csv).",
    )
    args = parser.parse_args()

    wp_base = os.getenv("WP_BASE", "").rstrip("/")
    username = os.getenv("WP_USERNAME", "")
    app_password = os.getenv("WP_APP_PASSWORD", "")

    if not wp_base or not username or not app_password:
        print(
            "Missing WP_BASE, WP_USERNAME, or WP_APP_PASSWORD in environment.",
            file=sys.stderr,
        )
        return 1

    api_base = f"{wp_base}/wp-json/wp/v2"
    session = build_session(username, app_password)

    posts = fetch_posts(session, api_base, args.category_id, args.status)
    other_cat_ids = {
        cid for p in posts for cid in p.get("categories", []) if cid != args.category_id
    }
    cat_map = fetch_category_map(session, api_base, other_cat_ids)

    csv_text = build_csv(posts, args.category_id, cat_map)
    output_path = args.output or f"wp_posts_category_{args.category_id}.csv"
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        f.write(csv_text)

    print(f"Wrote {len(posts)} posts to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
