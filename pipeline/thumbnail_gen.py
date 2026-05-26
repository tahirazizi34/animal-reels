"""
thumbnail_gen.py — Auto-generates YouTube thumbnails for animal videos

Creates a 1280x720 thumbnail with:
- Background: first scene image (blurred + darkened)
- Animal name in bold
- Hook text (attention-grabbing fact)
- Decorative accent elements
"""

import os
import subprocess
import textwrap
from database import StepTimer, update_video

# ── Thumbnail settings ─────────────────────────────────
THUMB_WIDTH  = 1280
THUMB_HEIGHT = 720

# Color schemes per mood — vibrant and eye-catching
MOOD_COLORS = {
    "ocean":      {"bg": "#0a1628", "accent": "#00d4ff", "text": "#ffffff"},
    "jungle":     {"bg": "#0a1f0a", "accent": "#39ff14", "text": "#ffffff"},
    "desert":     {"bg": "#2d1b00", "accent": "#ff8c00", "text": "#ffffff"},
    "arctic":     {"bg": "#0d1b2a", "accent": "#a8d8f0", "text": "#ffffff"},
    "savanna":    {"bg": "#1a0f00", "accent": "#ffd700", "text": "#ffffff"},
    "default":    {"bg": "#0a0a0a", "accent": "#7cfc6e", "text": "#ffffff"},
}


def generate_thumbnail(
    video_id:   str,
    title:      str,
    animal:     str,
    hook:       str,
    image_path: str,
    output_path: str,
) -> str:
    """
    Generate a YouTube thumbnail using FFmpeg.
    Returns path to the thumbnail PNG.
    """
    with StepTimer(video_id, "thumbnail", f"Generating thumbnail for {animal}"):

        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

        # Pick color scheme based on animal habitat
        colors = _pick_colors(animal)

        # Build thumbnail using FFmpeg drawtext filter
        _generate_with_ffmpeg(
            image_path=image_path,
            output_path=output_path,
            animal=_sanitize_text(animal),
            hook=_shorten_hook(hook),
            colors=colors,
        )

        size_kb = os.path.getsize(output_path) // 1024
        print(f"  ✓ Thumbnail saved: {output_path} ({size_kb}KB)")

        update_video(video_id, thumbnail_url=output_path)

    return output_path


