# agents/summarization_agent.py
"""
AGENT 5: SUMMARIZATION AGENT

Converts diarized + translated segments into structured journal entry.

Input: List of TranslatedSegment
Output: SummarizationResult with JournalEntry

Rules:
- Never hallucinate information not in transcript
- If unclear, say "Not mentioned" or "Unclear from conversation"
- Always include family_summary in plain language
"""

import openai
import os
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

from models.schemas import (
    SummarizationResult,
    JournalEntry,
    Medication,
    Appointment,
    MedicalTerm,
    TranslatedSegment,
    SpeakerRole,
    TermSource
)

load_dotenv()


class SummarizationAgent:
    """
    Generates structured medical journal entries from conversation segments.

    Usage:
        agent = SummarizationAgent()
        result = await agent.summarize(translated_segments, patient_name="Grandma")

        if result.success:
            journal = result.journal_entry
            print(journal.family_summary)
    """

    SYSTEM_PROMPT = """You are MedJournee, a privacy-first medical journaling assistant for families.

Your role:
- Convert medical visit transcripts into structured, family-friendly journal entries
- NEVER act as a doctor or provide diagnoses
- NEVER invent information not present in the transcript

Core behaviors:
- No hallucinations: If something is unclear or missing, say "Not mentioned"
- Plain language: Explain medical terms simply
- Speaker awareness: SPEAKER_1 = Healthcare Provider, SPEAKER_2 = Patient/Family

Output ONLY valid JSON matching this exact schema - no markdown, no explanation:
{
    "visit_type": "routine checkup/follow-up/urgent care/emergency/consultation",
    "chief_complaint": "main reason for visit",
    "symptoms": ["symptom1", "symptom2"],
    "diagnoses": ["diagnosis1", "diagnosis2"],
    "treatments": ["treatment1", "treatment2"],
    "medications": [
        {"name": "medication name", "dosage": "amount", "frequency": "how often", "duration": "how long"}
    ],
    "vital_signs": {"blood_pressure": "value", "temperature": "value"},
    "follow_up_instructions": ["instruction1", "instruction2"],
    "next_appointments": ["appointment1", "appointment2"],
    "patient_questions": ["question asked by patient/family"],
    "family_concerns": ["concern expressed by family"],
    "action_items": ["what patient needs to do"],
    "family_summary": "Plain language summary of the visit for family members",
    "confidence_notes": "Any uncertainties or missing information"
}

ONLY include information actually mentioned in the conversation. For missing fields, use empty arrays [] or empty strings ""."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment")

        self.client = openai.OpenAI(api_key=self.api_key)

    async def summarize(
        self,
        segments: List[TranslatedSegment],
        patient_name: Optional[str] = None,
        medical_terms: Optional[List[MedicalTerm]] = None
    ) -> SummarizationResult:
        """
        Generate structured journal entry from conversation segments.

        Args:
            segments: List of translated speaker segments
            patient_name: Optional patient name
            medical_terms: Optional pre-detected medical terms

        Returns:
            SummarizationResult with JournalEntry
        """
        if not segments:
            return SummarizationResult(
                success=False,
                error="No segments provided"
            )

        try:
            transcript = self._format_transcript(segments)
            prompt = self._build_prompt(transcript, patient_name)

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            ai_response = response.choices[0].message.content
            extracted = self._parse_response(ai_response)

            journal_entry = self._build_journal_entry(
                extracted,
                patient_name,
                medical_terms
            )

            confidence = self._calculate_confidence(journal_entry)

            return SummarizationResult(
                success=True,
                journal_entry=journal_entry,
                confidence_score=confidence
            )

        except openai.APIError as e:
            return SummarizationResult(
                success=False,
                error=f"OpenAI API error: {str(e)}"
            )
        except Exception as e:
            fallback = self._create_fallback_entry(segments, patient_name)
            return SummarizationResult(
                success=True,
                journal_entry=fallback,
                confidence_score=0.3,
                error=f"Used fallback due to: {str(e)}"
            )

    def _format_transcript(self, segments: List[TranslatedSegment]) -> str:
        """Format segments into readable transcript"""
        lines = []

        for seg in segments:
            role = "PROVIDER" if seg.speaker == "SPEAKER_1" else "PATIENT/FAMILY"
            lines.append(f"[{role}]: {seg.text}")

            if seg.translation and seg.translation != seg.text:
                lines.append(f"  (Translation: {seg.translation})")

        return "\n".join(lines)

    def _build_prompt(self, transcript: str, patient_name: Optional[str]) -> str:
        """Build the extraction prompt"""
        patient_context = f"Patient name: {patient_name}\n" if patient_name else ""

        return f"""{patient_context}
