import os
import json
import time
import httpx
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from database import StepTimer, log_step, update_video

# ── OAuth config ───────────────────────────────────────
SCOPES          = "https://www.googleapis.com/auth/youtube.upload"
AUTH_URL        = "https://accounts.google.com/o/oauth2/auth"
TOKEN_URL       = "https://oauth2.googleapis.com/token"
UPLOAD_URL      = "https://www.googleapis.com/upload/youtube/v3/videos"
REDIRECT_URI    = "http://localhost:8080"
TOKEN_FILE      = "youtube_token.json"
SECRETS_FILE    = "client_secrets.json"

# ── Video metadata defaults ────────────────────────────
DEFAULT_CATEGORY = "15"          # Pets & Animals
DEFAULT_PRIVACY  = "public"      # public / private / unlisted
DEFAULT_TAGS     = [
    "animals", "animal facts", "did you know",
    "wildlife", "nature", "shorts", "animalreels"
]


# ── OAuth flow ─────────────────────────────────────────

def _load_secrets() -> dict:
    if not os.path.exists(SECRETS_FILE):
        raise FileNotFoundError(
            f"'{SECRETS_FILE}' not found in pipeline/ folder.\n"
            "Download it from Google Cloud Console → APIs & Services → Credentials."
        )
    with open(SECRETS_FILE) as f:
        data = json.load(f)
    return data.get("installed") or data.get("web")


def _load_token() -> dict | None:
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return None


def _save_token(token: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)
    print(f"  ✓ Token saved to {TOKEN_FILE}")


def _refresh_token(secrets: dict, token: dict) -> dict:
    """Refresh an expired access token using the refresh token."""
    response = httpx.post(TOKEN_URL, data={
        "client_id":     secrets["client_id"],
        "client_secret": secrets["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type":    "refresh_token",
    })
    response.raise_for_status()
    new_token = response.json()
    token["access_token"]  = new_token["access_token"]
    token["expires_at"]    = time.time() + new_token.get("expires_in", 3600)
    _save_token(token)
    return token


# Simple local server to catch the OAuth redirect
class _OAuthHandler(BaseHTTPRequestHandler):
    code = None
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _OAuthHandler.code = params.get("code", [None])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h2>Auth complete! You can close this tab and return to the terminal.</h2>")
    def log_message(self, *args): pass  # Silence request logs


def _run_oauth_flow(secrets: dict) -> dict:
    """Run the full OAuth flow and return a token dict."""
    print("\n  Opening browser for YouTube authorization...")
    print("  If it doesn't open, copy the URL printed below.\n")

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

    # Wait for redirect on localhost:8080
    server = HTTPServer(("localhost", 8080), _OAuthHandler)
    server.handle_request()
    code = _OAuthHandler.code

    if not code:
        raise RuntimeError("No authorization code received.")

    # Exchange code for tokens
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
    """
    Get a valid access token, running OAuth flow if needed.
    Tokens are cached in youtube_token.json and auto-refreshed.
    """
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


# ── Upload ─────────────────────────────────────────────

def upload_to_youtube(
    video_id:    str,
    video_path:  str,
    title:       str,
    description: str = None,
    tags:        list = None,
    privacy:     str = DEFAULT_PRIVACY,
) -> str:
    """
    Upload a video to YouTube.
    Returns the YouTube video ID (e.g. 'dQw4w9WgXcQ').
    """
    with StepTimer(video_id, "posting", f"Uploading to YouTube: {title}"):

        access_token = get_access_token()

        if description is None:
            description = _build_description(title, tags or DEFAULT_TAGS)

        metadata = {
            "snippet": {
                "title":       title[:100],   # YouTube max title length
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

        update_video(
            video_id,
            youtube_id=youtube_id,
            status="posted",
            posted_at="now()",
        )

    return youtube_id


def _resumable_upload(access_token: str, metadata: dict, video_path: str, file_size: int) -> str:
    """
    Use YouTube's resumable upload protocol for reliable large file uploads.
    """
    # Step 1: Initialize upload session
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

    # Step 2: Upload the file in one chunk
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
        timeout=300,   # 5 min timeout for upload
    )
    upload_response.raise_for_status()

    result = upload_response.json()
    return result["id"]


def _build_description(title: str, tags: list) -> str:
    hashtags = " ".join(f"#{t.replace(' ', '')}" for t in tags[:5])
    return (
        f"{title}\n\n"
        f"Subscribe for daily animal facts you won't believe are real!\n\n"
        f"{hashtags} #AnimalReels #AnimalFacts #Shorts"
    )


# ── Auth setup helper ──────────────────────────────────

def setup_auth():
    """Run this once to authorize your YouTube account."""
    print("Setting up YouTube authorization...\n")
    token = get_access_token()
    print("\n✓ YouTube authorization complete!")
    print(f"  Token saved to: {TOKEN_FILE}")
    print(f"  This token will auto-refresh — you won't need to do this again.\n")
    return token


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if "--auth-only" in sys.argv:
        setup_auth()
        exit(0)

    print("YouTube Uploader Test\n")
    print("Options:")
    print("  python youtube_upload.py --auth-only   ← authorize YouTube account")
    print("  python youtube_upload.py --upload      ← upload test video\n")

    if "--upload" not in sys.argv:
        print("Run with --auth-only first to authorize your YouTube account.")
        exit(0)

    video_path = "test_output/axolotl_final.mp4"
    if not os.path.exists(video_path):
        print(f"✗ No video found at {video_path}")
        print("  Run video_assembly.py first (Phase 5)")
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

    print(f"Uploading {video_path} to YouTube...\n")

    yt_id = upload_to_youtube(
        video_id=TEST_VIDEO_ID,
        video_path=video_path,
        title="This Animal Can Regrow Its Brain 🦎 #Shorts #AnimalFacts",
        privacy="public",   # public for testing — change to public when ready
    )

    print(f"\n── Result ────────────────────────────────────────")
    print(f"  YouTube ID : {yt_id}")
    print(f"  URL        : https://www.youtube.com/watch?v={yt_id}")
    print(f"\n✓ Check your YouTube Studio to see the uploaded video!")
