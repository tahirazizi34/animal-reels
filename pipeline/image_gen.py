import os
import time
import httpx
from config import REPLICATE_API_TOKEN
from database import StepTimer, log_step

REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

# ── FLUX 1.1 Pro — much better quality than SDXL ──────
# ~$0.04/image vs ~$0.05/image, 6x faster, dramatically better quality
MODEL_VERSION = "black-forest-labs/flux-1.1-pro"
USE_OFFICIAL_MODEL = True  # Uses model name directly instead of version hash

STYLE_SUFFIX = (
    "professional wildlife photography, "
    "National Geographic quality, "
    "sharp focus, vivid colors, "
    "natural lighting, ultra detailed, "
    "8k resolution, photorealistic, "
    "family friendly, no text, no watermarks"
)

NEGATIVE_PROMPT = (
    "cartoon, anime, illustration, painting, drawing, "
    "ugly, blurry, low quality, watermark, text, logo, "
    "scary, dark, violent, disturbing, nsfw, nude, sexual"
)

HEADERS = {
    "Authorization": f"Token {REPLICATE_API_TOKEN}",
    "Content-Type":  "application/json",
}


def _start_prediction(prompt: str) -> str:
    """Submit image generation to FLUX 1.1 Pro."""
    for attempt in range(5):
        try:
            return _try_start_prediction(prompt)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                wait = 10 * (attempt + 1)
                print(f"  ⚠ Rate limited — waiting {wait}s before retry {attempt+1}/5...")
                time.sleep(wait)
            else:
                raise
        except (httpx.ConnectError, httpx.TimeoutException):
            if attempt < 4:
                print(f"  ⚠ Connection error — retrying in 5s...")
                time.sleep(5)
            else:
                raise
    raise RuntimeError("Failed after 5 attempts due to rate limiting")


def _try_start_prediction(prompt: str) -> str:
    full_prompt = f"{prompt}, {STYLE_SUFFIX}"

    # FLUX 1.1 Pro uses a different API endpoint format
    response = httpx.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro/predictions",
        headers=HEADERS,
        json={
            "input": {
                "prompt":            full_prompt,
                "aspect_ratio":      "9:16",
                "output_format":     "png",
                "output_quality":    100,
                "safety_tolerance":  2,
                "prompt_upsampling": True,
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]


def _start_prediction_safe(animal: str) -> str:
    """Fallback safe prompt if content is flagged."""
    safe_prompt = (
        f"cute {animal} in natural habitat, bright daylight, "
        f"children's nature documentary style, wholesome, "
        f"ultra detailed, photorealistic, no text"
    )
    response = httpx.post(
        "https://api.replicate.com/v1/models/black-forest-labs/flux-1.1-pro/predictions",
        headers=HEADERS,
        json={
            "input": {
                "prompt":           safe_prompt,
                "aspect_ratio":     "9:16",
                "output_format":    "png",
                "output_quality":   100,
                "safety_tolerance": 2,
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]


def _poll_prediction(prediction_id: str, timeout: int = 300) -> str:
    url   = f"{REPLICATE_API_URL}/{prediction_id}"
    start = time.time()

    while True:
        if time.time() - start > timeout:
            raise TimeoutError(f"Prediction timed out after {timeout}s")

        try:
            response = httpx.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            print(f"  ⚠ Network hiccup — retrying in 5s...")
            time.sleep(5)
            continue

        data   = response.json()
        status = data["status"]

        if status == "succeeded":
            output = data.get("output")
            if isinstance(output, list) and output:
                return output[0]
            elif isinstance(output, str):
                return output
            raise ValueError("Prediction succeeded but no output URL")

        elif status == "failed":
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Prediction failed: {error}")

        elif status in ("starting", "processing"):
            time.sleep(3)

        else:
            raise RuntimeError(f"Unexpected status: {status}")


def _generate_single_image(scene: str, animal: str, scene_index: int, video_id: str) -> str:
    """Generate one image with automatic retry on content flags."""
    try:
        pred_id = _start_prediction(scene)
        return _poll_prediction(pred_id)
    except RuntimeError as e:
        if "NSFW" in str(e) or "safety" in str(e).lower():
            print(f"  ⚠ Content flagged on scene {scene_index + 1} — retrying with safe prompt...")
            time.sleep(2)
            pred_id = _start_prediction_safe(animal)
            return _poll_prediction(pred_id)
        raise


def generate_images(video_id: str, scene_descriptions: list, animal: str) -> list:
    image_urls = []

    with StepTimer(video_id, "images", f"Generating {len(scene_descriptions)} images with FLUX 1.1 Pro"):
        for i, scene in enumerate(scene_descriptions):
            print(f"  Generating image {i + 1}/{len(scene_descriptions)}: {scene[:60]}...")
            url = _generate_single_image(scene, animal, i, video_id)
            image_urls.append(url)
            print(f"  ✓ Image {i + 1} ready")
            if i < len(scene_descriptions) - 1:
                time.sleep(5)  # avoid rate limits

        print(f"  ✓ All {len(scene_descriptions)} images generated")

    return image_urls


def download_images(image_urls: list, output_dir: str) -> list:
    os.makedirs(output_dir, exist_ok=True)
    local_paths = []

    for i, url in enumerate(image_urls):
        local_path = os.path.join(output_dir, f"scene_{i + 1:02d}.png")
        print(f"  Downloading image {i + 1}...")
        response = httpx.get(url, follow_redirects=True, timeout=60)
        response.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(response.content)
        local_paths.append(local_path)
        print(f"  ✓ Saved scene_{i + 1:02d}.png ({len(response.content) // 1024}KB)")

    return local_paths


if __name__ == "__main__":
    print("Testing FLUX 1.1 Pro image generation...\n")
    print("Model: FLUX 1.1 Pro (upgrade from SDXL)")
    print("Expected: sharper, more photorealistic, more vibrant\n")

    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"
    TEST_SCENES = [
        "Close-up of an axolotl's face showing its signature smile and feathery pink gills against a dark aquarium background",
        "An axolotl swimming gracefully underwater, showcasing its full body with tiny legs and flowing tail fin",
        "Aerial view of Lake Xochimilco in Mexico City with floating gardens and canals where wild axolotls live",
        "Detailed shot of an axolotl's external gills fanning out in the water, showing the delicate feathery structures",
        "Laboratory setting with an axolotl in a research tank, soft lighting highlighting its translucent skin",
    ]

    import database
    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    database.StepTimer = FakeTimer
    database.log_step  = lambda *a, **kw: None

    print("Generating 5 images (takes ~1-2 minutes)...\n")
    urls  = generate_images(TEST_VIDEO_ID, TEST_SCENES, "Axolotl")
    paths = download_images(urls, "test_images_flux")

    print(f"\n── Results ───────────────────────────────")
    for p in paths:
        print(f"  {p}  ({os.path.getsize(p) // 1024}KB)")

    print(f"\n✓ Open 'test_images_flux/' and compare with 'test_images/'")
    print(f"  FLUX should look significantly more photorealistic!")
