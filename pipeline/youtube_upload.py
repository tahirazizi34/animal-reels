import os
import json
import time
import httpx
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from database import StepTimer, log_step, update_video

SCOPES       = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL     = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL    = "https://oauth2.googleapis.com/token"
UPLOAD_URL   = "https://www.googleapis.com/upload/youtube/v3/videos"
REDIRECT_URI = "http://localhost:8080"
TOKEN_FILE   = "youtube_token.json"
SECRETS_FILE = "client_secrets.json"

DEFAULT_CATEGORY = "15"
DEFAULT_PRIVACY  = "public"
DEFAULT_TAGS     = [
    "animals", "animal facts", "did you know",
    "wildlife", "nature", "shorts", "animalreels"
]

# In-memory token cache — survives within a single process lifetime
_token_cache = {}


def _load_secrets() -> dict:
    env_val = os.environ.get("GOOGLE_CLIENT_SECRETS", "").strip()
    print(f"  [DEBUG] GOOGLE_CLIENT_SECRETS env var present: {bool(env_val)}")
    print(f"  [DEBUG] GOOGLE_CLIENT_SECRETS length: {len(env_val)}")

    if env_val:
        try:
            data   = json.loads(env_val)
            result = data.get("installed") or data.get("web") or data
            print(f"  [DEBUG] Parsed secrets keys: {list(result.keys())}")
            return result
        except json.JSONDecodeError as e:
            print(f"  [DEBUG] JSON parse error: {e}")

    if os.path.exists(SECRETS_FILE):
        print(f"  [DEBUG] Loading from file: {SECRETS_FILE}")
        with open(SECRETS_FILE) as f:
            data = json.load(f)
        return data.get("installed") or data.get("web")

    raise FileNotFoundError("No YouTube credentials found.")


def _load_token() -> dict | None:
    global _token_cache

    # 1. Use in-memory cache if available and not expired
    if _token_cache and time.time() < _token_cache.get("expires_at", 0) - 60:
        print(f"  [DEBUG] Using cached token (expires in {int(_token_cache['expires_at'] - time.time())}s)")
        return _token_cache

    # 2. Try YOUTUBE_REFRESH_TOKEN env var (most reliable for Railway)
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
    if refresh_token:
        print(f"  [DEBUG] YOUTUBE_REFRESH_TOKEN env var present: True")
        secrets = _load_secrets()
        token   = _exchange_refresh_token(secrets, refresh_token)
        _token_cache.update(token)
        return token

    # 3. Try full YOUTUBE_TOKEN env var
    env_val = os.environ.get("YOUTUBE_TOKEN", "").strip()
    print(f"  [DEBUG] YOUTUBE_TOKEN env var present: {bool(env_val)}")
    if env_val:
        try:
            token = json.loads(env_val)
            _token_cache.update(token)
            return token
        except json.JSONDecodeError as e:
            print(f"  [DEBUG] YOUTUBE_TOKEN parse error: {e}")

    # 4. Fall back to local file
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            token = json.load(f)
        _token_cache.update(token)
        return token

    return None


def _exchange_refresh_token(secrets: dict, refresh_token: str) -> dict:
    """Exchange refresh token for a new access token."""
    print(f"  Refreshing access token using refresh token...")
    response = httpx.post(TOKEN_URL, data={
        "client_id":     secrets["client_id"],
        "client_secret": secrets["client_secret"],
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    })
    response.raise_for_status()
    data = response.json()
    return {
        "access_token":  data["access_token"],
        "refresh_token": refresh_token,  # Refresh token doesn't change
        "expires_at":    time.time() + data.get("expires_in", 3600),
    }


def _save_token(token: dict):
    global _token_cache
    _token_cache.update(token)
    # Save to file for local development
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)
    print(f"  ✓ Token saved to {TOKEN_FILE}")


def _refresh_token(secrets: dict, token: dict) -> dict:
    refresh_tok = token.get("refresh_token") or os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    if not refresh_tok:
        raise RuntimeError("No refresh token available — please re-authorize")
    new_token = _exchange_refresh_token(secrets, refresh_tok)
    _save_token(new_token)
    return new_token


class _OAuthHandler(BaseHTTPRequestHandler):
    code = None
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _OAuthHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Auth complete! Return to the terminal.</h2>")
    def log_message(self, *args): pass


