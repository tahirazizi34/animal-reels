import os
import sys
import argparse
from config import validate, VIDEOS_PER_DAY, PIPELINE_MODE
from database import create_video, update_video, get_setting, log_step
from script_gen import generate_script
from mixed_media_gen import generate_mixed_media
from voice_gen import generate_voiceover
from video_assembly import assemble_mixed_video
from youtube_upload import upload_to_youtube
from music_selector import download_music
from thumbnail_gen import generate_thumbnail
from alerts import send_failure_alert, send_daily_summary

# Set to True to use mixed media (video + images)
# Set to False to use images only (faster, cheaper)
USE_MIXED_MEDIA = os.getenv("USE_MIXED_MEDIA", "true").lower() == "true"


def run_pipeline(script_only=False, images_only=False, voice_only=False):
    print("═══════════════════════════════════════")
    print("  Animal Reels Pipeline")
    mode_label = "Mixed Media (Video + Images)" if USE_MIXED_MEDIA else "Images Only"
    print(f"  Mode: {mode_label}")
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

    posted   = []
    failures = 0

    for i in range(videos_today):
        print(f"── Video {i + 1} of {videos_today} ──────────────────────")
        result = run_single_video(script_only=script_only, images_only=images_only, voice_only=voice_only)
        if result:
            posted.append(result)
        else:
            failures += 1
        print()

    send_daily_summary(
        videos_generated=videos_today,
        videos_posted=len(posted),
        failures=failures,
        video_titles=posted,
    )

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

        # ── Step 3: Mixed media (video clips + images) ─
        print("Step 3: Generating media...")
        if USE_MIXED_MEDIA:
            media_paths = generate_mixed_media(
                video_id=video_id,
                scene_descriptions=script["scene_descriptions"],
                animal=script["animal"],
            )
        else:
            # Fallback to images only
            from image_gen import generate_images, download_images
            image_urls   = generate_images(video_id, script["scene_descriptions"], script["animal"])
            image_dir    = os.path.join("output", video_id, "images")
            local_images = download_images(image_urls, image_dir)
            media_paths  = [("image", p) for p in local_images]

        print(f"✓ {len(media_paths)} scenes ready\n")
        if images_only:
            print("--images-only flag set. Stopping here."); return

        # ── Step 4: Voiceover ──────────────────────────
        print("Step 4: Generating voiceover...")
        audio_path = os.path.join("output", video_id, "voiceover.mp3")
        generate_voiceover(video_id, script["narration"], audio_path)
        print(f"✓ Voiceover saved\n")
        if voice_only:
            print("--voice-only flag set. Stopping here."); return

        # ── Step 4b: Music ─────────────────────────────
        print("Step 4b: Selecting background music...")
        music_path = os.path.join("output", video_id, "music.mp3")
        download_music(script["animal"], music_path)
        print(f"✓ Music ready\n")

        # ── Step 5: Assemble video ─────────────────────
        print("Step 5: Assembling video...")
        video_path = os.path.join("output", video_id, "final.mp4")
        assemble_mixed_video(
            video_id=video_id,
            media_paths=media_paths,
            audio_path=audio_path,
            output_path=video_path,
            title=script["title"],
            music_path=music_path,
        )
        print(f"✓ Video ready\n")

        # ── Step 5b: Thumbnail ─────────────────────────
        print("Step 5b: Generating thumbnail...")
        image_paths = [p for t, p in media_paths if t == "image"]
        thumb_bg    = image_paths[0] if image_paths else None

        if thumb_bg:
            thumb_path = os.path.join("output", video_id, "thumbnail.png")
            generate_thumbnail(
                video_id=video_id,
                title=script["title"],
                animal=script["animal"],
                hook=script["hook"],
                image_path=thumb_bg,
                output_path=thumb_path,
            )
            print(f"✓ Thumbnail ready\n")
        else:
            thumb_path = None

        # ── Step 6: Post to YouTube ────────────────────
        mode = PIPELINE_MODE
        if mode == "auto":
            print("Step 6: Posting to YouTube...")
            upload_to_youtube(
                video_id=video_id,
                video_path=video_path,
                title=script["title"],
                privacy="public",
                thumbnail_path=thumb_path,
            )
            print(f"✓ Posted to YouTube!\n")
        else:
            print("Step 6: Ready — awaiting approval.")
            update_video(video_id, status="ready")

        return script["title"]

    except Exception as e:
        print(f"\n✗ Pipeline failed: {e}")
        if video_id:
            update_video(video_id, status="failed", error_message=str(e))
            log_step(video_id, "pipeline", "failed", str(e))
        send_failure_alert(e, video_id=video_id)
        return None


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
