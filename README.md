# 🐾 Animal Reels — Private Pipeline

An automated video generation and posting pipeline for animal facts content.
Generates short-form videos daily and posts them to YouTube Shorts and TikTok.

---

## Stack

| Layer | Tool |
|---|---|
| Dashboard | HTML/CSS/JS (served via Railway) |
| Database | Supabase (Postgres) |
| AI Scripts | Claude API (Anthropic) |
| Image Gen | Replicate (Stable Diffusion XL) |
| Voiceover | ElevenLabs |
| Video Assembly | FFmpeg |
| Storage | Backblaze B2 |
| Social Posting | YouTube Data API v3 + TikTok API |
| Hosting | Railway |

---

## Setup

### 1. Clone and install

```bash
git clone <your-repo>
cd animal-reels
cp .env.example .env
# Fill in all your API keys in .env
```

### 2. Set up Supabase

1. Go to your Supabase project → SQL Editor
2. Paste the contents of `supabase_schema.sql`
3. Click Run
4. Copy your Project URL and keys into `.env`

### 3. Install Python deps

```bash
cd pipeline
pip install -r requirements.txt
```

### 4. Install FFmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu / Railway (add to Dockerfile)
apt-get install -y ffmpeg
```

### 5. Deploy to Railway

```bash
railway login
railway init
railway up
```

---

## Project Structure

```
animal-reels/
├── dashboard/
│   └── index.html          ← Your private dashboard UI
├── pipeline/
│   ├── main.py             ← Entry point, orchestrates all steps
│   ├── script_gen.py       ← Claude generates animal facts script
│   ├── image_gen.py        ← Replicate generates scene images
│   ├── voice_gen.py        ← ElevenLabs generates voiceover
│   ├── video_assembly.py   ← FFmpeg assembles final MP4
│   ├── uploader.py         ← Uploads to Backblaze B2
│   └── poster.py           ← Posts to YouTube & TikTok
├── scheduler/
│   └── cron.py             ← Daily scheduler
├── supabase_schema.sql     ← Run this in Supabase SQL editor
├── .env.example            ← Copy to .env and fill in keys
└── README.md
```

---

## Pipeline Flow

```
Cron fires at 09:00 UTC
  └─→ main.py runs
        ├─→ script_gen.py   → generates script + title
        ├─→ image_gen.py    → generates 5 scene images
        ├─→ voice_gen.py    → generates MP3 voiceover
        ├─→ video_assembly.py → stitches into MP4
        ├─→ uploader.py     → saves to Backblaze
        └─→ poster.py       → posts to YouTube/TikTok
                              (or waits for approval if mode=approve)
```

---

## Build Phases

- [x] Phase 1 — Foundation (dashboard + database schema + project structure)
- [ ] Phase 2 — Script engine (Claude generates animal facts scripts)
- [ ] Phase 3 — Image engine (Replicate generates scene visuals)
- [ ] Phase 4 — Voice engine (ElevenLabs narration)
- [ ] Phase 5 — Video assembly (FFmpeg stitches everything)
- [ ] Phase 6 — Auto-posting (YouTube + TikTok APIs)
- [ ] Phase 7 — Scheduler (daily cron on Railway)
