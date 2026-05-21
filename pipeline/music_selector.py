import os
import httpx
import anthropic
from config import ANTHROPIC_API_KEY

PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
PIXABAY_API_URL = "https://pixabay.com/api/videos/music/"  # Note: music endpoint

# ── Music mood selector ────────────────────────────────

SYSTEM_PROMPT = """You are a music director for a nature documentary YouTube channel.
Given an animal name, you pick the perfect background music mood.
You always respond with a single JSON object only. No markdown, no explanation."""

USER_PROMPT = """Pick the perfect background music mood for a video about: {animal}

Respond with this exact JSON:
{{
  "mood": "one of: peaceful, mysterious, epic, playful, dramatic, serene, adventurous, ethereal",
  "search_term": "2-3 word search query for royalty-free music (e.g. 'ocean ambient calm')",
  "reason": "one sentence why this mood fits"
}}"""

# Fallback search terms if Pixabay fails
MOOD_FALLBACKS = {
    "peaceful":    "peaceful nature ambient",
    "mysterious":  "mysterious dark ambient",
    "epic":        "epic cinematic nature",
    "playful":     "playful light acoustic",
    "dramatic":    "dramatic cinematic tension",
    "serene":      "serene calm meditation",
    "adventurous": "adventurous exploration music",
    "ethereal":    "ethereal soft ambient",
}

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def pick_music_mood(animal: str) -> dict:
    """Use Claude to pick the perfect music mood for an animal."""
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=200,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": USER_PROMPT.format(animal=animal)
        }]
    )

    import json
    raw = message.content[0].text.strip()
    return json.loads(raw)


def download_music(animal: str, output_path: str) -> str:
    """
    Pick music mood for the animal and download a matching track.
    Returns path to downloaded MP3.
    Falls back to bundled tracks if Pixabay unavailable.
    """
    print(f"  Selecting music for: {animal}")

    # Step 1: Claude picks the mood
    try:
        mood_data = pick_music_mood(animal)
        mood        = mood_data["mood"]
        search_term = mood_data["search_term"]
        print(f"  ✓ Mood: {mood} — {mood_data['reason']}")
    except Exception as e:
        print(f"  ⚠ Mood selection failed ({e}), using peaceful fallback")
        mood        = "peaceful"
        search_term = "peaceful nature ambient"

    # Step 2: Search Pixabay for a matching track
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    if PIXABAY_API_KEY:
        try:
            track_url = _search_pixabay(search_term)
            if track_url:
                _download_file(track_url, output_path)
                print(f"  ✓ Music downloaded: {os.path.basename(output_path)}")
                return output_path
        except Exception as e:
            print(f"  ⚠ Pixabay download failed ({e}), trying freemusicarchive...")

    # Step 3: Fallback — Free Music Archive (no API key needed)
    try:
        track_url = _search_free_music_archive(mood)
        if track_url:
            _download_file(track_url, output_path)
            print(f"  ✓ Music downloaded from FMA: {os.path.basename(output_path)}")
            return output_path
    except Exception as e:
        print(f"  ⚠ FMA failed ({e})")

    # Step 4: Last resort — generate a simple tone with FFmpeg
    print(f"  ⚠ Using generated ambient tone as music fallback")
    _generate_ambient_tone(output_path)
    return output_path


def _search_pixabay(search_term: str) -> str | None:
    """Search Pixabay music API and return download URL."""
    response = httpx.get(
        "https://pixabay.com/api/music/",
        params={
            "key":      PIXABAY_API_KEY,
            "q":        search_term,
            "per_page": 5,
        },
        timeout=15,
    )
    response.raise_for_status()
    hits = response.json().get("hits", [])
    if hits:
        return hits[0].get("audio", {}).get("url")
    return None


def _search_free_music_archive(mood: str) -> str | None:
    """
    Search Free Music Archive for royalty-free tracks.
    Uses curated ambient/nature tracks that are Creative Commons licensed.
    """
    # Curated list of CC0/CC-BY royalty-free ambient tracks from FMA
    CURATED_TRACKS = {
        "peaceful":    "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kai_Engel/Satin/Kai_Engel_-_01_-_Satin.mp3",
        "mysterious":  "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Sustains/Kai_Engel_-_07_-_Interlude.mp3",
        "serene":      "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kai_Engel/Satin/Kai_Engel_-_04_-_Contention.mp3",
        "playful":     "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Kai_Engel/Satin/Kai_Engel_-_02_-_Intermezzo.mp3",
        "epic":        "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Sustains/Kai_Engel_-_01_-_Sustain.mp3",
        "dramatic":    "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Sustains/Kai_Engel_-_03_-_Contention.mp3",
        "adventurous": "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Sustains/Kai_Engel_-_05_-_Interlude.mp3",
        "ethereal":    "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/ccCommunity/Kai_Engel/Sustains/Kai_Engel_-_09_-_Sustain.mp3",
    }
    return CURATED_TRACKS.get(mood, CURATED_TRACKS["peaceful"])


def _download_file(url: str, output_path: str):
    """Download a file from URL to local path."""
    response = httpx.get(url, follow_redirects=True, timeout=60)
    response.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(response.content)


def _generate_ambient_tone(output_path: str):
    """Generate a simple ambient tone using FFmpeg as last resort."""
    import subprocess
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi",
        "-i", "anoisesrc=color=brown:amplitude=0.05",
        "-t", "120",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    import sys

    test_animals = [
        "Axolotl",
        "Great White Shark",
        "Hummingbird",
        "Tardigrade",
        "Snow Leopard",
    ]

    print("Testing music selection...\n")

    for animal in test_animals:
        print(f"Animal: {animal}")
        try:
            mood_data = pick_music_mood(animal)
            print(f"  Mood:   {mood_data['mood']}")
            print(f"  Search: {mood_data['search_term']}")
            print(f"  Why:    {mood_data['reason']}\n")
        except Exception as e:
            print(f"  Error: {e}\n")

    # Test full download
    print("Testing music download for 'Snow Leopard'...")
    os.makedirs("test_audio", exist_ok=True)
    path = download_music("Snow Leopard", "test_audio/test_music.mp3")
    if os.path.exists(path):
        size_kb = os.path.getsize(path) // 1024
        print(f"✓ Downloaded: {path} ({size_kb}KB)")
    else:
        print("✗ Download failed")
