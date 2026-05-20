import os
import json
import subprocess
from database import StepTimer, log_step, update_video

# ── Video settings ─────────────────────────────────────
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
FPS          = 30
VIDEO_CODEC  = "libx264"
AUDIO_CODEC  = "aac"
CRF          = 23
PRESET       = "fast"

MUSIC_VOLUME = 0.12


def assemble_video(video_id, image_paths, audio_path, output_path, title, music_path=None):
    """Assemble final MP4 from images + voiceover."""
    with StepTimer(video_id, "assembly", "Assembling video with FFmpeg"):

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Get audio duration
        duration = _get_audio_duration(audio_path)
        print(f"  Audio duration: {duration:.1f}s")

        time_per_image = duration / len(image_paths)
        print(f"  Time per image: {time_per_image:.1f}s ({len(image_paths)} scenes)")

        # Create slideshow (simple crossfade, no zoom)
        temp_video = output_path.replace(".mp4", "_temp.mp4")
        _create_slideshow_simple(image_paths, time_per_image, temp_video)
        print(f"  ✓ Slideshow created")

        # Merge with audio
        if music_path and os.path.exists(music_path):
            _merge_with_music(temp_video, audio_path, music_path, output_path)
            print(f"  ✓ Merged with background music")
        else:
            _merge_audio_only(temp_video, audio_path, output_path)
            print(f"  ✓ Merged with voiceover")

        if os.path.exists(temp_video):
            os.remove(temp_video)

        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"  ✓ Final video: {output_path} ({size_mb:.1f}MB)")
        update_video(video_id, status="ready", video_url=output_path)

    return output_path


def _create_slideshow_simple(image_paths, time_per_image, output_path):
    """
    Fast slideshow: resize each image to 1080x1920, show for N seconds.
    No zoom — just clean cuts between scenes.
    """
    # Write a concat file listing each image with its duration
    concat_file = output_path + ".txt"
    with open(concat_file, "w") as f:
        for img in image_paths:
            abs_path = os.path.abspath(img).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")
            f.write(f"duration {time_per_image:.3f}\n")
        # FFmpeg concat needs the last file listed twice
        abs_path = os.path.abspath(image_paths[-1]).replace("\\", "/")
        f.write(f"file '{abs_path}'\n")

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", concat_file,
        "-vf", f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,"
               f"setsar=1",
        "-c:v", VIDEO_CODEC,
        "-crf", str(CRF),
        "-preset", PRESET,
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-y", output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(concat_file):
        os.remove(concat_file)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg slideshow failed:\n{result.stderr}")


def _get_audio_duration(audio_path):
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", audio_path],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    for stream in data["streams"]:
        if stream.get("codec_type") == "audio":
            return float(stream["duration"])
    raise ValueError(f"Could not get duration from {audio_path}")


def _merge_audio_only(video_path, audio_path, output_path):
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", AUDIO_CODEC,
        "-shortest", "-y", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed:\n{result.stderr}")


def _merge_with_music(video_path, voice_path, music_path, output_path):
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", video_path, "-i", voice_path, "-i", music_path,
        "-filter_complex",
        f"[2:a]volume={MUSIC_VOLUME},aloop=loop=-1:size=2e+09[music];"
        f"[1:a][music]amix=inputs=2:duration=first:dropout_transition=3[audio]",
        "-map", "0:v", "-map", "[audio]",
        "-c:v", "copy", "-c:a", AUDIO_CODEC,
        "-shortest", "-y", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg merge failed:\n{result.stderr}")


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    import glob

    print("Testing video assembly...\n")

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("✓ FFmpeg found\n")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("✗ FFmpeg not found! Install from https://ffmpeg.org/download.html")
        exit(1)

    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"
    image_paths   = sorted(glob.glob("test_images/scene_*.png"))
    audio_path    = "test_audio/axolotl_voiceover.mp3"
    output_path   = "test_output/axolotl_final.mp4"

    if not image_paths:
        print("✗ No images found in test_images/ — run image_gen.py first"); exit(1)
    if not os.path.exists(audio_path):
        print("✗ No voiceover found — run voice_gen.py first"); exit(1)

    print(f"✓ Found {len(image_paths)} images")
    print(f"✓ Found voiceover: {audio_path}")
    print(f"\nAssembling video...\n")

    import database
    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    database.StepTimer    = FakeTimer
    database.log_step     = lambda *a, **kw: None
    database.update_video = lambda *a, **kw: None

    path = assemble_video(
        video_id=TEST_VIDEO_ID,
        image_paths=image_paths,
        audio_path=audio_path,
        output_path=output_path,
        title="5 Incredible Facts About Axolotls",
    )

    print(f"\n── Result ────────────────────────────────────────")
    print(f"  File : {path}")
    print(f"  Size : {os.path.getsize(path) / (1024*1024):.1f}MB")
    print(f"\n✓ Open '{output_path}' to watch your first video!")
