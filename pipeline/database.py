import time
import httpx
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

# ── Supabase REST client (no supabase package needed) ──

def _headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


def _get(table: str, params: dict) -> list:
    r = httpx.get(_url(table), headers=_headers(), params=params)
    r.raise_for_status()
    return r.json()


def _post(table: str, data: dict) -> dict:
    r = httpx.post(_url(table), headers=_headers(), json=data)
    r.raise_for_status()
    result = r.json()
    return result[0] if isinstance(result, list) else result


def _patch(table: str, match: dict, data: dict):
    params = {k: f"eq.{v}" for k, v in match.items()}
    r = httpx.patch(_url(table), headers=_headers(), params=params, json=data)
    r.raise_for_status()


# ── Videos ────────────────────────────────────────────

def create_video(channel: str, title: str, script: str, animal: str) -> dict:
    return _post("videos", {
        "channel": channel,
        "title": title,
        "script": script,
        "animal": animal,
        "status": "pending",
    })


def update_video(video_id: str, **fields):
    _patch("videos", {"id": video_id}, fields)


def get_video(video_id: str) -> dict:
    results = _get("videos", {"id": f"eq.{video_id}", "limit": 1})
    return results[0] if results else None


def get_recent_animals(limit: int = 30) -> list:
    results = _get("videos", {
        "channel": "eq.animals",
        "select": "animal",
        "order": "created_at.desc",
        "limit": limit,
    })
    return [r["animal"] for r in results if r.get("animal")]


# ── Pipeline logs ──────────────────────────────────────

def log_step(video_id: str, step: str, status: str, message: str = "", duration_ms: int = None):
    _post("pipeline_logs", {
        "video_id": video_id,
        "step": step,
        "status": status,
        "message": message,
        "duration_ms": duration_ms,
    })


class StepTimer:
    def __init__(self, video_id: str, step: str, description: str = ""):
        self.video_id = video_id
        self.step = step
        self.description = description
        self.start = None

    def __enter__(self):
        self.start = time.time()
        log_step(self.video_id, self.step, "started", self.description)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = int((time.time() - self.start) * 1000)
        if exc_type:
            log_step(self.video_id, self.step, "failed", str(exc_val), duration_ms)
        else:
            log_step(self.video_id, self.step, "done", self.description, duration_ms)
        return False


# ── Settings ───────────────────────────────────────────

def get_setting(key: str, default: str = None) -> str:
    try:
        results = _get("settings", {"key": f"eq.{key}", "limit": 1})
        return results[0]["value"] if results else default
    except Exception:
        return default


def set_setting(key: str, value: str):
    _post("settings", {"key": key, "value": value})