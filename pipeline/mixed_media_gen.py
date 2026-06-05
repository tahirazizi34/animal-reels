"""
mixed_media_gen.py — Generates a mix of video clips and images for each video
"""

import os
import time
import shutil
import httpx
from video_clip_gen import generate_video_clip, download_video_clip, pick_video_scenes
from image_gen import _generate_single_image
from database import StepTimer


def _download_image(url: str, output_path: str) -> str:
    """Download a single image from URL to exact output path."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)
    size_kb = len(response.content) // 1024
    print(f"  ✓ Saved {os.path.basename(output_path)} ({size_kb}KB)")
    return output_path


def generate_mixed_media(video_id: str, scene_descriptions: list, animal: str) -> list:
    """
    Generate mix of video clips and images for all scenes.
    Returns list of (media_type, local_path) tuples in scene order.
    """
    with StepTimer(video_id, "media", f"Generating mixed media for {animal}"):

        # Pick which 2 scenes get video
        print(f"  Selecting best scenes for video clips...")
        try:
            video_indices = pick_video_scenes(scene_descriptions, animal)
            print(f"  ✓ Video scenes: {[i+1 for i in video_indices]}")
        except Exception as e:
            print(f"  ⚠ Scene selection failed ({e}) — using scenes 1 and 3")
            video_indices = [0, 2]

        image_dir = os.path.join("output", video_id, "images")
        clip_dir  = os.path.join("output", video_id, "clips")
        os.makedirs(image_dir, exist_ok=True)
        os.makedirs(clip_dir, exist_ok=True)

        media_paths      = []
        video_clip_count = 0
        image_count      = 0

        for i, scene in enumerate(scene_descriptions):
            scene_num = f"{i+1:02d}"

            if i in video_indices:
                # ── VIDEO CLIP ─────────────────────────
                print(f"\n  Scene {i+1}/{len(scene_descriptions)} → VIDEO CLIP")
                clip_path = os.path.join(clip_dir, f"scene_{scene_num}.mp4")

                try:
                    url  = generate_video_clip(scene, animal, i, video_id)
                    path = download_video_clip(url, clip_path)
                    media_paths.append(("video", path))
                    video_clip_count += 1
                    print(f"  ✓ Video clip ready")

                except Exception as e:
                    print(f"  ⚠ Video failed ({e}) — falling back to image")
                    image_path = os.path.join(image_dir, f"scene_{scene_num}.png")
                    try:
                        url  = _generate_single_image(scene, animal, i, video_id)
                        path = _download_image(url, image_path)
                        media_paths.append(("image", path))
                        image_count += 1
                    except Exception as e2:
                        raise RuntimeError(f"Both video and image failed for scene {i+1}: {e2}")

            else:
                # ── FLUX IMAGE ─────────────────────────
                print(f"\n  Scene {i+1}/{len(scene_descriptions)} → IMAGE")
                image_path = os.path.join(image_dir, f"scene_{scene_num}.png")

                try:
                    url  = _generate_single_image(scene, animal, i, video_id)
                    path = _download_image(url, image_path)
                    media_paths.append(("image", path))
                    image_count += 1
                    print(f"  ✓ Image ready")

                except Exception as e:
                    raise RuntimeError(f"Image failed for scene {i+1}: {e}")

            if i < len(scene_descriptions) - 1:
                time.sleep(3)

        print(f"\n  ✓ Media complete: {video_clip_count} video clips + {image_count} images")
        return media_paths
