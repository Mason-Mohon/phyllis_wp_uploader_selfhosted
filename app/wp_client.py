\
import os, requests, csv, html, io
from dotenv import load_dotenv
load_dotenv()

WP_BASE = os.getenv("WP_BASE","").rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_AUTHOR_NAME = os.getenv("WP_AUTHOR_NAME","").strip()
WP_CATEGORY_ID = os.getenv("WP_CATEGORY_ID", "72")  # Default to hardcoded ID
WP_CATEGORY_NAME = os.getenv("WP_CATEGORY_NAME", "Phyllis Schlafly Report Column")  # Default to hardcoded name
WP_CATEGORY_SLUG = os.getenv("WP_CATEGORY_SLUG", "phyllis-schlafly-report-column")  # Default to hardcoded slug

API = f"{WP_BASE}/wp-json/wp/v2"
session = requests.Session()
session.auth = (WP_USERNAME, WP_APP_PASSWORD)

# Add headers to bypass Cloudflare bot protection
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
})

# Debug: Print authentication info
print(f"DEBUG WP - WP_BASE: '{WP_BASE}'")
print(f"DEBUG WP - WP_USERNAME: '{WP_USERNAME}'")
print(f"DEBUG WP - WP_APP_PASSWORD: {'*' * len(WP_APP_PASSWORD) if WP_APP_PASSWORD else 'EMPTY'}")
print(f"DEBUG WP - API URL: '{API}'")
print(f"DEBUG WP - Category ID: '{WP_CATEGORY_ID}'")
print(f"DEBUG WP - Category Name: '{WP_CATEGORY_NAME}'")
print(f"DEBUG WP - Category Slug: '{WP_CATEGORY_SLUG}'")

def resolve_author_id():
    if not WP_AUTHOR_NAME: return None
    try:
        print(f"DEBUG WP - Searching for author: '{WP_AUTHOR_NAME}'")
        r = session.get(f"{API}/users", params={"search": WP_AUTHOR_NAME, "per_page": 100}, timeout=30)
        print(f"DEBUG WP - Author search response status: {r.status_code}")
        if r.status_code == 403: 
            print("DEBUG WP - Author search forbidden (403)")
            return None
        if r.status_code == 200:
            try:
                users = r.json()
                print(f"DEBUG WP - Found {len(users)} users")
                for u in users:
                    print(f"DEBUG WP - Checking user: name='{u.get('name')}', slug='{u.get('slug')}', username='{u.get('username')}'")
                    if (u.get("name")==WP_AUTHOR_NAME or 
                        u.get("slug")==WP_AUTHOR_NAME.lower().replace(' ', '-') or 
                        u.get("username")==WP_AUTHOR_NAME or
                        u.get("username")=="phyllis-wp"):  # Explicit check for phyllis-wp
                        print(f"DEBUG WP - Found matching author ID: {u.get('id')}")
                        return u.get("id")
            except ValueError as e:
                print(f"DEBUG WP - Failed to parse author JSON: {e}")
        return None
    except Exception as e:
        print(f"DEBUG WP - Exception in resolve_author_id: {e}")
        return None

def ensure_category_id():
    """Returns the hardcoded category ID instead of searching for it."""
    try:
        category_id = int(WP_CATEGORY_ID)
        print(f"DEBUG WP - Using hardcoded category: ID={category_id}, Name='{WP_CATEGORY_NAME}', Slug='{WP_CATEGORY_SLUG}'")
        return category_id
    except (ValueError, TypeError) as e:
        print(f"DEBUG WP - Invalid category ID '{WP_CATEGORY_ID}': {e}")
        return None

def create_post(title: str, content: str, date_iso: str, status: str="publish"):
    payload = {"title": title, "content": content, "status": status, "date": date_iso}
    cat_id = ensure_category_id()
    if cat_id: payload["categories"] = [cat_id]

    featured_id = os.getenv("WP_FEATURED_IMAGE_ID")
    if featured_id: 
        try:
            payload["featured_media"] = int(featured_id)
        except ValueError:
            pass

    author_id = resolve_author_id()
    tried_author = False
    if author_id:
        payload["author"] = author_id
        tried_author = True

    print(f"DEBUG WP - Posting to: {API}/posts")
    print(f"DEBUG WP - Payload: {payload}")
    print(f"DEBUG WP - Auth: {session.auth}")
    r = session.post(f"{API}/posts", json=payload, timeout=45)
    print(f"DEBUG WP - Response status: {r.status_code}")
    print(f"DEBUG WP - Response text: {r.text[:500]}")
    if r.status_code == 403 and tried_author:
        payload.pop("author", None)
        r = session.post(f"{API}/posts", json=payload, timeout=45)
        author_set = False
    else:
        r.raise_for_status()
        author_set = bool(author_id and r.status_code in (200,201))

    data = r.json()
    return {"id": data.get("id"), "URL": data.get("link"), "author_set": author_set}

def _chunked(seq, size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]

def _get_posts_page(category_id: int, page: int, per_page: int, status: str):
    params = {
        "categories": category_id,
        "per_page": per_page,
        "page": page,
        "status": status,
        "_fields": "id,title,date,categories,link",
    }
    r = session.get(f"{API}/posts", params=params, timeout=45)
    r.raise_for_status()
    total_pages = int(r.headers.get("X-WP-TotalPages", "1"))
    return r.json(), total_pages

def fetch_posts_by_category(category_id: int, status: str="publish"):
    posts = []
    page = 1
    per_page = 100
    total_pages = 1
    while page <= total_pages:
        page_posts, total_pages = _get_posts_page(category_id, page, per_page, status)
        if not page_posts:
            break
        posts.extend(page_posts)
        page += 1
    return posts

def fetch_category_map(category_ids):
    if not category_ids:
        return {}
    cat_map = {}
    for chunk in _chunked(list(category_ids), 100):
        params = {
            "include": ",".join(str(cid) for cid in chunk),
            "per_page": 100,
            "_fields": "id,name",
        }
        r = session.get(f"{API}/categories", params=params, timeout=30)
        r.raise_for_status()
        for c in r.json():
            cat_map[c.get("id")] = c.get("name", "")
    return cat_map

def export_posts_csv(category_id: int, status: str="publish") -> str:
    posts = fetch_posts_by_category(category_id, status=status)
    all_other_cat_ids = {
        cid for p in posts for cid in p.get("categories", []) if cid != category_id
    }
    cat_map = fetch_category_map(all_other_cat_ids)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "post_id",
        "title",
        "published_date",
        "additional_category_ids",
        "additional_category_names",
    ])
    for p in posts:
        cat_ids = [cid for cid in p.get("categories", []) if cid != category_id]
        cat_names = [cat_map.get(cid, "") for cid in cat_ids]
        title = html.unescape((p.get("title") or {}).get("rendered", "")).strip()
        writer.writerow([
            p.get("id", ""),
            title,
            p.get("date", ""),
            ",".join(str(cid) for cid in cat_ids),
            ",".join(name for name in cat_names if name),
        ])
    return output.getvalue()