MEDICAL VISIT TRANSCRIPT:
{transcript}

Extract the medical information from this conversation and return ONLY valid JSON.
Remember: Only include information actually mentioned. Use empty arrays/strings for missing information."""

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse GPT response into dictionary"""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return {
            "visit_type": "medical visit",
            "chief_complaint": "",
            "symptoms": [],
            "diagnoses": [],
            "treatments": [],
            "medications": [],
            "vital_signs": {},
            "follow_up_instructions": [],
            "next_appointments": [],
            "patient_questions": [],
            "family_concerns": [],
            "action_items": [],
            "family_summary": "Medical visit completed.",
            "confidence_notes": "Could not parse AI response"
        }

    def _build_journal_entry(
        self,
        extracted: Dict[str, Any],
        patient_name: Optional[str],
        medical_terms: Optional[List[MedicalTerm]]
    ) -> JournalEntry:
        """Build JournalEntry from extracted data"""
        medications = []
        for med in extracted.get("medications", []):
            if isinstance(med, dict):
                medications.append(Medication(
                    name=med.get("name", "Unknown"),
                    dosage=med.get("dosage"),
                    frequency=med.get("frequency"),
                    duration=med.get("duration")
                ))
            elif isinstance(med, str):
                medications.append(Medication(name=med))

        appointments = []
        for appt in extracted.get("next_appointments", []):
            if isinstance(appt, dict):
                appointments.append(Appointment(
                    type=appt.get("type", "Follow-up"),
                    date=appt.get("date"),
                    provider=appt.get("provider")
                ))
            elif isinstance(appt, str):
                appointments.append(Appointment(type=appt))

        entry = JournalEntry(
            visit_date=datetime.now().strftime("%Y-%m-%d"),
            visit_type=extracted.get("visit_type", "Medical Visit"),
            patient_name=patient_name,
            chief_complaint=extracted.get("chief_complaint", ""),
            symptoms=extracted.get("symptoms", []),
            diagnoses=extracted.get("diagnoses", []),
            treatments=extracted.get("treatments", []),
            medications=medications,
            vital_signs=extracted.get("vital_signs", {}),
            follow_up_instructions=extracted.get("follow_up_instructions", []),
            next_appointments=appointments,
            action_items=extracted.get("action_items", []),
            patient_questions=extracted.get("patient_questions", []),
            family_concerns=extracted.get("family_concerns", []),
            family_summary=extracted.get("family_summary", "Medical visit completed."),
            medical_terms=medical_terms or [],
            processing_notes=[extracted.get("confidence_notes", "")]
        )

        return entry

    def _calculate_confidence(self, entry: JournalEntry) -> float:
        """Calculate confidence score"""
        score = 0.3

        if entry.chief_complaint:
            score += 0.1
        if entry.symptoms:
            score += 0.1
        if entry.diagnoses:
            score += 0.1
        if entry.treatments:
            score += 0.1
        if entry.medications:
            score += 0.1
        if entry.follow_up_instructions:
            score += 0.1
        if entry.family_summary and len(entry.family_summary) > 20:
            score += 0.1

        return min(1.0, score)

    def _create_fallback_entry(
        self,
        segments: List[TranslatedSegment],
        patient_name: Optional[str]
    ) -> JournalEntry:
        """Create basic entry when AI processing fails"""
        all_text = " ".join([s.text for s in segments])
        preview = all_text[:500] + "..." if len(all_text) > 500 else all_text

        return JournalEntry(
            visit_date=datetime.now().strftime("%Y-%m-%d"),
            visit_type="Medical Visit",
            patient_name=patient_name,
            chief_complaint="Medical consultation",
            family_summary=f"Medical visit with {len(segments)} conversation segments. Full transcript: {preview}",
            processing_notes=["Fallback entry - AI extraction failed"]
        )

    async def self_correct(
        self,
        original_result: SummarizationResult,
        segments: List[TranslatedSegment],
        issues: List[str]
    ) -> SummarizationResult:
        """
        Self-correction: Attempt to fix issues identified by quality gates.

        Args:
            original_result: The original summarization result
            segments: Original transcript segments
            issues: List of issues identified by validator

        Returns:
            Improved SummarizationResult
        """
        if not original_result.journal_entry:
            # No journal entry to correct, try fresh
            return await self.summarize(segments, original_result.journal_entry.patient_name if original_result.journal_entry else None)

        try:
            # Build correction prompt
            original_json = {
                "visit_type": original_result.journal_entry.visit_type,
                "chief_complaint": original_result.journal_entry.chief_complaint,
                "symptoms": original_result.journal_entry.symptoms,
                "diagnoses": original_result.journal_entry.diagnoses,
                "treatments": original_result.journal_entry.treatments,
                "family_summary": original_result.journal_entry.family_summary,
            }

            correction_prompt = f"""You previously generated this journal entry but it has quality issues:

ORIGINAL OUTPUT:
{json.dumps(original_json, indent=2)}

ISSUES TO FIX:
{chr(10).join(f"- {issue}" for issue in issues)}

ORIGINAL TRANSCRIPT:
{self._format_transcript(segments)}

Please generate an IMPROVED journal entry that addresses these issues.
Output ONLY valid JSON matching the original schema."""

            response = self.client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": correction_prompt}
                ],
                temperature=0.2,
                max_tokens=2000
            )

            ai_response = response.choices[0].message.content
            extracted = self._parse_response(ai_response)

            corrected_entry = self._build_journal_entry(
                extracted,
                original_result.journal_entry.patient_name,
                original_result.journal_entry.medical_terms
            )

            confidence = self._calculate_confidence(corrected_entry)

            return SummarizationResult(
                success=True,
                journal_entry=corrected_entry,
                confidence_score=confidence
            )

        except Exception as e:
            # If self-correction fails, return original
            print(f"Self-correction failed: {e}")
            return original_result


