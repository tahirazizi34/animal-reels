-- ══════════════════════════════════════════════════
--  Animal Reels — Supabase Schema
--  Run this in your Supabase SQL editor
-- ══════════════════════════════════════════════════

-- Videos table: every generated video lives here
create table videos (
  id            uuid primary key default gen_random_uuid(),
  created_at    timestamptz default now(),

  -- Content
  channel       text not null check (channel in ('animals', 'kids', 'satisfying')),
  title         text not null,
  script        text not null,
  animal        text,                      -- e.g. "Red Panda"

  -- Pipeline step tracking
  status        text not null default 'pending'
                check (status in (
                  'pending',       -- just created
                  'generating',    -- pipeline is running
                  'ready',         -- video assembled, waiting for approval
                  'approved',      -- you approved it
                  'posting',       -- being uploaded to social
                  'posted',        -- live on social media
                  'failed'         -- something went wrong
                )),

  error_message text,                      -- if status = failed, why

  -- File paths
  video_url     text,                      -- Backblaze URL of final MP4
  thumbnail_url text,                      -- thumbnail image URL

  -- Social media results
  youtube_id    text,                      -- YouTube video ID after posting
  tiktok_id     text,                      -- TikTok video ID after posting
  posted_at     timestamptz                -- when it went live
);

-- Pipeline logs table: detailed logs per video step
create table pipeline_logs (
  id         uuid primary key default gen_random_uuid(),
  created_at timestamptz default now(),
  video_id   uuid references videos(id) on delete cascade,
  step       text not null,               -- 'script', 'images', 'voice', 'assembly', 'upload'
  status     text not null check (status in ('started', 'done', 'failed')),
  message    text,
  duration_ms int                         -- how long the step took
);

-- Settings table: your channel config
create table settings (
  key   text primary key,
  value text not null
);

-- Default settings
insert into settings (key, value) values
  ('animals_enabled',   'true'),
  ('kids_enabled',      'false'),
  ('satisfying_enabled','false'),
  ('videos_per_day',    '2'),
  ('pipeline_mode',     'approve'),        -- 'auto' or 'approve'
  ('post_time',         '09:00');          -- daily run time (UTC)

-- Index for fast dashboard queries
create index on videos (status);
create index on videos (created_at desc);
create index on videos (channel);
create index on pipeline_logs (video_id);

-- ── Row Level Security ─────────────────────────────
-- Since this is your private dashboard, we keep it simple
alter table videos enable row level security;
alter table pipeline_logs enable row level security;
alter table settings enable row level security;

-- Service role (your backend) has full access
create policy "service role full access on videos"
  on videos for all
  using (true)
  with check (true);

create policy "service role full access on logs"
  on pipeline_logs for all
  using (true)
  with check (true);

create policy "service role full access on settings"
  on settings for all
  using (true)
  with check (true);
