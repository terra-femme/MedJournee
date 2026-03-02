# agents/terminology_agent.py
"""
AGENT 4: TERMINOLOGY AGENT

Detects medical terms and provides plain-language explanations.

Input: Text (transcript or journal entry)
Output: TerminologyResult with detected terms and explanations

Strategy:
1. Check UofM Plain Language Medical Dictionary (FREE, offline)
2. All explanations must be family-friendly (8th grade reading level)
"""

import re
from typing import Optional, List, Set
from difflib import SequenceMatcher

from models.schemas import (
    TerminologyResult,
    MedicalTerm,
    TermSource
)


class TerminologyAgent:
    """
    Detects and explains medical terms using UofM Plain Language Dictionary.

    Usage:
        agent = TerminologyAgent()
        result = await agent.detect_and_explain("Patient has hypertension and diabetes.")

        for term in result.terms_found:
            print(f"{term.term}: {term.simple}")
    """

    # UofM PLAIN LANGUAGE MEDICAL DICTIONARY
    MEDICAL_DICTIONARY = {
        # Cardiovascular
        "hypertension": {
            "simple": "high blood pressure",
            "explanation": "When the force of blood pushing against your artery walls is too high. This can damage your heart over time.",
            "category": "cardiovascular"
        },
        "hypotension": {
            "simple": "low blood pressure",
            "explanation": "When blood pressure is lower than normal. Can cause dizziness when standing up.",
            "category": "cardiovascular"
        },
        "cholesterol": {
            "simple": "fat in your blood",
            "explanation": "A waxy substance in your blood. Too much can clog arteries and lead to heart problems.",
            "category": "cardiovascular"
        },
        "ldl": {
            "simple": "bad cholesterol",
            "explanation": "Low-density lipoprotein - the type of cholesterol that can build up in your arteries.",
            "category": "cardiovascular"
        },
        "hdl": {
            "simple": "good cholesterol",
            "explanation": "High-density lipoprotein - helps remove bad cholesterol from your blood.",
            "category": "cardiovascular"
        },
        "arrhythmia": {
            "simple": "irregular heartbeat",
            "explanation": "When your heart beats too fast, too slow, or with an irregular pattern.",
            "category": "cardiovascular"
        },
        "tachycardia": {
            "simple": "fast heartbeat",
            "explanation": "Heart rate faster than 100 beats per minute at rest.",
            "category": "cardiovascular"
        },
        "bradycardia": {
            "simple": "slow heartbeat",
            "explanation": "Heart rate slower than 60 beats per minute.",
            "category": "cardiovascular"
        },

        # Metabolic
        "diabetes": {
            "simple": "high blood sugar disease",
            "explanation": "A condition where your body has trouble controlling blood sugar levels.",
            "category": "metabolic"
        },
        "diabetes mellitus": {
            "simple": "sugar diabetes",
            "explanation": "The medical name for diabetes - when your body can't properly use sugar from food.",
            "category": "metabolic"
        },
        "prediabetes": {
            "simple": "early warning of diabetes",
            "explanation": "Blood sugar is higher than normal but not high enough to be diabetes.",
            "category": "metabolic"
        },
        "glucose": {
            "simple": "blood sugar",
            "explanation": "The main type of sugar in your blood that your body uses for energy.",
            "category": "metabolic"
        },
        "insulin": {
            "simple": "blood sugar hormone",
            "explanation": "A hormone that helps your body use sugar from food for energy.",
            "category": "metabolic"
        },

        # Blood
        "anemia": {
            "simple": "low red blood cells",
            "explanation": "Not having enough healthy red blood cells to carry oxygen to your body.",
            "category": "blood"
        },
        "hemoglobin": {
            "simple": "oxygen carrier in blood",
            "explanation": "The protein in red blood cells that carries oxygen throughout your body.",
            "category": "blood"
        },

        # Tests
        "ecg": {
            "simple": "heart rhythm test",
            "explanation": "Electrocardiogram - a test that records the electrical activity of your heart.",
            "category": "test"
        },
        "ekg": {
            "simple": "heart rhythm test",
            "explanation": "Same as ECG - electrocardiogram. Tests your heart's electrical activity.",
            "category": "test"
        },
        "mri": {
            "simple": "detailed body scan",
            "explanation": "Magnetic resonance imaging - uses magnets to create detailed pictures inside your body.",
            "category": "test"
        },
        "ct scan": {
            "simple": "detailed X-ray",
            "explanation": "Computed tomography - combines many X-ray images to create detailed pictures.",
            "category": "test"
        },
        "cbc": {
            "simple": "blood cell count test",
            "explanation": "Complete blood count - measures red cells, white cells, and platelets.",
            "category": "test"
        },
        "a1c": {
            "simple": "average blood sugar test",
            "explanation": "A blood test showing your average blood sugar over the past 2-3 months.",
            "category": "test"
        },
        "biopsy": {
            "simple": "tissue sample test",
            "explanation": "Removing a small piece of tissue to examine under a microscope.",
            "category": "test"
        },
        "ultrasound": {
            "simple": "sound wave scan",
            "explanation": "A test that uses sound waves to create pictures inside your body.",
            "category": "test"
        },
        "x-ray": {
            "simple": "bone picture",
            "explanation": "Uses radiation to create images of structures inside your body.",
            "category": "test"
        },

        # Diagnoses
        "benign": {
            "simple": "not cancer",
            "explanation": "A growth that is NOT cancer and will not spread to other parts of the body.",
            "category": "diagnosis"
        },
        "malignant": {
            "simple": "cancerous",
            "explanation": "A growth that IS cancer and may spread to other parts of the body.",
            "category": "diagnosis"
        },
        "metastasis": {
            "simple": "cancer spread",
            "explanation": "When cancer cells spread from where they started to other parts of the body.",
            "category": "diagnosis"
        },
        "prognosis": {
            "simple": "expected outcome",
            "explanation": "The doctor's prediction of how a disease will progress.",
            "category": "diagnosis"
        },
        "diagnosis": {
            "simple": "identifying the problem",
            "explanation": "Determining what illness or condition you have based on symptoms and tests.",
            "category": "diagnosis"
        },
        "acute": {
            "simple": "sudden and short-term",
            "explanation": "A condition that starts suddenly and usually doesn't last long.",
            "category": "diagnosis"
        },
        "chronic": {
            "simple": "long-lasting",
            "explanation": "A condition that lasts a long time (months or years) or keeps coming back.",
            "category": "diagnosis"
        },
        "remission": {
            "simple": "disease improvement",
            "explanation": "When signs and symptoms of a disease decrease or disappear.",
            "category": "diagnosis"
        },
        "relapse": {
            "simple": "disease return",
            "explanation": "When a disease comes back after a period of improvement.",
            "category": "diagnosis"
        },

        # Medications
        "antibiotic": {
            "simple": "bacteria-killing medicine",
            "explanation": "Medicine that fights bacterial infections. Does NOT work on viruses.",
            "category": "medication"
        },
        "analgesic": {
            "simple": "pain reliever",
            "explanation": "Medicine that reduces pain, like aspirin, ibuprofen, or acetaminophen.",
            "category": "medication"
        },
        "anti-inflammatory": {
            "simple": "swelling reducer",
            "explanation": "Medicine that reduces swelling, redness, and pain.",
            "category": "medication"
        },
        "prescription": {
            "simple": "doctor's medicine order",
            "explanation": "A written order from a doctor for medicine.",
            "category": "medication"
        },
        "dosage": {
            "simple": "amount of medicine",
            "explanation": "How much medicine to take and how often.",
            "category": "medication"
        },
        "generic": {
            "simple": "non-brand medicine",
            "explanation": "A medicine that works the same as a brand-name drug but usually costs less.",
            "category": "medication"
        },

        # Symptoms
        "edema": {
            "simple": "swelling",
            "explanation": "Swelling caused by fluid trapped in your body's tissues.",
            "category": "symptom"
        },
        "inflammation": {
            "simple": "swelling and redness",
            "explanation": "Your body's response to injury or infection.",
            "category": "symptom"
        },
        "nausea": {
            "simple": "feeling sick to stomach",
            "explanation": "The queasy feeling that you might vomit.",
            "category": "symptom"
        },
        "fatigue": {
            "simple": "extreme tiredness",
            "explanation": "Feeling very tired and lacking energy, even after rest.",
            "category": "symptom"
        },
        "vertigo": {
            "simple": "spinning dizziness",
            "explanation": "A type of dizziness where you feel like the room is spinning.",
            "category": "symptom"
        },
        "fever": {
            "simple": "high body temperature",
            "explanation": "Body temperature above normal (100.4F/38C).",
            "category": "symptom"
        },

        # Vitals
        "vital signs": {
            "simple": "basic body measurements",
            "explanation": "Temperature, pulse, breathing rate, and blood pressure.",
            "category": "vital"
        },
        "blood pressure": {
            "simple": "force of blood flow",
            "explanation": "The force of blood pushing against artery walls.",
            "category": "vital"
        },
        "systolic": {
            "simple": "top blood pressure number",
            "explanation": "Pressure when heart beats.",
            "category": "vital"
        },
        "diastolic": {
            "simple": "bottom blood pressure number",
            "explanation": "Pressure when heart rests between beats.",
            "category": "vital"
        },
        "pulse": {
            "simple": "heartbeat rate",
            "explanation": "How many times your heart beats per minute.",
            "category": "vital"
        },

        # Specialists
        "cardiologist": {
            "simple": "heart doctor",
            "explanation": "A doctor who specializes in heart and blood vessel problems.",
            "category": "specialist"
        },
        "oncologist": {
            "simple": "cancer doctor",
            "explanation": "A doctor who specializes in diagnosing and treating cancer.",
            "category": "specialist"
        },
        "neurologist": {
            "simple": "brain and nerve doctor",
            "explanation": "A doctor who specializes in brain, spinal cord, and nerve disorders.",
            "category": "specialist"
        },
        "dermatologist": {
            "simple": "skin doctor",
            "explanation": "A doctor who specializes in skin, hair, and nail conditions.",
            "category": "specialist"
        },
        "endocrinologist": {
            "simple": "hormone doctor",
            "explanation": "A doctor who specializes in hormone-related conditions.",
            "category": "specialist"
        },
        "gastroenterologist": {
            "simple": "digestive system doctor",
            "explanation": "A doctor who specializes in stomach and intestine problems.",
            "category": "specialist"
        },
        "pulmonologist": {
            "simple": "lung doctor",
            "explanation": "A doctor who specializes in lung and breathing problems.",
            "category": "specialist"
        },

        # Respiratory
        "pneumonia": {
            "simple": "lung infection",
            "explanation": "An infection that inflames the air sacs in one or both lungs.",
            "category": "respiratory"
        },
        "bronchitis": {
            "simple": "airway inflammation",
            "explanation": "Inflammation of the bronchial tubes. Causes coughing and mucus.",
            "category": "respiratory"
        },
        "asthma": {
            "simple": "breathing condition",
            "explanation": "Airways narrow and swell, making breathing difficult.",
            "category": "respiratory"
        },
        "copd": {
            "simple": "chronic lung disease",
            "explanation": "Lung diseases that block airflow and make breathing difficult.",
            "category": "respiratory"
        },

        # Emergency
        "stroke": {
            "simple": "brain attack",
            "explanation": "When blood flow to part of the brain is blocked. Emergency - call 911.",
            "category": "emergency"
        },
        "heart attack": {
            "simple": "heart muscle damage",
            "explanation": "When blood flow to the heart is blocked. Emergency - call 911.",
            "category": "emergency"
        },
        "myocardial infarction": {
            "simple": "heart attack",
            "explanation": "The medical term for heart attack.",
            "category": "emergency"
        },
        "anaphylaxis": {
            "simple": "severe allergic reaction",
            "explanation": "A life-threatening allergic reaction requiring immediate treatment.",
            "category": "emergency"
        },

        # Treatment
        "intravenous": {
            "simple": "through a vein",
            "explanation": "Giving medicine or fluids directly into a vein.",
            "category": "treatment"
        },
        "iv": {
            "simple": "medicine through a vein",
            "explanation": "Fluids or medicine given directly into your bloodstream.",
            "category": "treatment"
        },
        "oral": {
            "simple": "by mouth",
            "explanation": "Taking medicine by swallowing it.",
            "category": "treatment"
        },
        "topical": {
            "simple": "on the skin",
            "explanation": "Medicine applied directly to the skin.",
            "category": "treatment"
        },

        # General
        "outpatient": {
            "simple": "no overnight stay",
            "explanation": "Medical care where you go home the same day.",
            "category": "general"
        },
        "inpatient": {
            "simple": "hospital stay",
            "explanation": "When you stay overnight in a hospital for treatment.",
            "category": "general"
        },
        "follow-up": {
            "simple": "return visit",
            "explanation": "A visit to check on your progress after treatment.",
            "category": "general"
        },
        "referral": {
            "simple": "doctor recommendation",
            "explanation": "When your doctor sends you to see another doctor or specialist.",
            "category": "general"
        },
    }

    ABBREVIATIONS = {
        "bp": "blood pressure",
        "hr": "heart rate",
        "rr": "respiratory rate",
        "temp": "temperature",
        "rx": "prescription",
        "dx": "diagnosis",
        "hx": "history",
        "tx": "treatment",
        "fx": "fracture",
        "sx": "symptoms",
        "pt": "patient",
        "po": "by mouth",
        "prn": "as needed",
        "bid": "twice a day",
        "tid": "three times a day",
        "qid": "four times a day",
        "qd": "once a day",
        "stat": "immediately",
        "npo": "nothing by mouth",
        "sob": "shortness of breath",
        "cp": "chest pain",
        "ha": "headache",
        "uti": "urinary tract infection",
        "uri": "upper respiratory infection",
    }

    def __init__(self):
        """Initialize terminology agent"""
        self.dictionary = self.MEDICAL_DICTIONARY
        self.abbreviations = self.ABBREVIATIONS

    async def detect_and_explain(self, text: str) -> TerminologyResult:
        """Scan text for medical terms and provide explanations"""
        if not text or not text.strip():
            return TerminologyResult(
                success=True,
                terms_found=[],
                terms_count=0
            )

        detected_terms = []
        text_lower = text.lower()
        checked_terms: Set[str] = set()

        words = re.findall(r'\b[\w/-]+\b', text_lower)

        for i, word in enumerate(words):
            if word in checked_terms:
                continue

            # Check exact match
            if word in self.dictionary:
                term_data = self.dictionary[word]
                detected_terms.append(MedicalTerm(
                    term=word,
                    simple=term_data["simple"],
                    explanation=term_data["explanation"],
                    category=term_data["category"],
                    source=TermSource.UOFM_DICTIONARY
                ))
                checked_terms.add(word)
                continue

            # Check abbreviations
            if word in self.abbreviations:
                expansion = self.abbreviations[word]
                detected_terms.append(MedicalTerm(
                    term=word.upper(),
                    simple=expansion,
                    explanation=f"Medical abbreviation for: {expansion}",
                    category="abbreviation",
                    source=TermSource.ABBREVIATION
                ))
                checked_terms.add(word)
                continue

            # Check two-word phrases
            if i < len(words) - 1:
                phrase = f"{word} {words[i+1]}"
                if phrase in self.dictionary:
                    term_data = self.dictionary[phrase]
                    detected_terms.append(MedicalTerm(
                        term=phrase,
                        simple=term_data["simple"],
                        explanation=term_data["explanation"],
                        category=term_data["category"],
                        source=TermSource.UOFM_DICTIONARY
                    ))
                    checked_terms.add(word)
                    checked_terms.add(words[i+1])
                    continue

            # Fuzzy match
            fuzzy_match = self._fuzzy_match(word)
            if fuzzy_match:
                term_data = self.dictionary[fuzzy_match]
                detected_terms.append(MedicalTerm(
                    term=fuzzy_match,
                    simple=term_data["simple"],
                    explanation=term_data["explanation"],
                    category=term_data["category"],
                    source=TermSource.UOFM_DICTIONARY
                ))
                checked_terms.add(word)

        return TerminologyResult(
            success=True,
            terms_found=detected_terms,
            terms_count=len(detected_terms)
        )

    def _fuzzy_match(self, word: str, threshold: float = 0.85) -> Optional[str]:
        """Find close matches for word variations"""
        if len(word) < 4:
            return None

        best_match = None
        best_ratio = 0

        for term in self.dictionary:
            ratio = SequenceMatcher(None, word[:len(term)], term).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = term

        return best_match

    def get_term(self, term: str) -> Optional[MedicalTerm]:
        """Look up a specific term"""
        term_lower = term.lower().strip()

        if term_lower in self.dictionary:
            data = self.dictionary[term_lower]
            return MedicalTerm(
                term=term_lower,
                simple=data["simple"],
                explanation=data["explanation"],
                category=data["category"],
                source=TermSource.UOFM_DICTIONARY
            )

        if term_lower in self.abbreviations:
            expansion = self.abbreviations[term_lower]
            return MedicalTerm(
                term=term_lower.upper(),
                simple=expansion,
                explanation=f"Medical abbreviation for: {expansion}",
                category="abbreviation",
                source=TermSource.ABBREVIATION
            )

        return None


# =============================================================================
# STANDALONE FUNCTION
# =============================================================================

_agent: Optional[TerminologyAgent] = None


def get_agent() -> TerminologyAgent:
    """Get or create the global terminology agent"""
    global _agent
    if _agent is None:
        _agent = TerminologyAgent()
    return _agent


async def detect_medical_terms(text: str) -> List[dict]:
    """Backward-compatible function"""
    agent = get_agent()
    result = await agent.detect_and_explain(text)

    return [
        {
            "term": t.term,
            "simple": t.simple,
            "explanation": t.explanation,
            "category": t.category,
            "source": t.source.value,
        }
        for t in result.terms_found
    ]
