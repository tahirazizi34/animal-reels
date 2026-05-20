import os
import sys
import argparse
from config import validate, VIDEOS_PER_DAY, PIPELINE_MODE
from database import create_video, update_video, get_setting, log_step
from script_gen import generate_script
from image_gen import generate_images, download_images
from voice_gen import generate_voiceover
from video_assembly import assemble_video
from youtube_upload import upload_to_youtube


def run_pipeline(script_only=False, images_only=False, voice_only=False):
    print("═══════════════════════════════════════")
    print("  Animal Reels Pipeline")
    print("═══════════════════════════════════════\n")

    try:
        validate()
        print("✓ Environment validated\n")
    except EnvironmentError as e:
        print(f"✗ {e}")
        sys.exit(1)

    animals_enabled = get_setting("animals_enabled", "true")
    if animals_enabled != "true":
        print("Animals channel is disabled. Exiting.")
        return

    videos_today = int(get_setting("videos_per_day", str(VIDEOS_PER_DAY)))
    print(f"Generating {videos_today} video(s) today...\n")

    for i in range(videos_today):
        print(f"── Video {i + 1} of {videos_today} ──────────────────────")
        run_single_video(script_only=script_only, images_only=images_only, voice_only=voice_only)
        print()

    print("═══════════════════════════════════════")
    print("  Pipeline complete ✓")
    print("═══════════════════════════════════════")


def run_single_video(script_only=False, images_only=False, voice_only=False):
    video_id = None

    try:
        # ── Step 1: Create DB record ───────────────────
        print("Creating video record...")
        video = create_video(channel="animals", title="Generating...", script="", animal="")
        video_id = video["id"]
        print(f"✓ Video ID: {video_id}\n")

        # ── Step 2: Script ─────────────────────────────
        print("Step 2: Generating script...")
        script = generate_script(video_id)
        print(f"✓ Animal: {script['animal']}")
        print(f"✓ Title:  {script['title']}\n")
        if script_only:
            import json; print(json.dumps(script, indent=2)); return

        # ── Step 3: Images ─────────────────────────────
        print("Step 3: Generating images...")
        image_urls = generate_images(video_id, script["scene_descriptions"], script["animal"])
        image_dir = os.path.join("output", video_id, "images")
        local_images = download_images(image_urls, image_dir)
        print(f"✓ {len(local_images)} images saved\n")
        if images_only:
            print(f"Open '{image_dir}' to review."); return

        # ── Step 4: Voiceover ──────────────────────────
        print("Step 4: Generating voiceover...")
        audio_path = os.path.join("output", video_id, "voiceover.mp3")
        generate_voiceover(video_id, script["narration"], audio_path)
        print(f"✓ Voiceover saved\n")
        if voice_only:
            print(f"Open '{audio_path}' to listen."); return

        # ── Step 5: Assemble video ─────────────────────
        print("Step 5: Assembling video...")
        video_path = os.path.join("output", video_id, "final.mp4")
        assemble_video(
            video_id=video_id,
            image_paths=local_images,
            audio_path=audio_path,
            output_path=video_path,
            title=script["title"],
        )
        print(f"✓ Video ready\n")

        # ── Step 6: Post to YouTube ────────────────────
        mode = PIPELINE_MODE  # reads directly from .env

        if mode == "auto":
            print("Step 6: Posting to YouTube...")
            upload_to_youtube(
                video_id=video_id,
                video_path=video_path,
                title=script["title"],
                privacy="public",
            )
            print(f"✓ Posted to YouTube!\n")
        else:
            print("Step 6: Video is ready — awaiting your approval in dashboard.")
            print(f"  Run: python youtube_upload.py --upload to post manually.")
            update_video(video_id, status="ready")

    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        if video_id:
            update_video(video_id, status="failed", error_message=str(e))
            log_step(video_id, "pipeline", "failed", str(e))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Animal Reels Pipeline")
    parser.add_argument("--script-only",  action="store_true")
    parser.add_argument("--images-only",  action="store_true")
    parser.add_argument("--voice-only",   action="store_true")
    args = parser.parse_args()
    run_pipeline(
        script_only=args.script_only,
        images_only=args.images_only,
        voice_only=args.voice_only,
    )
