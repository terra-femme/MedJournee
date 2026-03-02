-- Supabase (PostgreSQL) migration for MedJournee
-- Run this in the Supabase SQL Editor to create all tables

-- ==================== LIVE SESSIONS ====================
CREATE TABLE IF NOT EXISTS live_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    family_id VARCHAR(100) NOT NULL,
    target_language VARCHAR(10) NOT NULL DEFAULT 'vi',
    session_status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (session_status IN ('active', 'completed', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    total_segments INTEGER DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_sessions_user_id ON live_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_family_id ON live_sessions(family_id);
CREATE INDEX IF NOT EXISTS idx_live_sessions_status ON live_sessions(session_status);
CREATE INDEX IF NOT EXISTS idx_live_sessions_started_at ON live_sessions(started_at);

-- ==================== SESSION SEGMENTS ====================
CREATE TABLE IF NOT EXISTS session_segments (
    segment_id VARCHAR(100) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL REFERENCES live_sessions(session_id) ON DELETE CASCADE,
    speaker VARCHAR(50) NOT NULL,
    speaker_role VARCHAR(30) DEFAULT 'Unknown'
        CHECK (speaker_role IN ('Healthcare Provider', 'Patient/Family', 'Unknown')),
    original_text TEXT NOT NULL,
    translated_text TEXT,
    timestamp_start NUMERIC(12,3),
    timestamp_end NUMERIC(12,3),
    confidence NUMERIC(4,3),
    enrollment_match BOOLEAN DEFAULT FALSE,
    enrollment_confidence NUMERIC(4,3),
    method VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_session_segments_session_id ON session_segments(session_id);
CREATE INDEX IF NOT EXISTS idx_session_segments_speaker ON session_segments(speaker);
CREATE INDEX IF NOT EXISTS idx_session_segments_created_at ON session_segments(created_at);

-- ==================== JOURNAL ENTRIES ====================
CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id VARCHAR(100) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL REFERENCES live_sessions(session_id) ON DELETE CASCADE,
    user_id VARCHAR(100) NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    family_id VARCHAR(100) NOT NULL,
    visit_date DATE NOT NULL,
    provider_name VARCHAR(255),
    visit_type VARCHAR(100),
    main_reason TEXT,
    symptoms TEXT,
    diagnoses TEXT,
    treatments TEXT,
    vital_signs TEXT,
    test_results TEXT,
    medications TEXT,
    follow_up_instructions TEXT,
    next_appointments TEXT,
    action_items TEXT,
    patient_questions TEXT,
    family_concerns TEXT,
    family_summary TEXT,
    medical_terms_explained TEXT,
    visit_summary TEXT NOT NULL,
    raw_transcript TEXT,  -- Stores the full conversation transcript with speaker labels
    ai_confidence NUMERIC(4,3),
    ai_model VARCHAR(100),
    processing_method VARCHAR(100),  -- 'ai_medical_summarization' or 'raw_transcript_only'
    consent_given BOOLEAN DEFAULT TRUE,
    audio_deleted BOOLEAN DEFAULT TRUE,
    transcripts_deleted BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    personal_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_journal_entries_session_id ON journal_entries(session_id);
CREATE INDEX IF NOT EXISTS idx_journal_entries_user_id ON journal_entries(user_id);
CREATE INDEX IF NOT EXISTS idx_journal_entries_family_id ON journal_entries(family_id);
CREATE INDEX IF NOT EXISTS idx_journal_entries_visit_date ON journal_entries(visit_date);
CREATE INDEX IF NOT EXISTS idx_journal_entries_patient_name ON journal_entries(patient_name);
CREATE INDEX IF NOT EXISTS idx_journal_entries_created_at ON journal_entries(created_at);

-- ==================== VOICE ENROLLMENTS ====================
CREATE TABLE IF NOT EXISTS voice_enrollments (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
    family_id VARCHAR(255) NOT NULL,
    speaker_name VARCHAR(255) NOT NULL,
    relationship VARCHAR(100) NOT NULL,
    encrypted_voice_profile TEXT NOT NULL,
    quality_score NUMERIC(3,2) NOT NULL,
    sample_count INTEGER NOT NULL,
    enrollment_date TIMESTAMPTZ NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    privacy_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==================== AUTO-UPDATE updated_at ====================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_live_sessions_updated_at
    BEFORE UPDATE ON live_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_journal_entries_updated_at
    BEFORE UPDATE ON journal_entries
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
