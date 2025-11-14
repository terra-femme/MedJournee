-- 1. Live Sessions Table
-- Tracks all medical visit sessions (active and completed)
CREATE TABLE IF NOT EXISTS live_sessions (
    session_id VARCHAR(100) PRIMARY KEY,
    user_id VARCHAR(100) NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    family_id VARCHAR(100) NOT NULL,
    target_language VARCHAR(10) NOT NULL DEFAULT 'vi',
    session_status ENUM('active', 'completed', 'failed') NOT NULL DEFAULT 'active',
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP NULL,
    total_segments INT DEFAULT 0,
    duration_seconds INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_family_id (family_id),
    INDEX idx_status (session_status),
    INDEX idx_started_at (started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Session Segments Table
-- Temporarily stores conversation segments during active sessions
-- Auto-deleted after journal generation for privacy
CREATE TABLE IF NOT EXISTS session_segments (
    segment_id VARCHAR(100) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    speaker VARCHAR(50) NOT NULL,
    speaker_role ENUM('Healthcare Provider', 'Patient/Family', 'Unknown') DEFAULT 'Unknown',
    original_text TEXT NOT NULL,
    translated_text TEXT,
    timestamp_start DECIMAL(12,3),
    timestamp_end DECIMAL(12,3),
    confidence DECIMAL(4,3),
    enrollment_match BOOLEAN DEFAULT FALSE,
    enrollment_confidence DECIMAL(4,3),
    method VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES live_sessions(session_id) ON DELETE CASCADE,
    INDEX idx_session_id (session_id),
    INDEX idx_speaker (speaker),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Journal Entries Table
-- Permanently stores AI-generated medical visit summaries
CREATE TABLE IF NOT EXISTS journal_entries (
    entry_id VARCHAR(100) PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    user_id VARCHAR(100) NOT NULL,
    patient_name VARCHAR(255) NOT NULL,
    family_id VARCHAR(100) NOT NULL,
    
    -- Visit Information
    visit_date DATE NOT NULL,
    provider_name VARCHAR(255),
    visit_type VARCHAR(100),
    main_reason TEXT,
    
    -- Medical Details (stored as JSON for flexibility)
    symptoms TEXT,  -- JSON array
    diagnoses TEXT,  -- JSON array
    treatments TEXT,  -- JSON array
    vital_signs TEXT,  -- JSON object
    test_results TEXT,  -- JSON array
    
    -- Medications (stored as JSON array)
    medications TEXT,
    
    -- Follow-up Care
    follow_up_instructions TEXT,  -- JSON array
    next_appointments TEXT,  -- JSON array
    action_items TEXT,  -- JSON array
    
    -- Family Section
    patient_questions TEXT,  -- JSON array
    family_concerns TEXT,  -- JSON array
    family_summary TEXT,
    
    -- Medical Terms Explained
    medical_terms_explained TEXT,  -- JSON object
    
    -- Overall Summary
    visit_summary TEXT NOT NULL,
    
    -- AI Metadata
    ai_confidence DECIMAL(4,3),
    ai_model VARCHAR(100),
    processing_method VARCHAR(100),
    
    -- Privacy & Compliance
    consent_given BOOLEAN DEFAULT TRUE,
    audio_deleted BOOLEAN DEFAULT TRUE,
    transcripts_deleted BOOLEAN DEFAULT TRUE,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    FOREIGN KEY (session_id) REFERENCES live_sessions(session_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_family_id (family_id),
    INDEX idx_visit_date (visit_date),
    INDEX idx_patient_name (patient_name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Create a view for easy journal entry retrieval
CREATE OR REPLACE VIEW journal_entries_summary AS
SELECT 
    entry_id,
    session_id,
    user_id,
    patient_name,
    visit_date,
    provider_name,
    visit_type,
    main_reason,
    visit_summary,
    ai_confidence,
    created_at
FROM journal_entries
ORDER BY visit_date DESC, created_at DESC;

-- 5. Insert test data for verification (optional)
INSERT INTO live_sessions (session_id, user_id, patient_name, family_id, target_language, session_status, ended_at, total_segments, duration_seconds)
VALUES ('test-session-001', 'user-001', 'Mary Johnson', 'kris', 'vi', 'completed', NOW(), 5, 180);

INSERT INTO journal_entries (
    entry_id, session_id, user_id, patient_name, family_id,
    visit_date, provider_name, visit_type, main_reason,
    symptoms, diagnoses, treatments, vital_signs, medications,
    visit_summary, ai_confidence, ai_model
) VALUES (
    'test-entry-001',
    'test-session-001',
    'user-001',
    'Mary Johnson',
    'kris',
    CURDATE(),
    'Dr. Smith',
    'Follow-up Visit',
    'Routine checkup and medication review',
    '["No current symptoms", "Feeling well"]',
    '["Hypertension - controlled"]',
    '["Continue current medication regimen"]',
    '{"blood_pressure": "120/80", "heart_rate": "72 bpm"}',
    '[{"name": "Lisinopril", "dosage": "10mg", "frequency": "Once daily", "duration": "Ongoing"}]',
    'Patient came for routine follow-up. Blood pressure is well controlled on current medications. No new concerns raised.',
    0.92,
    'gpt-4'
);

-- 6. Verify tables were created
SHOW TABLES;

-- 7. Check test data
SELECT * FROM live_sessions WHERE session_id = 'test-session-001';
SELECT entry_id, patient_name, visit_date, visit_type FROM journal_entries WHERE entry_id = 'test-entry-001';
