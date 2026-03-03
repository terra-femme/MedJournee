# PWA Bug Fixes — March 2026

## Summary
8 bugs fixed + 7 hotfixes across the MedJournee PWA (Render frontend + Tailscale backend) found during live device testing.

---

## Hotfix 7 — Enrollment form family_id editable field replaced with read-only display

### Free-text family_id input replaced with locked display + optional Change toggle
**File:** `static/enrollment.html`

**Problem:** The enrollment form had a plain text `<input>` for the family group ID. A user could accidentally type anything (e.g., `'kristy'` instead of `'family-001'`), causing the enrollment to be saved under a different ID than the recording page sends. The mismatch silently broke all enrolled-speaker recognition without any error.

**Fix:**
- Replaced the editable input with a read-only display pill (`#familyIdDisplay`) showing the current family ID
- Family ID is loaded from `localStorage` (or falls back to `'family-001'`) and immediately written back, keeping enrollment and recording pages in sync
- A "✎ Change" button reveals the actual `<input>` and a warning hint below it only when the user explicitly taps it
- The button text toggles to "✓ Done" while the input is open, and back to "✎ Change" when collapsed
- `updateFamilyIdLabel()` fires on every `oninput` keystroke: updates the display label, persists to `localStorage`, and reloads the enrolled-speakers list for the new ID
- `loadEnrollments()` on init now uses the same resolved family ID, so the enrolled list is pre-populated without any user action

**New JS functions:**
- `toggleFamilyIdEdit()` — shows/hides the editable input and hint text, toggles button label
- `updateFamilyIdLabel()` — syncs input → label → localStorage → enrollment list on each keystroke

---

## Hotfix 6 — Voice enrollment family_id mismatch (enrollment never matched)

### Enrollment saved under wrong family_id, recording page used a different one
**Files:** `static/enrollment.html`, `static/record.html`
**Supabase:** Manual SQL fix required (one-time)

**Root cause:** The enrollment page had no default `family_id` — the user typed `'kristy'` into the field and the enrollment was saved under `family_id = 'kristy'`. The recording page had no localStorage value and fell back to the hardcoded default `'family-001'`. The enrollment lookup during every session queried for `family-001` and returned nothing, so the enrolled voice was never matched despite a quality score of 0.93.

**Supabase fix (one-time, run in SQL Editor):**
```sql
UPDATE voice_enrollments
SET family_id = 'family-001'
WHERE id = '69f57ce3-7d86-40c8-bd80-0b6056bf03e6';
```

**Code fix:** Both pages now share the same fallback — `localStorage` value or `'family-001'`. On load, both pages write the resolved value back to localStorage so they stay in sync going forward. Previously enrollment.html only saved to localStorage on the `change` event, so if the user navigated away without triggering a change, localStorage was never updated.

---

## Hotfix 5 — Whisper hallucinating conversational gap-fillers (`temperature=0` + medical prompt)

### Added `temperature=0` and `prompt` to Whisper API call
**File:** `agents/transcription_agent.py`

**Root cause:** Whisper's default temperature allows probabilistic output. During natural pauses in clinical conversation, Whisper was generating responses it statistically expected to follow — not what was actually said:
- Pause after "Hello, how are you?" → Whisper added "Are you okay?" (never said)
- "...what's the treatment plan" → Whisper rephrased to "Do you have a treatment plan?" (never said)

**Fix:**
- `temperature=0` — forces deterministic transcription, no creative gap-filling
- `prompt: "Medical appointment. Patient and doctor."` — short domain hint (kept under 10 words to avoid the known Whisper prompt-echo issue). Biases vocabulary toward clinical language.

---

## Hotfix 4 — Speaker labeling redesign + remove Healthcare Provider assumption

### Removed "Healthcare Provider" / "Patient/Family" role assumptions
**Files:** `agents/diarization_agent.py`, `pipeline/orchestrator.py`, `routes/realtime_routes.py`, `static/record.html`, `static/entry.html`

**Problem:** The app hardcoded SPEAKER_1 = Healthcare Provider and SPEAKER_2 = Patient/Family. In reality, any number of people can be in a room — multiple family members, nurses, doctors — so this assumption was wrong and misleading. Enrolled voices were being ignored in favor of this label.

