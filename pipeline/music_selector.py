import os
import time
import subprocess
import httpx
import anthropic
from config import ANTHROPIC_API_KEY

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")

SYSTEM_PROMPT = """You are a music director for a nature documentary YouTube channel.
Given an animal name, you pick the perfect background music mood.
You always respond with a single JSON object only. No markdown, no explanation."""

USER_PROMPT = """Pick the perfect background music mood for a video about: {animal}

Respond with this exact JSON:
{{
  "mood": "one of: peaceful, mysterious, epic, playful, dramatic, serene, adventurous, ethereal",
  "reason": "one sentence why this mood fits"
}}"""

MOOD_FILTERS = {
    "peaceful":    "anoisesrc=color=brown:amplitude=0.4",
    "mysterious":  "anoisesrc=color=pink:amplitude=0.35",
    "serene":      "anoisesrc=color=brown:amplitude=0.3",
    "ethereal":    "anoisesrc=color=pink:amplitude=0.3",
    "epic":        "anoisesrc=color=white:amplitude=0.45",
    "dramatic":    "anoisesrc=color=white:amplitude=0.45",
    "playful":     "anoisesrc=color=brown:amplitude=0.4",
    "adventurous": "anoisesrc=color=pink:amplitude=0.4",
}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def pick_music_mood(animal: str) -> dict:
    import json
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT.format(animal=animal)}]
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    import json as j
    return j.loads(raw)


def _generate_ambient_tone(output_path: str, mood: str = "peaceful"):
    """Generate ambient background music using FFmpeg filters."""
    noise_filter = MOOD_FILTERS.get(mood, MOOD_FILTERS["peaceful"])
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"{noise_filter},highpass=f=80,lowpass=f=800,volume=0.6",
        "-t", "180",
        "-y", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg ambient tone failed:\n{result.stderr}")
    print(f"  ✓ Generated ambient tone ({mood})")


def download_music(animal: str, output_path: str) -> str:
    """Pick music mood and generate matching ambient track."""
    print(f"  Selecting music for: {animal}")
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    try:
        mood_data = pick_music_mood(animal)
        mood      = mood_data["mood"]
        print(f"  ✓ Mood: {mood} — {mood_data['reason']}")
    except Exception as e:
        print(f"  ⚠ Mood selection failed ({e}), using peaceful")
        mood = "peaceful"

    print(f"  Generating ambient {mood} music...")
    _generate_ambient_tone(output_path, mood)
    size_kb = os.path.getsize(output_path) // 1024
    print(f"  ✓ Music ready ({size_kb}KB)")
    return output_path
