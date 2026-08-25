"""
dashboard_server.py — Private dashboard backend

Serves the dashboard UI and proxies Supabase data securely.
Protected by DASHBOARD_SECRET password.
"""

import os
import json
import httpx
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

SUPABASE_URL              = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
DASHBOARD_SECRET          = os.getenv("DASHBOARD_SECRET", "changeme")
PORT                      = int(os.getenv("PORT", "8080"))

SUPABASE_HEADERS = {
    "apikey":        SUPABASE_SERVICE_ROLE_KEY or "",
    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY or ''}",
    "Content-Type":  "application/json",
}


def supabase_get(table: str, params: dict = {}) -> list:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=SUPABASE_HEADERS,
        params=params,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def supabase_patch(table: str, match: dict, data: dict):
    params = {k: f"eq.{v}" for k, v in match.items()}
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**SUPABASE_HEADERS, "Prefer": "return=representation"},
        params=params,
        json=data,
        timeout=10,
    )
    r.raise_for_status()


class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        print(f"[Dashboard] {format % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status=200):
        body = html.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def is_authenticated(self) -> bool:
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {DASHBOARD_SECRET}":
            return True
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token  = params.get("token", [None])[0]
        return token == DASHBOARD_SECRET

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        # Serve dashboard UI
        if path in ("/", "/dashboard"):
            html_file = Path(__file__).parent / "dashboard.html"
            if html_file.exists():
                self.send_html(html_file.read_text(encoding="utf-8"))
            else:
                self.send_html("<h1>dashboard.html not found</h1>", 404)
            return

        # Health check (no auth needed)
        if path == "/health":
            self.send_json({"status": "ok"})
            return

        # API endpoints require auth
        if not self.is_authenticated():
            self.send_json({"error": "Unauthorized"}, 401)
            return

        if path == "/api/stats":
            self._handle_stats()
        elif path == "/api/videos":
            self._handle_videos()
        elif path == "/api/logs":
            self._handle_logs()
        elif path == "/api/settings":
            self._handle_settings()
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self.is_authenticated():
            self.send_json({"error": "Unauthorized"}, 401)
            return

        path = urlparse(self.path).path

        if path == "/api/approve":
            self._handle_approve()
        elif path == "/api/settings":
            self._handle_update_settings()
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _handle_stats(self):
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            all_videos   = supabase_get("videos", {"select": "status,created_at,channel"})
            today_videos = [v for v in all_videos if v.get("created_at", "").startswith(today)]
            stats = {
                "today":   len(today_videos),
                "posted":  len([v for v in today_videos if v["status"] == "posted"]),
                "pending": len([v for v in today_videos if v["status"] in ("ready", "pending", "generating")]),
                "failed":  len([v for v in today_videos if v["status"] == "failed"]),
                "total":   len(all_videos),
            }
            self.send_json(stats)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def _handle_videos(self):
        try:
            videos = supabase_get("videos", {
                "select": "*",
                "order":  "created_at.desc",
                "limit":  "30",
            })
            self.send_json(videos)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def _handle_logs(self):
        try:
            logs = supabase_get("pipeline_logs", {
                "select": "*",
                "order":  "created_at.desc",
                "limit":  "100",
            })
            self.send_json(logs)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def _handle_settings(self):
        try:
            settings = supabase_get("settings")
            self.send_json({s["key"]: s["value"] for s in settings})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def _handle_approve(self):
        try:
            body     = self._read_body()
            video_id = body.get("video_id")
            if not video_id:
                self.send_json({"error": "video_id required"}, 400)
                return
            supabase_patch("videos", {"id": video_id}, {"status": "approved"})
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def _handle_update_settings(self):
        try:
            body = self._read_body()
            for key, value in body.items():
                supabase_patch("settings", {"key": key}, {"value": str(value)})
            self.send_json({"ok": True})
        except Exception as e:
            self.send_json({"error": str(e)}, 500)


if __name__ == "__main__":
    print(f"Animal Reels Dashboard — http://localhost:{PORT}")
    server = HTTPServer(("0.0.0.0", PORT), DashboardHandler)
    server.serve_forever()
