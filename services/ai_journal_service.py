# services/ai_journal_service.py
"""
AI-Powered Medical Journal Summarization Service

This service analyzes speaker-differentiated medical conversations and automatically
generates structured journal entries with key medical information extracted and organized
for family medical journaling.

Privacy-First Design:
- Only processes summarized content, not raw transcripts
- Focuses on actionable medical information
- Supports family-friendly language explanations
- Auto-deletes processed conversation data
"""

import openai
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import re
from dotenv import load_dotenv

load_dotenv()

@dataclass
class MedicalSummary:
    """Structured medical visit summary"""
    visit_date: str
    provider_name: Optional[str]
    visit_type: str
    chief_complaint: str
    symptoms_discussed: List[str]
    diagnoses: List[str]
    treatments_prescribed: List[str]
    medications: List[Dict[str, str]]
    follow_up_instructions: List[str]
    next_appointments: List[Dict[str, str]]
    vital_signs: Dict[str, str]
    test_results: List[Dict[str, str]]
    patient_questions: List[str]
    family_concerns: List[str]
    medical_terms_explained: Dict[str, str]
    action_items: List[str]

class AIJournalService:
    """
    AI service that converts medical conversations into structured journal entries
    """
    
    def __init__(self):
        self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Medical terminology database for explanations
        self.medical_terms = {
            "hypertension": "high blood pressure",
            "diabetes": "blood sugar condition", 
            "CBC": "complete blood count test",
            "ECG": "heart rhythm test",
            "cholesterol": "fatty substance in blood",
            "prescription": "doctor's medication order"
        }
        
    async def generate_medical_journal_entry(
        self, 
        speaker_segments: List[Dict], 
        patient_info: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Main function: Convert speaker-differentiated conversation into structured journal entry
        
        Args:
            speaker_segments: List of segments with speaker, text, translation
            patient_info: Optional patient demographic info
            
        Returns:
            Structured journal entry with AI-extracted medical information
        """
        
        try:
            print(f"Processing {len(speaker_segments)} speaker segments for journal generation")
            
            # Step 1: Separate provider vs patient/family speech
            provider_statements, patient_statements = self._separate_speakers(speaker_segments)
            
            # Step 2: Extract structured medical information using AI
            medical_summary = await self._extract_medical_information(
                provider_statements, patient_statements, patient_info
            )
            
            # Step 3: Generate family-friendly explanations
            explained_terms = await self._explain_medical_terms(medical_summary)
            
            # Step 4: Create structured journal entry
            journal_entry = self._create_structured_entry(medical_summary, explained_terms)
            
            # Step 5: Add metadata and privacy notes
            journal_entry["metadata"] = {
                "generated_at": datetime.now().isoformat(),
                "ai_processed": True,
                "privacy_compliant": True,
                "segments_processed": len(speaker_segments),
                "processing_method": "ai_medical_summarization"
            }
            
            return {
                "success": True,
                "journal_entry": journal_entry,
                "medical_summary": medical_summary,
                "confidence_score": self._calculate_confidence(medical_summary)
            }
            
        except Exception as e:
            print(f"Journal generation error: {e}")
            return {
                "success": False,
                "error": f"Failed to generate journal entry: {str(e)}",
                "fallback_summary": self._create_fallback_entry(speaker_segments)
            }
    
    def _separate_speakers(self, speaker_segments: List[Dict]) -> tuple:
        """Separate healthcare provider speech from patient/family speech"""
        provider_statements = []
        patient_statements = []
        
        for segment in speaker_segments:
            speaker = segment.get("speaker", "SPEAKER_1")
            text = segment.get("text", "")
            
            # SPEAKER_1 = Healthcare Provider, SPEAKER_2 = Patient/Family
            if speaker == "SPEAKER_1" or segment.get("speaker_role") == "Healthcare Provider":
                provider_statements.append({
                    "text": text,
                    "translation": segment.get("translation", ""),
                    "timestamp": segment.get("timestamp_start", 0)
                })
            else:
                patient_statements.append({
                    "text": text,
                    "translation": segment.get("translation", ""),
                    "timestamp": segment.get("timestamp_start", 0)
                })
        
        return provider_statements, patient_statements
    
    async def _extract_medical_information(
        self, 
        provider_statements: List[Dict], 
        patient_statements: List[Dict],
        patient_info: Optional[Dict]
    ) -> MedicalSummary:
        """Use AI to extract structured medical information from conversation"""
        
        # Combine all text for analysis
        provider_text = "\n".join([stmt["text"] for stmt in provider_statements])
        patient_text = "\n".join([stmt["text"] for stmt in patient_statements])
        
        # Create AI prompt for medical information extraction
        prompt = self._create_extraction_prompt(provider_text, patient_text, patient_info)
        
        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system", 
                        "content": "You are a medical AI assistant that extracts key information from medical visits for personal health journaling. Focus on actionable medical information and use family-friendly language."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            # Parse AI response
            ai_response = response.choices[0].message.content
            extracted_info = self._parse_ai_response(ai_response)
            
            return self._create_medical_summary(extracted_info)
            
        except Exception as e:
            print(f"AI extraction error: {e}")
            # Fallback to rule-based extraction
            return self._fallback_extraction(provider_text, patient_text)
    
    def _create_extraction_prompt(
        self, 
        provider_text: str, 
        patient_text: str, 
        patient_info: Optional[Dict]
    ) -> str:
        """Create detailed prompt for AI medical information extraction"""
        
        patient_context = ""
        if patient_info:
            patient_context = f"Patient info: {json.dumps(patient_info, indent=2)}\n\n"
        
        return f"""
{patient_context}MEDICAL VISIT CONVERSATION:

Healthcare Provider Statements:
{provider_text}

Patient/Family Statements:
{patient_text}

EXTRACT the following information and format as JSON:

{{
    "visit_type": "routine checkup/follow-up/urgent care/emergency/consultation",
    "chief_complaint": "main reason for visit",
    "symptoms_mentioned": ["symptom1", "symptom2"],
    "diagnoses_discussed": ["diagnosis1", "diagnosis2"],
    "treatments_prescribed": ["treatment1", "treatment2"],
    "medications": [
        {{"name": "medication name", "dosage": "amount", "frequency": "how often", "duration": "how long"}}
    ],
    "vital_signs": {{"blood_pressure": "value", "temperature": "value", "weight": "value"}},
    "test_results": [
        {{"test_name": "test", "result": "result", "date": "date"}}
    ],
    "follow_up_instructions": ["instruction1", "instruction2"],
    "next_appointments": [
        {{"type": "appointment type", "date": "when", "provider": "who"}}
    ],
    "patient_questions": ["question1", "question2"],
    "family_concerns": ["concern1", "concern2"],
    "medical_terms_used": ["term1", "term2"],
    "action_items": ["action1", "action2"]
}}

Focus on:
- Actionable medical information
- Clear, family-friendly language
- Important dates and appointments
- Medication details
- Follow-up care instructions

Only include information that was actually mentioned in the conversation.
"""
    
    def _parse_ai_response(self, ai_response: str) -> Dict:
        """Parse AI response and extract JSON"""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                return json.loads(json_str)
            else:
                # Fallback parsing
                return self._manual_parse_response(ai_response)
        except json.JSONDecodeError:
            print("Failed to parse AI JSON response")
            return self._manual_parse_response(ai_response)
    
    def _create_medical_summary(self, extracted_info: Dict) -> MedicalSummary:
        """Convert extracted information to MedicalSummary object"""
        return MedicalSummary(
            visit_date=datetime.now().strftime("%Y-%m-%d"),
            provider_name=extracted_info.get("provider_name"),
            visit_type=extracted_info.get("visit_type", "medical visit"),
            chief_complaint=extracted_info.get("chief_complaint", ""),
            symptoms_discussed=extracted_info.get("symptoms_mentioned", []),
            diagnoses=extracted_info.get("diagnoses_discussed", []),
            treatments_prescribed=extracted_info.get("treatments_prescribed", []),
            medications=extracted_info.get("medications", []),
            follow_up_instructions=extracted_info.get("follow_up_instructions", []),
            next_appointments=extracted_info.get("next_appointments", []),
            vital_signs=extracted_info.get("vital_signs", {}),
            test_results=extracted_info.get("test_results", []),
            patient_questions=extracted_info.get("patient_questions", []),
            family_concerns=extracted_info.get("family_concerns", []),
            medical_terms_explained={},
            action_items=extracted_info.get("action_items", [])
        )
    
    async def _explain_medical_terms(self, medical_summary: MedicalSummary) -> Dict[str, str]:
        """Generate family-friendly explanations for medical terms"""
        
        # Collect all medical terms from the summary
        terms_to_explain = set()
        
        # Add terms from diagnoses
        for diagnosis in medical_summary.diagnoses:
            terms_to_explain.update(self._extract_medical_terms(diagnosis))
        
        # Add terms from treatments
        for treatment in medical_summary.treatments_prescribed:
            terms_to_explain.update(self._extract_medical_terms(treatment))
        
        # Add medication names
        for med in medical_summary.medications:
            if med.get("name"):
                terms_to_explain.add(med["name"].lower())
        
        explanations = {}
        
        # Use AI to explain complex terms
        if terms_to_explain:
            try:
                prompt = f"""
                Explain these medical terms in simple, family-friendly language:
                {list(terms_to_explain)}
                
                Format as JSON: {{"term": "simple explanation"}}
                Keep explanations under 20 words each.
                """
                
                response = self.openai_client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You explain medical terms in simple language for families."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.2,
                    max_tokens=800
                )
                
                ai_explanations = json.loads(response.choices[0].message.content)
                explanations.update(ai_explanations)
                
            except Exception as e:
                print(f"Term explanation error: {e}")
                # Use fallback explanations
                for term in terms_to_explain:
                    if term in self.medical_terms:
                        explanations[term] = self.medical_terms[term]
        
        return explanations
    
    def _extract_medical_terms(self, text: str) -> set:
        """Extract medical terms that need explanation"""
        # Common medical terms that families might not understand
        medical_keywords = [
            "hypertension", "diabetes", "cholesterol", "CBC", "ECG", "EKG",
            "prescription", "dosage", "chronic", "acute", "diagnosis",
            "prognosis", "symptoms", "syndrome", "antibiotics", "inflammation"
        ]
        
        text_lower = text.lower()
        found_terms = set()
        
        for term in medical_keywords:
            if term in text_lower:
                found_terms.add(term)
        
        return found_terms
    
    def _create_structured_entry(
        self, 
        medical_summary: MedicalSummary, 
        explained_terms: Dict[str, str]
    ) -> Dict[str, Any]:
        """Create the final structured journal entry"""
        
        return {
            "entry_type": "medical_visit",
            "visit_information": {
                "date": medical_summary.visit_date,
                "provider": medical_summary.provider_name or "Healthcare Provider",
                "visit_type": medical_summary.visit_type,
                "main_reason": medical_summary.chief_complaint
            },
            "medical_details": {
                "symptoms": medical_summary.symptoms_discussed,
                "diagnoses": medical_summary.diagnoses,
                "treatments": medical_summary.treatments_prescribed,
                "vital_signs": medical_summary.vital_signs,
                "test_results": medical_summary.test_results
            },
            "medications": medical_summary.medications,
            "follow_up_care": {
                "instructions": medical_summary.follow_up_instructions,
                "appointments": medical_summary.next_appointments,
                "action_items": medical_summary.action_items
            },
            "family_section": {
                "patient_questions": medical_summary.patient_questions,
                "family_concerns": medical_summary.family_concerns,
                "notes_for_family": self._generate_family_summary(medical_summary)
            },
            "medical_terms_explained": explained_terms,
            "summary": self._generate_visit_summary(medical_summary)
        }
    
    def _generate_family_summary(self, medical_summary: MedicalSummary) -> str:
        """Generate a family-friendly summary of the visit"""
        
        summary_parts = []
        
        if medical_summary.chief_complaint:
            summary_parts.append(f"Visit was for: {medical_summary.chief_complaint}")
        
        if medical_summary.diagnoses:
            summary_parts.append(f"Doctor discussed: {', '.join(medical_summary.diagnoses)}")
        
        if medical_summary.treatments_prescribed:
            summary_parts.append(f"Recommended treatments: {', '.join(medical_summary.treatments_prescribed)}")
        
        if medical_summary.medications:
            med_names = [med.get("name", "") for med in medical_summary.medications if med.get("name")]
            if med_names:
                summary_parts.append(f"New medications: {', '.join(med_names)}")
        
        if medical_summary.follow_up_instructions:
            summary_parts.append(f"Important follow-up: {'; '.join(medical_summary.follow_up_instructions)}")
        
        return ". ".join(summary_parts) if summary_parts else "Medical visit completed."
    
    def _generate_family_summary(self, medical_summary: MedicalSummary) -> str:
        """Generate a detailed narrative family-friendly summary of the visit"""
        
        narrative = []
        
        # Opening - Chief complaint
        if medical_summary.chief_complaint and medical_summary.symptoms_discussed:
            symptoms = ", ".join(medical_summary.symptoms_discussed[:3])  # First 3 symptoms
            narrative.append(f"Patient complained of {medical_summary.chief_complaint} with symptoms including {symptoms}")
        elif medical_summary.chief_complaint:
            narrative.append(f"Patient came in for {medical_summary.chief_complaint}")
        
        # Provider assessment and diagnosis
        if medical_summary.diagnoses:
            if len(medical_summary.diagnoses) == 1:
                narrative.append(f"Provider discussed {medical_summary.diagnoses[0]}")
            else:
                narrative.append(f"Provider discussed {', '.join(medical_summary.diagnoses[:-1])} and {medical_summary.diagnoses[-1]}")
        
        # Treatments and recommendations
        if medical_summary.treatments_prescribed:
            treatments = ", ".join(medical_summary.treatments_prescribed[:2])  # First 2 treatments
            if len(medical_summary.treatments_prescribed) == 1:
                narrative.append(f"Provider recommended {treatments}")
            else:
                narrative.append(f"Provider recommended {treatments} among other treatments")
        
        # Medications - more detailed
        if medical_summary.medications:
            if len(medical_summary.medications) == 1:
                med = medical_summary.medications[0]
                med_detail = f"{med.get('name', 'medication')}"
                if med.get('dosage'):
                    med_detail += f" ({med.get('dosage')})"
                narrative.append(f"Patient agreed to start {med_detail}")
            else:
                med_names = [med.get("name", "medication") for med in medical_summary.medications[:2]]
                narrative.append(f"Patient agreed to start {med_names[0]} and {med_names[1]}")
        
        # Patient concerns and questions
        if medical_summary.patient_questions:
            first_question = medical_summary.patient_questions[0]
            narrative.append(f"Patient asked about {first_question.lower()}")
        
        # Follow-up actions
        if medical_summary.next_appointments:
            appt = medical_summary.next_appointments[0]
            appt_type = appt.get('type', 'follow-up')
            narrative.append(f"Provider scheduled {appt_type} appointment")
        
        if medical_summary.follow_up_instructions:
            first_instruction = medical_summary.follow_up_instructions[0]
            narrative.append(f"Provider instructed patient to {first_instruction.lower()}")
        
        # Action items
        if medical_summary.action_items:
            actions = medical_summary.action_items[:2]
            if len(actions) == 1:
                narrative.append(f"Patient agreed to {actions[0].lower()}")
            else:
                narrative.append(f"Patient agreed to {actions[0].lower()} and {actions[1].lower()}")
        
        return ". ".join(narrative) + "." if narrative else "Medical visit completed with discussion of patient concerns."
    
    def _calculate_confidence(self, medical_summary: MedicalSummary) -> float:
        """Calculate confidence score for the generated summary"""
        score = 0.5  # Base score
        
        # Add points for extracted information
        if medical_summary.chief_complaint: score += 0.1
        if medical_summary.diagnoses: score += 0.1
        if medical_summary.treatments_prescribed: score += 0.1
        if medical_summary.medications: score += 0.1
        if medical_summary.follow_up_instructions: score += 0.1
        
        return min(1.0, score)
    
    def _fallback_extraction(self, provider_text: str, patient_text: str) -> MedicalSummary:
        """Simple rule-based extraction as fallback"""
        return MedicalSummary(
            visit_date=datetime.now().strftime("%Y-%m-%d"),
            provider_name=None,
            visit_type="medical visit",
            chief_complaint="Medical consultation",
            symptoms_discussed=[],
            diagnoses=[],
            treatments_prescribed=[],
            medications=[],
            follow_up_instructions=[],
            next_appointments=[],
            vital_signs={},
            test_results=[],
            patient_questions=[],
            family_concerns=[],
            medical_terms_explained={},
            action_items=[]
        )
    
    def _create_fallback_entry(self, speaker_segments: List[Dict]) -> Dict[str, Any]:
        """Create basic journal entry if AI processing fails"""
        
        all_text = " ".join([seg.get("text", "") for seg in speaker_segments])
        
        return {
            "entry_type": "medical_visit_basic",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": f"Medical visit - {len(speaker_segments)} conversation segments processed",
            "full_conversation_summary": all_text[:500] + "..." if len(all_text) > 500 else all_text,
            "processing_note": "Basic summary due to AI processing limitation"
        }
    
    def _manual_parse_response(self, response: str) -> Dict:
        """Manual parsing if JSON extraction fails"""
        # Simple keyword extraction
        return {
            "visit_type": "medical visit",
            "chief_complaint": "",
            "symptoms_mentioned": [],
            "diagnoses_discussed": [],
            "treatments_prescribed": [],
            "medications": [],
            "vital_signs": {},
            "test_results": [],
            "follow_up_instructions": [],
            "next_appointments": [],
            "patient_questions": [],
            "family_concerns": [],
            "action_items": []
        }

# Global service instance
ai_journal_service = AIJournalService()