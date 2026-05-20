import os
from dotenv import load_dotenv

load_dotenv()

# ── Supabase ──────────────────────────────────────────
SUPABASE_URL              = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY         = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# ── Anthropic ─────────────────────────────────────────
ANTHROPIC_API_KEY         = os.getenv("ANTHROPIC_API_KEY")

# ── Replicate ─────────────────────────────────────────
REPLICATE_API_TOKEN       = os.getenv("REPLICATE_API_TOKEN")

# ── ElevenLabs ────────────────────────────────────────
ELEVENLABS_API_KEY        = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID       = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

# ── Backblaze B2 ──────────────────────────────────────
B2_KEY_ID                 = os.getenv("B2_KEY_ID")
B2_APPLICATION_KEY        = os.getenv("B2_APPLICATION_KEY")
B2_BUCKET_NAME            = os.getenv("B2_BUCKET_NAME", "animal-reels-videos")
B2_ENDPOINT               = os.getenv("B2_ENDPOINT")

# ── App config ────────────────────────────────────────
VIDEOS_PER_DAY            = int(os.getenv("VIDEOS_PER_DAY", "2"))
PIPELINE_MODE             = os.getenv("PIPELINE_MODE", "approve")  # 'auto' or 'approve'

def validate():
    """Call this at startup to catch missing keys early."""
    required = {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_SERVICE_ROLE_KEY": SUPABASE_SERVICE_ROLE_KEY,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "REPLICATE_API_TOKEN": REPLICATE_API_TOKEN,
        "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
        "B2_KEY_ID": B2_KEY_ID,
        "B2_APPLICATION_KEY": B2_APPLICATION_KEY,
        "B2_ENDPOINT": B2_ENDPOINT,
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
