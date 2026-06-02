"""
mixed_media_gen.py — Generates a mix of video clips and images for each video

- 2 scenes → AI video clips (most dramatic)
- 3 scenes → FLUX 1.1 Pro images (remaining)
- Returns list of local file paths in scene order
"""

import os
from video_clip_gen import generate_video_clip, download_video_clip, pick_video_scenes
from image_gen import _generate_single_image, download_images
from database import StepTimer


def generate_mixed_media(video_id: str, scene_descriptions: list, animal: str) -> list:
    """
    Generate mix of video clips and images for all scenes.
    Returns list of local file paths in scene order.
    """
    with StepTimer(video_id, "media", f"Generating mixed media for {animal}"):

        # Step 1: Claude picks which 2 scenes get video
        print(f"  Selecting best scenes for video clips...")
        try:
            video_indices = pick_video_scenes(scene_descriptions, animal)
            print(f"  ✓ Video scenes: {[i+1 for i in video_indices]}")
        except Exception as e:
            print(f"  ⚠ Scene selection failed ({e}) — using scenes 1 and 3")
            video_indices = [0, 2]

        # Step 2: Generate each scene
        media_paths = []
        video_clip_count = 0
        image_count = 0

        for i, scene in enumerate(scene_descriptions):
            if i in video_indices:
                # Generate video clip
                print(f"\n  Scene {i+1}/{len(scene_descriptions)} → VIDEO CLIP")
                try:
                    output_dir = os.path.join("output", video_id, "clips")
                    output_path = os.path.join(output_dir, f"scene_{i+1:02d}.mp4")
                    os.makedirs(output_dir, exist_ok=True)

                    url = generate_video_clip(scene, animal, i, video_id)
                    path = download_video_clip(url, output_path)
                    media_paths.append(("video", path))
                    video_clip_count += 1
                    print(f"  ✓ Video clip ready")

                except Exception as e:
                    # Fallback to image if video fails
                    print(f"  ⚠ Video failed ({e}) — falling back to image")
                    url = _generate_single_image(scene, animal, i, video_id)
                    image_dir = os.path.join("output", video_id, "images")
                    os.makedirs(image_dir, exist_ok=True)
                    local_paths = download_images([url], image_dir)
                    # Rename to correct scene number
                    import shutil
                    correct_path = os.path.join(image_dir, f"scene_{i+1:02d}.png")
                    shutil.move(local_paths[0], correct_path)
                    media_paths.append(("image", correct_path))
                    image_count += 1

            else:
                # Generate FLUX image
                print(f"\n  Scene {i+1}/{len(scene_descriptions)} → IMAGE")
                try:
                    url = _generate_single_image(scene, animal, i, video_id)
                    image_dir = os.path.join("output", video_id, "images")
                    os.makedirs(image_dir, exist_ok=True)
                    local_paths = download_images([url], image_dir)
                    import shutil
                    correct_path = os.path.join(image_dir, f"scene_{i+1:02d}.png")
                    shutil.move(local_paths[0], correct_path)
                    media_paths.append(("image", correct_path))
                    image_count += 1
                    print(f"  ✓ Image ready")

                except Exception as e:
                    print(f"  ⚠ Image failed: {e}")
                    raise

        print(f"\n  ✓ Media complete: {video_clip_count} video clips + {image_count} images")
        return media_paths
