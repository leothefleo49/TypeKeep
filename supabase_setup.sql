-- ══════════════════════════════════════════════════════════════
-- TypeKeep Cloud Sync — Supabase Setup SQL
--
-- Run this in your Supabase project's SQL Editor:
--   https://supabase.com/dashboard → SQL Editor → New Query
--
-- This creates the tables needed for cross-device sync.
-- ══════════════════════════════════════════════════════════════

-- Sync groups (each group shares a passphrase)
CREATE TABLE IF NOT EXISTS sync_groups (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    sync_key TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Devices in each sync group
CREATE TABLE IF NOT EXISTS sync_devices (
    id TEXT PRIMARY KEY,
    sync_key TEXT NOT NULL,
    device_name TEXT NOT NULL DEFAULT 'Unknown',
    device_type TEXT NOT NULL DEFAULT 'desktop',
    last_seen TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Synced clipboard entries
CREATE TABLE IF NOT EXISTS sync_clipboard (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sync_key TEXT NOT NULL,
    device_id TEXT NOT NULL,
    device_name TEXT,
    content_type TEXT NOT NULL DEFAULT 'text',
    content_text TEXT,
    source_app TEXT,
    timestamp TIMESTAMPTZ DEFAULT now(),
    extra JSONB
);

-- Synced message summaries (for mobile viewing)
CREATE TABLE IF NOT EXISTS sync_messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sync_key TEXT NOT NULL,
    device_id TEXT NOT NULL,
    device_name TEXT,
    final_text TEXT,
    app TEXT,
    win_title TEXT,
    start_time DOUBLE PRECISION,
    end_time DOUBLE PRECISION,
    keystroke_count INTEGER DEFAULT 0,
    synced_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_sync_clip_key ON sync_clipboard(sync_key);
CREATE INDEX IF NOT EXISTS idx_sync_clip_ts ON sync_clipboard(timestamp);
CREATE INDEX IF NOT EXISTS idx_sync_msg_key ON sync_messages(sync_key);
CREATE INDEX IF NOT EXISTS idx_sync_msg_ts ON sync_messages(synced_at);
CREATE INDEX IF NOT EXISTS idx_sync_dev_key ON sync_devices(sync_key);

-- Row Level Security (RLS) — allow access via anon key
ALTER TABLE sync_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_clipboard ENABLE ROW LEVEL SECURITY;
ALTER TABLE sync_messages ENABLE ROW LEVEL SECURITY;

-- Policies: anyone with the anon key can read/write
-- (Security is handled by the sync_key passphrase)
CREATE POLICY "Allow all" ON sync_groups FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON sync_devices FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON sync_clipboard FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Allow all" ON sync_messages FOR ALL USING (true) WITH CHECK (true);

-- Auto-cleanup: delete entries older than 30 days (optional cron)
-- You can set up a Supabase Edge Function or pg_cron for this:
-- DELETE FROM sync_clipboard WHERE timestamp < now() - interval '30 days';
-- DELETE FROM sync_messages WHERE synced_at < now() - interval '30 days';
