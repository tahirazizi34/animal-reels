import os
import httpx
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
from database import StepTimer, log_step

ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1"

# ── Voice settings ─────────────────────────────────────
# Tuned for warm, engaging animal documentary style
VOICE_SETTINGS = {
    "stability": 0.75,         # Higher = more consistent tone
    "similarity_boost": 0.75,  # Higher = closer to original voice
    "style": 0.3,              # Slight expressiveness
    "use_speaker_boost": True, # Cleaner audio quality
}

HEADERS = {
    "xi-api-key": ELEVENLABS_API_KEY,
    "Content-Type": "application/json",
}


# ── Main function ──────────────────────────────────────

def generate_voiceover(video_id: str, narration: str, output_path: str) -> str:
    """
    Generate a voiceover MP3 from narration text using ElevenLabs.
    Returns the local path to the saved MP3 file.
    """
    with StepTimer(video_id, "voice", "Generating voiceover with ElevenLabs"):

        print(f"  Voice ID: {ELEVENLABS_VOICE_ID}")
        print(f"  Narration: {len(narration.split())} words / ~{_estimate_duration(narration)}s")

        audio_bytes = _call_elevenlabs(narration)

        # Save to disk
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        size_kb = len(audio_bytes) // 1024
        print(f"  ✓ Voiceover saved to {output_path} ({size_kb}KB)")

    return output_path


def _call_elevenlabs(narration: str) -> bytes:
    """Call ElevenLabs TTS API and return raw audio bytes."""
    url = f"{ELEVENLABS_API_URL}/text-to-speech/{ELEVENLABS_VOICE_ID}"

    response = httpx.post(
        url,
        headers=HEADERS,
        json={
            "text": narration,
            "model_id": "eleven_multilingual_v2",  # Best quality model
            "voice_settings": VOICE_SETTINGS,
        },
        timeout=60,
    )

    if response.status_code == 401:
        raise PermissionError("ElevenLabs API key is invalid or expired.")
    elif response.status_code == 422:
        raise ValueError(f"ElevenLabs rejected the request: {response.text}")

    response.raise_for_status()
    return response.content


def _estimate_duration(text: str) -> int:
    """Rough estimate: average speaking pace ~140 words/minute."""
    words = len(text.split())
    return round((words / 140) * 60)


def list_voices() -> list:
    """Helper to list all available voices on your ElevenLabs account."""
    response = httpx.get(
        f"{ELEVENLABS_API_URL}/voices",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    voices = response.json().get("voices", [])
    return [{"id": v["voice_id"], "name": v["name"]} for v in voices]


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    print("Testing voiceover generation...\n")

    # First, list available voices so you can pick the best one
    print("Fetching your available ElevenLabs voices...\n")
    try:
        voices = list_voices()
        print("── Available Voices ──────────────────────────────")
        for v in voices:
            marker = " ← currently selected" if v["id"] == ELEVENLABS_VOICE_ID else ""
            print(f"  {v['name']:<30} {v['id']}{marker}")
        print()
    except Exception as e:
        print(f"Could not fetch voices: {e}\n")

    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"

    # Narration from the Axolotl script generated in Phase 2
    TEST_NARRATION = (
        "This adorable creature can regrow its own brain, and scientists are obsessed "
        "with figuring out how. Axolotls can regenerate not just limbs, but their heart, "
        "lungs, spinal cord, and even parts of their brain with zero scarring. "
        "Unlike most amphibians, axolotls never go through metamorphosis — they stay in "
        "their juvenile aquatic form their entire lives. "
        "They're only found naturally in one place on Earth: a single lake system near "
        "Mexico City, and they're critically endangered in the wild. "
        "Axolotls breathe through their feathery external gills, but they also have "
        "functional lungs and can gulp air from the surface. "
        "Their cells are ten times more resistant to cancer than mammal cells, making "
        "them invaluable for medical research. "
        "Follow Animal Reels for more incredible creatures you won't believe are real!"
    )

    # Patch DB calls for isolated test
    import database
    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
    database.StepTimer = FakeTimer
    database.log_step = lambda *a, **kw: None

    output_path = os.path.join("test_audio", "axolotl_voiceover.mp3")

    print(f"Generating voiceover for Axolotl script...")
    print(f"Estimated duration: ~{_estimate_duration(TEST_NARRATION)} seconds\n")

    path = generate_voiceover(TEST_VIDEO_ID, TEST_NARRATION, output_path)

    print(f"\n── Result ────────────────────────────────────────")
    print(f"  File: {path}")
    print(f"  Size: {os.path.getsize(path) // 1024}KB")
    print(f"\n✓ Open '{output_path}' to listen to the voiceover!")
    print(f"\nTip: If you want a different voice, copy any voice ID")
    print(f"     from the list above into ELEVENLABS_VOICE_ID in your .env")
