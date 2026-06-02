"""
video_clip_gen.py — Generates short AI video clips using fal.ai

Uses Kling 1.6 Pro for high quality animal video clips via async queue.
"""

import os
import time
import httpx
from database import StepTimer, log_step

FAL_API_KEY = os.getenv("FAL_API_KEY", "")

HEADERS = {
    "Authorization": f"Key {FAL_API_KEY}",
    "Content-Type":  "application/json",
}

MODEL = "fal-ai/kling-video/v1.6/pro/text-to-video"
QUEUE_URL = f"https://queue.fal.run/{MODEL}"


def generate_video_clip(scene: str, animal: str, scene_index: int, video_id: str) -> str:
    """
    Generate a single AI video clip from a scene description.
    Returns URL of the generated video.
    """
    print(f"  Submitting clip {scene_index + 1}: {scene[:60]}...")

    prompt = (
        f"{scene}. "
        f"Professional wildlife documentary, "
        f"cinematic camera movement, "
        f"National Geographic quality, "
        f"natural lighting, photorealistic, "
        f"smooth motion, family friendly"
    )

    for attempt in range(3):
        try:
            # Submit to async queue
            response = httpx.post(
                QUEUE_URL,
                headers=HEADERS,
                json={
                    "prompt":       prompt,
                    "duration":     "5",
                    "aspect_ratio": "9:16",
                    "cfg_scale":    0.5,
                },
                timeout=60,
            )

            if response.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  ⚠ Rate limited — waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            data = response.json()

            request_id = data.get("request_id")
            status_url  = data.get("status_url")
            response_url = data.get("response_url")

            if not request_id:
                raise ValueError(f"No request_id in response: {data}")

            print(f"  Queued (ID: {request_id[:16]}...) — waiting for result...")
            return _poll_result(request_id, status_url, response_url)

        except httpx.TimeoutException:
            if attempt < 2:
                print(f"  ⚠ Timeout — retrying in 10s...")
                time.sleep(10)
            else:
                raise
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            if attempt < 2:
                print(f"  ⚠ Connection error — retrying in 10s...")
                time.sleep(10)
            else:
                raise

    raise RuntimeError("Failed after 3 attempts")


def _poll_result(request_id: str, status_url: str = None, result_url: str = None, timeout: int = 600) -> str:
    """Poll fal.ai queue for result."""
    if not status_url:
        status_url = f"https://queue.fal.run/{MODEL}/requests/{request_id}/status"
    if not result_url:
        result_url = f"https://queue.fal.run/{MODEL}/requests/{request_id}"
    start = time.time()
    last_status = ""

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Timed out after {timeout}s")

        try:
            r = httpx.get(status_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            data   = r.json()
            status = data.get("status", "")

            if status != last_status:
                print(f"  Status: {status}")
                last_status = status

            if status == "COMPLETED":
                # Fetch result
                result_r = httpx.get(result_url, headers=HEADERS, timeout=30)
                result_r.raise_for_status()
                result = result_r.json()

                # Extract video URL - try multiple response formats
                if "video" in result and isinstance(result["video"], dict):
                    return result["video"]["url"]
                elif "video" in result and isinstance(result["video"], str):
                    return result["video"]
                elif "outputs" in result and result["outputs"]:
                    out = result["outputs"][0]
                    return out["url"] if isinstance(out, dict) else out
                elif "output" in result:
                    out = result["output"]
                    if isinstance(out, dict):
                        return out.get("url") or out.get("video_url")
                    return out
                else:
                    raise ValueError(f"No video URL in result: {list(result.keys())}")

            elif status == "FAILED":
                error = data.get("error", "unknown")
                raise RuntimeError(f"Generation failed: {error}")

            elif status in ("IN_QUEUE", "IN_PROGRESS"):
                time.sleep(8)

            else:
                time.sleep(8)

        except (httpx.ConnectError, httpx.TimeoutException):
            print(f"  ⚠ Network hiccup — retrying...")
            time.sleep(5)


def download_video_clip(url: str, output_path: str) -> str:
    """Download a video clip from URL to local disk."""
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    print(f"  Downloading clip...")
    response = httpx.get(url, follow_redirects=True, timeout=120)
    response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(response.content)

    size_mb = len(response.content) / (1024 * 1024)
    print(f"  ✓ Saved: {output_path} ({size_mb:.1f}MB)")
    return output_path


def pick_video_scenes(scene_descriptions: list, animal: str) -> list:
    """Pick which 2 scenes get video clips using Claude."""
    import anthropic
    from config import ANTHROPIC_API_KEY

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    scenes_text = "\n".join([f"{i+1}. {s}" for i, s in enumerate(scene_descriptions)])

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": (
                f"Pick the 2 most visually dynamic scenes for a {animal} video "
                f"that would look best as moving video clips.\n\n"
                f"Scenes:\n{scenes_text}\n\n"
                f"Respond with ONLY two numbers separated by a comma, e.g.: 1,3"
            )
        }]
    )

    response = message.content[0].text.strip()
    indices  = [int(x.strip()) - 1 for x in response.split(",")]
    return indices[:2]


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    print("Testing fal.ai video clip generation...\n")

    if not FAL_API_KEY:
        print("✗ FAL_API_KEY not set in .env"); exit(1)

    TEST_SCENES = [
        "Close-up of an axolotl face showing its signature smile and feathery pink gills",
        "An axolotl swimming gracefully underwater showcasing its full body",
        "Aerial view of Lake Xochimilco with floating gardens where wild axolotls live",
        "Detailed shot of axolotl external gills fanning out in the water",
        "Laboratory setting with an axolotl in a research tank soft lighting",
    ]

    print("Picking best scenes for video...")
    indices = pick_video_scenes(TEST_SCENES, "Axolotl")
    print(f"✓ Selected scenes: {[i+1 for i in indices]}\n")

    os.makedirs("test_clips", exist_ok=True)

    for i, scene_idx in enumerate(indices):
        scene = TEST_SCENES[scene_idx]
        print(f"Generating clip {i+1}/2...")
        try:
            url  = generate_video_clip(scene, "Axolotl", scene_idx, "test-id")
            path = download_video_clip(url, f"test_clips/clip_{i+1}.mp4")
            size = os.path.getsize(path) / (1024*1024)
            print(f"✓ Clip {i+1} ready! ({size:.1f}MB)\n")
        except Exception as e:
            print(f"✗ Clip {i+1} failed: {e}\n")

    print("✓ Open 'test_clips/' to watch your AI video clips!")