def _run_oauth_flow(secrets: dict) -> dict:
    print("\n  Opening browser for YouTube authorization...")
    params = {
        "client_id":     secrets["client_id"],
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",
    }
    auth_url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"  Auth URL: {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8080), _OAuthHandler)
    server.handle_request()
    code = _OAuthHandler.code

    if not code:
        raise RuntimeError("No authorization code received.")

    response = httpx.post(TOKEN_URL, data={
        "client_id":     secrets["client_id"],
        "client_secret": secrets["client_secret"],
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
        "grant_type":    "authorization_code",
    })
    response.raise_for_status()
    token = response.json()
    token["expires_at"] = time.time() + token.get("expires_in", 3600)
    return token


def get_access_token() -> str:
    global _token_cache
    secrets = _load_secrets()
    token   = _load_token()

    if not token:
        print("  No YouTube token — starting OAuth flow...")
        token = _run_oauth_flow(secrets)
        _save_token(token)
    elif time.time() > token.get("expires_at", 0) - 60:
        print("  Access token expired — refreshing automatically...")
        token = _refresh_token(secrets, token)
        _token_cache.update(token)

    return token["access_token"]


def set_thumbnail(youtube_id: str, thumbnail_path: str, access_token: str):
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        return
    with open(thumbnail_path, "rb") as f:
        thumb_data = f.read()
    response = httpx.post(
        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={youtube_id}&uploadType=media",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/png"},
        content=thumb_data, timeout=60,
    )
    if response.status_code == 200:
        print(f"  ✓ Custom thumbnail set")
    else:
        print(f"  ⚠ Thumbnail failed: {response.status_code}")


def upload_to_youtube(video_id, video_path, title, description=None,
                      tags=None, privacy=DEFAULT_PRIVACY,
                      thumbnail_path=None, category_id=DEFAULT_CATEGORY) -> str:
    with StepTimer(video_id, "posting", f"Uploading to YouTube: {title}"):

        access_token = get_access_token()

        if description is None:
            hashtags    = " ".join(f"#{t.replace(' ', '')}" for t in (tags or DEFAULT_TAGS)[:5])
            description = (
                f"{title}\n\n"
                f"Subscribe for daily animal facts you won't believe are real!\n\n"
                f"{hashtags} #AnimalReels #AnimalFacts #Shorts"
            )

        metadata = {
            "snippet": {
                "title":       title[:100],
                "description": description,
                "tags":        tags or DEFAULT_TAGS,
                "categoryId":  category_id,
            },
            "status": {
                "privacyStatus":           privacy,
                "selfDeclaredMadeForKids": False,
            }
        }

        file_size = os.path.getsize(video_path)
        print(f"  Uploading {file_size/(1024*1024):.1f}MB to YouTube...")

        for attempt in range(3):
            try:
                init_r = httpx.post(
                    f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
                    headers={
                        "Authorization":           f"Bearer {access_token}",
                        "Content-Type":            "application/json",
                        "X-Upload-Content-Type":   "video/mp4",
                        "X-Upload-Content-Length": str(file_size),
                    },
                    json=metadata, timeout=30,
                )
                if init_r.status_code == 429:
                    wait = 60 * (attempt + 1)
                    print(f"  ⚠ Rate limited — waiting {wait}s...")
                    time.sleep(wait)
                    continue
                init_r.raise_for_status()
                break
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429 and attempt < 2:
                    time.sleep(60 * (attempt + 1))
                else:
                    raise

        upload_url = init_r.headers["Location"]
        with open(video_path, "rb") as f:
            video_data = f.read()

        upload_r = httpx.put(
            upload_url,
            headers={
                "Authorization":  f"Bearer {access_token}",
                "Content-Type":   "video/mp4",
                "Content-Length": str(file_size),
            },
            content=video_data, timeout=300,
        )
        upload_r.raise_for_status()
        youtube_id = upload_r.json()["id"]

        print(f"  ✓ Uploaded! YouTube ID: {youtube_id}")
        print(f"  ✓ URL: https://www.youtube.com/watch?v={youtube_id}")

        if thumbnail_path:
            set_thumbnail(youtube_id, thumbnail_path, access_token)

        update_video(video_id, youtube_id=youtube_id, status="posted", posted_at="now()")

    return youtube_id


def setup_auth():
    print("Setting up YouTube authorization...\n")
    secrets = _load_secrets()
    token   = _run_oauth_flow(secrets)
    _save_token(token)

    print("\n✓ YouTube authorization complete!")
    print(f"\n── Add this to Railway Variables ─────────────────")
    print(f"YOUTUBE_REFRESH_TOKEN={token.get('refresh_token', 'NOT_FOUND')}")
    print(f"\nThis never expires and auto-refreshes access tokens!")
    print(f"──────────────────────────────────────────────────\n")


if __name__ == "__main__":
    import sys
    if "--auth-only" in sys.argv:
        setup_auth()
    else:
        print("Usage: python youtube_upload.py --auth-only")
