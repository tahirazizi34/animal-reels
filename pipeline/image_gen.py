import os
import time
import httpx
from config import REPLICATE_API_TOKEN
from database import StepTimer, log_step

REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
MODEL_VERSION     = "7762fd07cf82c948538e41f63f77d685e02b063e37e496e96eefd46c929f9bdc"

STYLE_SUFFIX = (
    "professional wildlife photography style, "
    "soft natural lighting, shallow depth of field, "
    "ultra detailed, 4k, beautiful, family friendly, "
    "no text, no watermarks"
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

# Fallback prompts if NSFW is triggered — safe, generic animal scenes
NSFW_FALLBACK_SUFFIX = (
    "cute and friendly, bright natural daylight, "
    "children's nature documentary style, wholesome, "
    "ultra detailed, 4k, no text, no watermarks"
)


def _start_prediction(prompt: str) -> str:
    for attempt in range(3):
        try:
            return _try_start_prediction(prompt)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if attempt < 2:
                print(f"  ⚠ Connection error ({e.__class__.__name__}) — retrying in 5s...")
                time.sleep(5)
            else:
                raise
    raise RuntimeError("Failed after 3 attempts")


def _try_start_prediction(prompt: str) -> str:
    response = httpx.post(
        REPLICATE_API_URL,
        headers=HEADERS,
        json={
            "version": MODEL_VERSION,
            "input": {
                "prompt":               f"{prompt}, {STYLE_SUFFIX}",
                "negative_prompt":      NEGATIVE_PROMPT,
                "width":                1080,
                "height":               1920,
                "num_outputs":          1,
                "scheduler":            "K_EULER",
                "num_inference_steps":  30,
                "guidance_scale":       7.5,
            }
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["id"]


def _start_prediction_safe(prompt: str, animal: str) -> str:
    """Fallback prompt — simpler and more conservative."""
    safe_prompt = f"{animal} in natural habitat, bright daylight, {NSFW_FALLBACK_SUFFIX}"
    response = httpx.post(
        REPLICATE_API_URL,
        headers=HEADERS,
        json={
            "version": MODEL_VERSION,
            "input": {
                "prompt":               safe_prompt,
                "negative_prompt":      NEGATIVE_PROMPT,
                "width":                1080,
                "height":               1920,
                "num_outputs":          1,
                "scheduler":            "K_EULER",
                "num_inference_steps":  30,
                "guidance_scale":       7.5,
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
            print(f"  ⚠ Network hiccup ({e.__class__.__name__}) — retrying in 5s...")
            time.sleep(5)
            continue

        data   = response.json()
        status = data["status"]

        if status == "succeeded":
            output = data.get("output", [])
            if output:
                return output[0]
            raise ValueError("Prediction succeeded but no output URL")

        elif status == "failed":
            error = data.get("error", "unknown error")
            raise RuntimeError(f"Prediction failed: {error}")

        elif status in ("starting", "processing"):
            time.sleep(3)

        else:
            raise RuntimeError(f"Unexpected status: {status}")


def _generate_single_image(scene: str, animal: str, scene_index: int, video_id: str) -> str:
    """Generate one image with automatic retry on NSFW false positives."""
    try:
        pred_id = _start_prediction(scene)
        return _poll_prediction(pred_id)

    except RuntimeError as e:
        if "NSFW" in str(e):
            print(f"  ⚠ NSFW false positive on scene {scene_index + 1} — retrying with safe prompt...")
            time.sleep(2)
            pred_id = _start_prediction_safe(scene, animal)
            return _poll_prediction(pred_id)
        raise


def generate_images(video_id: str, scene_descriptions: list, animal: str) -> list:
    image_urls = []

    with StepTimer(video_id, "images", f"Generating {len(scene_descriptions)} scene images"):
        for i, scene in enumerate(scene_descriptions):
            print(f"  Submitting image {i + 1}/{len(scene_descriptions)}: {scene[:60]}...")
            url = _generate_single_image(scene, animal, i, video_id)
            image_urls.append(url)
            print(f"  ✓ Image {i + 1} ready")
            if i < len(scene_descriptions) - 1:
                time.sleep(1)

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
    import glob
    print("Testing image generation...\n")

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

    urls  = generate_images(TEST_VIDEO_ID, TEST_SCENES, "Axolotl")
    paths = download_images(urls, "test_images")
    print(f"\n✓ {len(paths)} images saved to test_images/")
