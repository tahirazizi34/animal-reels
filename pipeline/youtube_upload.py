import os
import json
import time
import httpx
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from database import StepTimer, log_step, update_video

# ── OAuth config ───────────────────────────────────────
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


def _load_secrets() -> dict:
    # Try env var first (Railway)
    env_val = os.environ.get("GOOGLE_CLIENT_SECRETS", "").strip()
    print(f"  [DEBUG] GOOGLE_CLIENT_SECRETS env var present: {bool(env_val)}")
    print(f"  [DEBUG] GOOGLE_CLIENT_SECRETS length: {len(env_val)}")

    if env_val:
        try:
            data = json.loads(env_val)
            result = data.get("installed") or data.get("web") or data
            print(f"  [DEBUG] Parsed secrets keys: {list(result.keys())}")
            return result
        except json.JSONDecodeError as e:
            print(f"  [DEBUG] JSON parse error: {e}")
            print(f"  [DEBUG] First 100 chars: {env_val[:100]}")

    # Fall back to local file
    if os.path.exists(SECRETS_FILE):
        print(f"  [DEBUG] Loading from file: {SECRETS_FILE}")
        with open(SECRETS_FILE) as f:
            data = json.load(f)
        return data.get("installed") or data.get("web")

    raise FileNotFoundError(
        f"No YouTube credentials found.\n"
        f"Either set GOOGLE_CLIENT_SECRETS env var or place {SECRETS_FILE} in pipeline/"
    )


def _load_token() -> dict | None:
    env_val = os.environ.get("YOUTUBE_TOKEN", "").strip()
    print(f"  [DEBUG] YOUTUBE_TOKEN env var present: {bool(env_val)}")

    if env_val:
        try:
            return json.loads(env_val)
        except json.JSONDecodeError as e:
            print(f"  [DEBUG] YOUTUBE_TOKEN parse error: {e}")

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)

    return None


def _save_token(token: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)
    print(f"  ✓ Token saved to {TOKEN_FILE}")


def _refresh_token(secrets: dict, token: dict) -> dict:
    response = httpx.post(TOKEN_URL, data={
        "client_id":     secrets["client_id"],
        "client_secret": secrets["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type":    "refresh_token",
    })
    response.raise_for_status()
    new_token = response.json()
    token["access_token"] = new_token["access_token"]
    token["expires_at"]   = time.time() + new_token.get("expires_in", 3600)
    _save_token(token)
    return token


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
    secrets = _load_secrets()
    token   = _load_token()

    if not token:
        print("  No YouTube token found — starting OAuth flow...")
        token = _run_oauth_flow(secrets)
        _save_token(token)
    elif time.time() > token.get("expires_at", 0) - 60:
        print("  Access token expired — refreshing...")
        token = _refresh_token(secrets, token)

    return token["access_token"]


def set_thumbnail(youtube_id: str, thumbnail_path: str, access_token: str):
    """Upload a custom thumbnail to YouTube."""
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        print("  ⚠ No thumbnail file found — skipping")
        return

    with open(thumbnail_path, "rb") as f:
        thumb_data = f.read()

    response = httpx.post(
        f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={youtube_id}&uploadType=media",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "image/png",
        },
        content=thumb_data,
        timeout=60,
    )

    if response.status_code == 200:
        print(f"  ✓ Custom thumbnail set")
    else:
        print(f"  ⚠ Thumbnail upload failed: {response.status_code} — {response.text[:100]}")


def upload_to_youtube(video_id, video_path, title, description=None, tags=None, privacy=DEFAULT_PRIVACY, thumbnail_path=None) -> str:
    with StepTimer(video_id, "posting", f"Uploading to YouTube: {title}"):

        access_token = get_access_token()

        if description is None:
            description = _build_description(title, tags or DEFAULT_TAGS)

        metadata = {
            "snippet": {
                "title":       title[:100],
                "description": description,
                "tags":        tags or DEFAULT_TAGS,
                "categoryId":  DEFAULT_CATEGORY,
            },
            "status": {
                "privacyStatus":           privacy,
                "selfDeclaredMadeForKids": False,
            }
        }

        file_size = os.path.getsize(video_path)
        print(f"  Uploading {file_size / (1024*1024):.1f}MB to YouTube...")

        youtube_id = _resumable_upload(access_token, metadata, video_path, file_size)

        print(f"  ✓ Uploaded! YouTube ID: {youtube_id}")
        print(f"  ✓ URL: https://www.youtube.com/watch?v={youtube_id}")

        # Set custom thumbnail
        if thumbnail_path:
            set_thumbnail(youtube_id, thumbnail_path, access_token)

        update_video(video_id, youtube_id=youtube_id, status="posted", posted_at="now()")

    return youtube_id


def _resumable_upload(access_token, metadata, video_path, file_size) -> str:
    init_response = httpx.post(
        f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={
            "Authorization":           f"Bearer {access_token}",
            "Content-Type":            "application/json",
            "X-Upload-Content-Type":   "video/mp4",
            "X-Upload-Content-Length": str(file_size),
        },
        json=metadata,
        timeout=30,
    )
    init_response.raise_for_status()
    upload_url = init_response.headers["Location"]

    with open(video_path, "rb") as f:
        video_data = f.read()

    upload_response = httpx.put(
        upload_url,
        headers={
            "Authorization":  f"Bearer {access_token}",
            "Content-Type":   "video/mp4",
            "Content-Length": str(file_size),
        },
        content=video_data,
        timeout=300,
    )
    upload_response.raise_for_status()
    return upload_response.json()["id"]


def _build_description(title, tags):
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
    return (
        f"{title}\n\n"
        f"Subscribe for daily animal facts you won't believe are real!\n\n"
        f"{hashtags} #AnimalReels #AnimalFacts #Shorts"
    )


def setup_auth():
    print("Setting up YouTube authorization...\n")
    get_access_token()
    print("\n✓ YouTube authorization complete!")


if __name__ == "__main__":
    import sys
    if "--auth-only" in sys.argv:
        setup_auth()
        exit(0)

    print("YouTube Uploader\n")
    print("  python youtube_upload.py --auth-only   ← authorize account")
    print("  python youtube_upload.py --upload      ← upload test video\n")

    if "--upload" not in sys.argv:
        exit(0)

    video_path = "test_output/axolotl_final.mp4"
    if not os.path.exists(video_path):
        print(f"✗ No video found at {video_path}")
        exit(1)

    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"

    import database
    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    database.StepTimer    = FakeTimer
    database.log_step     = lambda *a, **kw: None
    database.update_video = lambda *a, **kw: None

    yt_id = upload_to_youtube(
        video_id=TEST_VIDEO_ID,
        video_path=video_path,
        title="This Animal Can Regrow Its Brain #Shorts #AnimalFacts",
        privacy="public",
    )
    print(f"\n✓ https://www.youtube.com/watch?v={yt_id}")
