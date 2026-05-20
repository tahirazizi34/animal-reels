import json
import anthropic
from config import ANTHROPIC_API_KEY
from database import get_recent_animals, StepTimer, update_video

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Prompt ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are a script writer for a family-friendly YouTube Shorts and TikTok channel 
called "Animal Reels". You write short, engaging, educational scripts about animals.

Your scripts must be:
- Warm, friendly, and suitable for all ages (kids and adults)
- Packed with genuinely surprising and fascinating facts
- Written in a conversational, enthusiastic tone (like a knowledgeable friend, not a textbook)
- Exactly 5 facts, each one a single clear sentence
- Between 60–90 seconds when read aloud (roughly 140–180 words for the narration)
- Structured with a hook opening, 5 facts, and a warm closing line

You always respond with valid JSON only. No markdown, no backticks, no preamble."""

USER_PROMPT_TEMPLATE = """Create a script for a 60-second animal facts video.

Rules:
- Do NOT use any of these recently featured animals: {recent_animals}
- Pick an animal that is visually interesting and photogenic
- Make the hook the very first line — surprising and attention-grabbing
- Each fact should be genuinely surprising, not something everyone already knows
- The closing line should encourage viewers to follow for more

Respond with this exact JSON structure:
{{
  "animal": "Animal name here",
  "title": "Catchy video title (max 60 chars, no hashtags)",
  "hook": "Opening line that grabs attention immediately",
  "facts": [
    "Fact 1 — one clear sentence",
    "Fact 2 — one clear sentence",
    "Fact 3 — one clear sentence",
    "Fact 4 — one clear sentence",
    "Fact 5 — one clear sentence"
  ],
  "closing": "Warm closing line encouraging follows",
  "scene_descriptions": [
    "Visual description for scene 1 (used for image generation)",
    "Visual description for scene 2",
    "Visual description for scene 3",
    "Visual description for scene 4",
    "Visual description for scene 5"
  ],
  "narration": "Full narration text combining hook + facts + closing, as it will be read aloud. No stage directions, just the words."
}}"""


# ── Main function ──────────────────────────────────────

def generate_script(video_id: str) -> dict:
    """
    Generate a complete animal facts script using Claude.
    Updates the video record in Supabase and returns the parsed script data.
    """
    with StepTimer(video_id, "script", "Generating animal facts script with Claude"):

        # Get recently used animals to avoid repetition
        recent = get_recent_animals(limit=30)
        recent_str = ", ".join(recent) if recent else "none yet"

        # Call Claude
        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(recent_animals=recent_str)
                }
            ],
            system=SYSTEM_PROMPT,
        )

        raw = message.content[0].text.strip()

        # Parse JSON response
        try:
            script = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"Claude returned invalid JSON: {e}\n\nRaw response:\n{raw}")

        # Validate required fields
        required_fields = ["animal", "title", "hook", "facts", "closing", "scene_descriptions", "narration"]
        missing = [f for f in required_fields if f not in script]
        if missing:
            raise ValueError(f"Script missing required fields: {missing}")

        if len(script["facts"]) != 5:
            raise ValueError(f"Expected 5 facts, got {len(script['facts'])}")

        if len(script["scene_descriptions"]) != 5:
            raise ValueError(f"Expected 5 scene descriptions, got {len(script['scene_descriptions'])}")

        # Save to database
        update_video(
            video_id,
            title=script["title"],
            script=script["narration"],
            animal=script["animal"],
            status="generating",
        )

        print(f"✓ Script generated: '{script['title']}' ({script['animal']})")
        print(f"  Narration length: {len(script['narration'].split())} words")

        return script


# ── Test runner ────────────────────────────────────────

if __name__ == "__main__":
    """Run this file directly to test script generation without the full pipeline."""
    import json

    print("Testing script generation...\n")

    # We need a fake video_id for testing — use a placeholder
    TEST_VIDEO_ID = "00000000-0000-0000-0000-000000000001"

    # Monkey-patch DB calls for isolated testing
    import database
    database.get_recent_animals = lambda limit=30: ["Lion", "Elephant", "Dolphin"]
    database.update_video = lambda vid, **kwargs: print(f"  [DB] Would save: {kwargs}")

    class FakeTimer:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

    database.StepTimer = FakeTimer

    script = generate_script(TEST_VIDEO_ID)

    print("\n── Generated Script ──────────────────────────────")
    print(json.dumps(script, indent=2))