def _sanitize_text(text: str) -> str:
    """Remove ALL characters that could break FFmpeg drawtext filter."""
    import re
    # Keep only letters, numbers and spaces - safest possible
    text = re.sub(r"[^a-zA-Z0-9 ]", "", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def _shorten_hook(hook: str, max_len: int = 38) -> str:
    """Shorten hook text to fit on thumbnail."""
    hook = _sanitize_text(hook)
    if len(hook) <= max_len:
        return hook
    shortened = hook[:max_len].rsplit(" ", 1)[0]
    return shortened + "..."


def _pick_colors(animal: str) -> dict:
    """Pick color scheme based on animal's typical habitat."""
    animal_lower = animal.lower()

    ocean_animals = ["shark", "whale", "dolphin", "octopus", "shrimp", "crab",
                     "jellyfish", "seal", "walrus", "orca", "tuna", "squid"]
    jungle_animals = ["frog", "parrot", "jaguar", "gorilla", "sloth", "toucan",
                      "chameleon", "anaconda", "lemur", "orangutan"]
    arctic_animals = ["polar bear", "penguin", "arctic", "snow leopard", "wolf",
                      "seal", "walrus", "husky", "reindeer", "narwhal"]
    savanna_animals = ["lion", "elephant", "giraffe", "zebra", "cheetah",
                       "rhino", "hippo", "wildebeest", "hyena", "meerkat"]
    desert_animals  = ["camel", "scorpion", "rattlesnake", "roadrunner",
                       "fennec", "jerboa", "horned lizard"]

    for a in ocean_animals:
        if a in animal_lower: return MOOD_COLORS["ocean"]
    for a in jungle_animals:
        if a in animal_lower: return MOOD_COLORS["jungle"]
    for a in arctic_animals:
        if a in animal_lower: return MOOD_COLORS["arctic"]
    for a in savanna_animals:
        if a in animal_lower: return MOOD_COLORS["savanna"]
    for a in desert_animals:
        if a in animal_lower: return MOOD_COLORS["desert"]

    return MOOD_COLORS["default"]


def _hex_to_ffmpeg(hex_color: str) -> str:
    """Convert #rrggbb to ffmpeg color format."""
    h = hex_color.lstrip('#')
    return f"0x{h}FF"


def _generate_with_ffmpeg(image_path, output_path, animal, hook, colors):
    """Use FFmpeg drawtext to create thumbnail."""

    accent   = _hex_to_ffmpeg(colors["accent"])
    text_col = _hex_to_ffmpeg(colors["text"])
    bg_col   = _hex_to_ffmpeg(colors["bg"])

    # Wrap hook text if too long
    hook_lines = textwrap.wrap(hook, width=28)
    hook_line1 = hook_lines[0] if len(hook_lines) > 0 else ""
    hook_line2 = hook_lines[1] if len(hook_lines) > 1 else ""

    # Build filter chain
    filters = [
        # Step 1: Scale and crop background image to 1280x720
        f"scale={THUMB_WIDTH}:{THUMB_HEIGHT}:force_original_aspect_ratio=increase",
        f"crop={THUMB_WIDTH}:{THUMB_HEIGHT}",

        # Step 2: Blur and darken the background
        "gblur=sigma=8",
        "eq=brightness=-0.25:saturation=0.8",

        # Step 3: Dark overlay on left side for text readability
        f"drawbox=x=0:y=0:w={THUMB_WIDTH//2+100}:h={THUMB_HEIGHT}:color={bg_col}@0.65:t=fill",

        # Step 4: Accent bar on left edge
        f"drawbox=x=0:y=0:w=12:h={THUMB_HEIGHT}:color={accent}:t=fill",

        # Step 5: Animal name (big, bold)
        f"drawtext=text='{animal.upper()}':fontsize=88:fontcolor={accent}:"
        f"x=40:y=180:font=Impact:"
        f"shadowcolor=black@0.9:shadowx=4:shadowy=4",

        # Step 6: Hook line 1
        f"drawtext=text='{hook_line1}':fontsize=52:fontcolor={text_col}:"
        f"x=40:y=310:font=Impact:"
        f"shadowcolor=black@0.9:shadowx=3:shadowy=3",
    ]

    # Add second hook line if exists
    if hook_line2:
        filters.append(
            f"drawtext=text='{hook_line2}':fontsize=52:fontcolor={text_col}:"
            f"x=40:y=375:font=Impact:"
            f"shadowcolor=black@0.9:shadowx=3:shadowy=3"
        )

    # Step 7: "ANIMAL REELS" branding at bottom
    filters.append(
        f"drawbox=x=0:y={THUMB_HEIGHT-60}:w=320:h=60:color={accent}@0.9:t=fill"
    )
    filters.append(
        f"drawtext=text='🐾 ANIMAL REELS':fontsize=28:fontcolor=black:"
        f"x=20:y={THUMB_HEIGHT-42}:font=Impact"
    )

    filter_str = ",".join(filters)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", image_path,
        "-vf", filter_str,
        "-vframes", "1",
        "-q:v", "2",
        "-y", output_path
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg thumbnail failed:\n{result.stderr}")


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    import glob

    print("Testing thumbnail generation...\n")

    # Find a test image
    images = sorted(glob.glob("test_images/scene_*.png"))
    if not images:
        print("✗ No images found in test_images/")
        print("  Run image_gen.py first")
        exit(1)

    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"

    import database
    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    database.StepTimer    = FakeTimer
    database.log_step     = lambda *a, **kw: None
    database.update_video = lambda *a, **kw: None

    os.makedirs("test_output", exist_ok=True)

    test_cases = [
        ("Axolotl",      "This adorable creature can regrow its own brain"),
        ("Snow Leopard",  "This ghost of the mountains is almost invisible"),
        ("Pistol Shrimp", "This tiny shrimp creates underwater explosions"),
    ]

    for animal, hook in test_cases:
        out = f"test_output/thumbnail_{animal.lower().replace(' ','_')}.png"
        print(f"Generating thumbnail: {animal}")
        path = generate_thumbnail(
            video_id=TEST_VIDEO_ID,
            title=f"5 Facts About {animal}",
            animal=_sanitize_text(animal),
            hook=hook,
            image_path=images[0],
            output_path=out,
        )
        print(f"  → {path}\n")

    print("✓ Open test_output/ to see your thumbnails!")