**New behaviour:**
- Unknown speakers display as **"Speaker 1"**, **"Speaker 2"** etc. (formatted from AssemblyAI's SPEAKER_1 label)
- Enrolled speakers display as their **enrolled name** (e.g. "Kristy") with green highlight
- No more "Healthcare Provider" / "Patient/Family" labels for unidentified speakers
- Live recording shows "Speaker" for unidentified, enrolled name for matched voices
- Raw transcript stored as `"Speaker 1: ..."` / `"Kristy: ..."` instead of `"Healthcare Provider: ..."`

**Changes per file:**
- `diarization_agent.py` — `_apply_default_roles()` now sets all segments to `UNKNOWN` instead of HEALTHCARE_PROVIDER/PATIENT_FAMILY
- `orchestrator.py` — instant-transcribe no longer assigns speaker role from detected language; defaults to UNKNOWN, only overrides when enrolled match found
- `realtime_routes.py` — raw transcript builder uses enrolled name or formats "SPEAKER_1" → "Speaker 1"
- `record.html` — live display: enrolled = green + name, unknown = blue + "Speaker"
- `entry.html` — transcript: SPEAKER_N formatted to "Speaker N"; enrolled names shown in green

---

## Hotfix 3 — Whisper hallucinating conversational responses during pauses

### Added `temperature=0` and medical `initial_prompt` to Whisper API call
**File:** `agents/transcription_agent.py`

**Root cause:** Whisper's default temperature allows probabilistic/creative output. During pauses in speech (common in clinical conversations), Whisper fills the silence by completing what sounds like a natural conversational exchange:
- Pause after "Hello, how are you?" → Whisper generates "Are you okay?" (natural greeting response)
- "...what's the treatment plan" → Whisper rephrases to "Do you have a treatment plan?" (Q&A completion)

These phrases were never spoken. The previous hallucination filter only caught YouTube-style phrases, not these conversational completions.

**Fix:**
- `temperature=0` — disables probabilistic sampling entirely. Whisper becomes deterministic and only transcribes what it actually hears rather than filling gaps with probable continuations.
- `prompt: "Medical appointment. Patient and doctor."` — short domain prompt (< 10 words to avoid the known prompt-echo issue). Shifts Whisper's vocabulary bias toward clinical language instead of casual conversation patterns.

---

## Hotfix 2 — Hallucination filter false positive on medical farewells

### `see you.*next` regex blocked real speech in long transcripts
**File:** `agents/transcription_agent.py`

Log evidence: `[Hallucination Filter] Pattern blocked ('see you.*next'): 'Hello, how are you? I feel really sick today... I'll just see you next time.'`

The `see you.*next` regex was designed to catch YouTube-style hallucinations ("see you in the next video"). But it ran against the **full accumulated transcript** with no length guard. When a real medical appointment ended with "see you next time," the entire transcript was blocked — even though AssemblyAI's finalize-session correctly included the phrase in the final result.

**Fix:** Removed `see you.*next` from the general pattern list. Added a separate length-guarded check: the pattern now only fires when the full text is **< 80 characters** (i.e., a short standalone utterance, not a real multi-sentence conversation).

---

## Hotfix — Personal Notes (post-deploy)

### personal_notes column missing from live Supabase table
The `personal_notes` column was appended to the end of the `CREATE TABLE` statement in `supabase_migration.sql` after the table was originally created in Supabase. The live table never had the column added, causing all note saves to fail silently.

**Required Supabase action (run once in SQL Editor):**
```sql
ALTER TABLE journal_entries ADD COLUMN IF NOT EXISTS personal_notes TEXT;
```

**Also fixed in `static/entry.html`:** `autoSaveNotes()` was calling `showSaveIndicator()` unconditionally without checking the API response body. Now checks `result.success` and shows a red "✕ Save failed" indicator if the save fails, making errors visible to the user. `showSaveIndicator()` updated to accept an `'error'` state.

---

## HIGH Priority

### 1. Personal notes not saving + journal edit broken
**Files:** `routes/live_translation.py`

Both `PUT /live-session/update-journal/{session_id}` and `PUT /live-session/update-journal-notes/{session_id}` were calling `database_service.get_connection()` — a method that no longer exists after the migration from Google Cloud SQL to Supabase. Both endpoints were silently failing on every call.

**Fix:** Rewrote both endpoints to use `database_service.supabase.table("journal_entries").update(...).eq("session_id", ...)` directly. Preserved the date format conversion and JSON serialisation logic in `update_journal_entry`.

---

### 2. Appointment save — no feedback, no navigation
**Files:** `static/appointment.html`

After creating or updating an appointment, there was no visual confirmation and the page silently stayed in place (new) or navigated back without feedback (update). Users had no indication the save succeeded.

**Fix:**
- Added a green toast notification element (`#saveToast`) with slide-up animation.
- `showSaveToast(msg)` helper function shows the toast for 1.2 seconds.
- **New appointment:** Shows "Appointment created!" toast, then redirects to `mobile.html` after 1.4s so the calendar reloads showing the new appointment.
- **Update existing:** Shows "Appointment updated!" toast, then calls `goBack()` after 1 second.

---

### 3. Transcription hallucinations persisting on screen
**Files:** `static/record.html`

Whisper occasionally hallucinates text in one 4-second chunk (e.g. "Thank you for watching") and then retracts it in the next chunk by returning a corrected full transcript. The frontend was showing a delta-diff of each chunk, so once a hallucinated segment was displayed it stayed visible forever — even after Whisper corrected itself.

**Fix:** After each successful transcription response, scan all displayed `.segment` elements and compare their text against the new full transcript. Any segment whose text is no longer present in the latest full transcript is marked `.retracted` — visually dimmed to 35% opacity with strikethrough text and a tooltip. This prevents hallucinated text from misleading the user while preserving it for transparency.

---

### 4. Enrolled speakers not identified (Kristy shown as provider1)
**Files:** `agents/diarization_agent.py`

The post-session diarization enrollment matching threshold was 0.65 cosine similarity. The live instant-transcribe pipeline uses 0.60. The slightly higher threshold caused borderline matches to be rejected, leaving enrolled speakers with no name override.

**Fix:**
- Lowered acceptance threshold from `>= 0.65` to `>= 0.60` to align with the live pipeline.
- Added per-segment confidence logging for every enrollment attempt: speaker ID, segment duration, matched name, and confidence score. This makes it much easier to diagnose future matching issues from backend logs.

---

## MEDIUM Priority

### 5. Hamburger "Today" leads nowhere
**Files:** `static/mobile.html`

`goToToday()` re-rendered the calendar and highlighted today's date but never opened the day modal showing today's appointments. The user tapped "Today" and nothing visibly happened.

**Fix:** Added `openDayModal(selectedDate)` call at the end of `goToToday()`, matching the behaviour of tapping a day directly on the calendar.

---

### 6. Recent journal entries showing wrong date (off by 1 day)
**Files:** `static/mobile.html`

`createEntryCard()` used `new Date(entry.date)` where `entry.date` is a plain ISO date string like `"2025-10-01"`. JavaScript parses plain date-only strings as UTC midnight. In any timezone west of UTC (e.g. EST = UTC-5), midnight UTC becomes 7 PM the previous day locally, causing `getDate()` to return the day before.

**Fix:** Changed to `new Date(entry.date + 'T00:00:00')` which forces the date to be parsed in the device's local timezone.

---

## LOW Priority

### 7. White background visible when scrolling to bottom of page
**Files:** `static/css/neuglass.css`

`body` had a gradient background with `min-height: 100vh` but no `background-attachment: fixed`. When content exceeded the viewport height, the gradient was painted at content height and the browser showed white below it on scroll.

**Fix:** Added `background-attachment: fixed` to the `body` rule. The gradient stays pinned to the viewport while content scrolls over it.

---

### 8. No explicit save button on journal entry page
**Files:** `static/entry.html`

The entry page used auto-save (debounced) but had no visible save button in the action bar. Users had no manual way to confirm their edits were persisted.

**Fix:** Added a "Save" button to the `#actionBar` that calls `saveAllChanges()`. Styled to match the existing glass design (green tint, rounded pill).

---

## Files Modified

| File | Change |
|------|--------|
| `routes/live_translation.py` | Rewrote `update_journal_entry` + `update_journal_notes` to use Supabase |
| `static/appointment.html` | Added save toast + post-save navigation |
| `static/record.html` | Retracted hallucinated segments visual indicator |
| `agents/diarization_agent.py` | Lowered enrollment threshold 0.65 → 0.60, added confidence logging |
| `static/mobile.html` | `goToToday()` now opens day modal; fixed date timezone in `createEntryCard()` |
| `static/entry.html` | Added explicit Save button to action bar |
| `static/css/neuglass.css` | Added `background-attachment: fixed` to body |
