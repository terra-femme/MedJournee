-- ============================================
-- MEDJOURNEE: Appointments & Talking Points
-- Run this in Supabase SQL Editor
-- ============================================

-- 1. Create appointments table
CREATE TABLE IF NOT EXISTS appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(100) NOT NULL,
    family_id VARCHAR(100) NOT NULL,

    -- Appointment details
    title VARCHAR(255) DEFAULT 'Appointment',
    scheduled_date DATE NOT NULL,
    scheduled_time TIME,                        -- Optional: NULL = "All day"
    provider_name VARCHAR(255),
    location VARCHAR(255),
    appointment_type VARCHAR(50),               -- 'checkup', 'follow-up', 'lab', 'imaging', 'specialist'

    -- Post-visit linking
    linked_entry_id VARCHAR(100) REFERENCES journal_entries(entry_id) ON DELETE SET NULL,
    linked_at TIMESTAMPTZ,

    -- Status
    status VARCHAR(20) DEFAULT 'scheduled'
        CHECK (status IN ('scheduled', 'completed', 'cancelled')),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Create talking_points table
CREATE TABLE IF NOT EXISTS talking_points (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    appointment_id UUID NOT NULL REFERENCES appointments(id) ON DELETE CASCADE,

    -- Point content
    text TEXT NOT NULL,
    category VARCHAR(30) DEFAULT 'general',     -- 'medication', 'symptoms', 'results', 'questions', 'general'
    priority VARCHAR(10) DEFAULT 'medium',      -- 'high', 'medium', 'low'

    -- Checklist state
    done BOOLEAN DEFAULT FALSE,
    checked_at TIMESTAMPTZ,

    -- Ordering
    sort_order INTEGER DEFAULT 0,

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_appointments_user_date ON appointments(user_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_appointments_family ON appointments(family_id);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_talking_points_appointment ON talking_points(appointment_id);
CREATE INDEX IF NOT EXISTS idx_talking_points_done ON talking_points(done);

-- 4. Auto-update updated_at trigger (reuse existing function if available)
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Drop triggers if they exist (to allow re-running migration)
DROP TRIGGER IF EXISTS update_appointments_updated_at ON appointments;
DROP TRIGGER IF EXISTS update_talking_points_updated_at ON talking_points;

CREATE TRIGGER update_appointments_updated_at
    BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_talking_points_updated_at
    BEFORE UPDATE ON talking_points
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- 5. Verify tables were created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('appointments', 'talking_points');
