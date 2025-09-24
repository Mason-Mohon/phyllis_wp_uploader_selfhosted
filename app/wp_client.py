\
import os, requests
from dotenv import load_dotenv
load_dotenv()

WP_BASE = os.getenv("WP_BASE","").rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME","")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD","")
WP_AUTHOR_NAME = os.getenv("WP_AUTHOR_NAME","").strip()
WP_CATEGORY_NAME = os.getenv("WP_CATEGORY_NAME","").strip()

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
    if not WP_CATEGORY_NAME: return None
    try:
        print(f"DEBUG WP - Searching for category: '{WP_CATEGORY_NAME}'")
        r = session.get(f"{API}/categories", params={"search": WP_CATEGORY_NAME, "per_page": 100}, timeout=30)
        print(f"DEBUG WP - Category search response status: {r.status_code}")
        print(f"DEBUG WP - Category search response text: {r.text[:500]}")
        print(f"DEBUG WP - Category search response headers: {dict(r.headers)}")
        
        if r.status_code in (200,201):
            if r.text.strip() == "":
                print("DEBUG WP - Empty response body for category search")
                return None
            try:
                categories = r.json()
                print(f"DEBUG WP - Found {len(categories)} categories")
                for c in categories:
                    print(f"DEBUG WP - Checking category: name='{c.get('name')}', id={c.get('id')}")
                    if c.get("name")==WP_CATEGORY_NAME: 
                        print(f"DEBUG WP - Found existing category ID: {c.get('id')}")
                        return c.get("id")
            except ValueError as e:
                print(f"DEBUG WP - Failed to parse category search JSON: {e}")
                print(f"DEBUG WP - Raw response: '{r.text}'")
                return None
        
        # Try getting all categories if search failed
        print(f"DEBUG WP - Search failed, trying to get all categories...")
        r_all = session.get(f"{API}/categories", params={"per_page": 100}, timeout=30)
        print(f"DEBUG WP - All categories response status: {r_all.status_code}")
        if r_all.status_code == 200 and r_all.text.strip():
            try:
                all_categories = r_all.json()
                print(f"DEBUG WP - Found {len(all_categories)} total categories")
                for c in all_categories:
                    print(f"DEBUG WP - Category: '{c.get('name')}' (ID: {c.get('id')})")
                    if c.get("name")==WP_CATEGORY_NAME: 
                        print(f"DEBUG WP - Found category in full list! ID: {c.get('id')}")
                        return c.get("id")
            except ValueError as e:
                print(f"DEBUG WP - Failed to parse all categories JSON: {e}")
        
        print(f"DEBUG WP - Creating new category: '{WP_CATEGORY_NAME}'")
        r2 = session.post(f"{API}/categories", json={"name": WP_CATEGORY_NAME}, timeout=30)
        print(f"DEBUG WP - Category creation response status: {r2.status_code}")
        print(f"DEBUG WP - Category creation response text: {r2.text[:200]}")
        
        if r2.status_code in (200,201): 
            try:
                return r2.json().get("id")
            except ValueError as e:
                print(f"DEBUG WP - Failed to parse category creation JSON: {e}")
                return None
        return None
    except Exception as e:
        print(f"DEBUG WP - Exception in ensure_category_id: {e}")
        return None

def create_post(title: str, content: str, date_iso: str, status: str="publish"):
    payload = {"title": title, "content": content, "status": status, "date": date_iso}
    cat_id = ensure_category_id()
    if cat_id: payload["categories"] = [cat_id]

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