# =============================================================================
# STANDALONE FUNCTION
# =============================================================================

_agent: Optional[SummarizationAgent] = None


def get_agent() -> SummarizationAgent:
    """Get or create the global summarization agent"""
    global _agent
    if _agent is None:
        _agent = SummarizationAgent()
    return _agent


async def generate_journal_entry(
    segments: List[Dict],
    patient_info: Optional[Dict] = None
) -> Dict:
    """Backward-compatible function"""
    agent = get_agent()

    typed_segments = []
    for s in segments:
        typed_segments.append(TranslatedSegment(
            speaker=s.get("speaker", "SPEAKER_1"),
            speaker_role=SpeakerRole(s.get("speaker_role", "Unknown")),
            text=s.get("text", ""),
            detected_language=s.get("detected_language", ""),
            start_time=s.get("start_time", 0),
            end_time=s.get("end_time", 0),
            confidence=s.get("confidence", 0.8),
            translation=s.get("translation", "")
        ))

    patient_name = None
    if patient_info:
        patient_name = patient_info.get("name")

    result = await agent.summarize(typed_segments, patient_name)

    if result.success and result.journal_entry:
        entry = result.journal_entry
        return {
            "success": True,
            "journal_entry": {
                "entry_type": "medical_visit",
                "visit_information": {
                    "date": entry.visit_date,
                    "provider": entry.provider_name or "Healthcare Provider",
                    "visit_type": entry.visit_type,
                    "main_reason": entry.chief_complaint
                },
                "medical_details": {
                    "symptoms": entry.symptoms,
                    "diagnoses": entry.diagnoses,
                    "treatments": entry.treatments,
                    "vital_signs": entry.vital_signs,
                    "test_results": entry.test_results
                },
                "medications": [
                    {"name": m.name, "dosage": m.dosage, "frequency": m.frequency, "duration": m.duration}
                    for m in entry.medications
                ],
                "follow_up_care": {
                    "instructions": entry.follow_up_instructions,
                    "appointments": [{"type": a.type, "date": a.date} for a in entry.next_appointments],
                    "action_items": entry.action_items
                },
                "family_section": {
                    "patient_questions": entry.patient_questions,
                    "family_concerns": entry.family_concerns,
                    "notes_for_family": entry.family_summary
                },
                "medical_terms_explained": {
                    t.term: {"simple": t.simple, "explanation": t.explanation}
                    for t in entry.medical_terms
                },
                "summary": entry.family_summary
            },
            "confidence_score": result.confidence_score,
            "medical_terms_detected": len(entry.medical_terms)
        }
    else:
        return {
            "success": False,
            "error": result.error,
        }
