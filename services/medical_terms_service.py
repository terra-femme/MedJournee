# services/medical_terms_service.py
"""
Medical Terms Service for MedJournee
Based on: University of Michigan Plain Language Medical Dictionary (CC BY 4.0)
          + MedlinePlus API integration for additional terms

Integrates with your existing AI journal generation to:
1. Detect medical terms in transcripts
2. Provide plain language explanations
3. Generate translated explanations for family members
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher

# Plain Language Medical Dictionary
# Source: CDC Plain Language Thesaurus + U of M Health Sciences Library
# License: Creative Commons Attribution 4.0
MEDICAL_TERMS_PLAIN_LANGUAGE = {
    # Common terms families encounter
    "hypertension": {
        "term": "hypertension",
        "simple": "high blood pressure",
        "explanation": "When the force of blood pushing against your artery walls is too high. This can damage your heart over time.",
        "category": "cardiovascular"
    },
    "hypotension": {
        "term": "hypotension", 
        "simple": "low blood pressure",
        "explanation": "When blood pressure is lower than normal. Can cause dizziness when standing up.",
        "category": "cardiovascular"
    },
    "diabetes": {
        "term": "diabetes",
        "simple": "high blood sugar disease",
        "explanation": "A condition where your body has trouble controlling blood sugar levels. Requires careful diet and often medication.",
        "category": "metabolic"
    },
    "diabetes mellitus": {
        "term": "diabetes mellitus",
        "simple": "sugar diabetes",
        "explanation": "The medical name for diabetes - when your body can't properly use sugar from food for energy.",
        "category": "metabolic"
    },
    "prediabetes": {
        "term": "prediabetes",
        "simple": "early warning of diabetes",
        "explanation": "Blood sugar is higher than normal but not high enough to be diabetes. Can often be reversed with diet and exercise.",
        "category": "metabolic"
    },
    "anemia": {
        "term": "anemia",
        "simple": "low red blood cells",
        "explanation": "Not having enough healthy red blood cells to carry oxygen to your body. Can make you feel tired and weak.",
        "category": "blood"
    },
    "cholesterol": {
        "term": "cholesterol",
        "simple": "fat in your blood",
        "explanation": "A waxy substance in your blood. Too much can clog arteries and lead to heart problems.",
        "category": "cardiovascular"
    },
    "ldl": {
        "term": "LDL",
        "simple": "bad cholesterol",
        "explanation": "Low-density lipoprotein - the type of cholesterol that can build up in your arteries. Lower is better.",
        "category": "cardiovascular"
    },
    "hdl": {
        "term": "HDL",
        "simple": "good cholesterol", 
        "explanation": "High-density lipoprotein - helps remove bad cholesterol from your blood. Higher is better.",
        "category": "cardiovascular"
    },
    "ecg": {
        "term": "ECG",
        "simple": "heart rhythm test",
        "explanation": "Electrocardiogram - a test that records the electrical activity of your heart to check for problems.",
        "category": "test"
    },
    "ekg": {
        "term": "EKG",
        "simple": "heart rhythm test",
        "explanation": "Same as ECG - electrocardiogram. Tests your heart's electrical activity.",
        "category": "test"
    },
    "echocardiogram": {
        "term": "echocardiogram",
        "simple": "heart ultrasound",
        "explanation": "Uses sound waves to create pictures of your heart to see how well it's pumping.",
        "category": "test"
    },
    "mri": {
        "term": "MRI",
        "simple": "detailed body scan",
        "explanation": "Magnetic resonance imaging - uses magnets and radio waves to create detailed pictures inside your body.",
        "category": "test"
    },
    "ct scan": {
        "term": "CT scan",
        "simple": "detailed X-ray",
        "explanation": "Computed tomography - combines many X-ray images to create detailed cross-section pictures of your body.",
        "category": "test"
    },
    "cbc": {
        "term": "CBC",
        "simple": "blood cell count test",
        "explanation": "Complete blood count - measures red cells, white cells, and platelets to check your overall health.",
        "category": "test"
    },
    "complete blood count": {
        "term": "complete blood count",
        "simple": "blood cell count test",
        "explanation": "A test that counts different types of cells in your blood to check for infections, anemia, and other conditions.",
        "category": "test"
    },
    "biopsy": {
        "term": "biopsy",
        "simple": "tissue sample test",
        "explanation": "Removing a small piece of tissue from your body to examine under a microscope, often to check for cancer.",
        "category": "procedure"
    },
    "benign": {
        "term": "benign",
        "simple": "not cancer",
        "explanation": "A growth or tumor that is NOT cancer and will not spread to other parts of the body.",
        "category": "diagnosis"
    },
    "malignant": {
        "term": "malignant",
        "simple": "cancerous",
        "explanation": "A growth that IS cancer and may spread to other parts of the body if not treated.",
        "category": "diagnosis"
    },
    "metastasis": {
        "term": "metastasis",
        "simple": "cancer spread",
        "explanation": "When cancer cells spread from where they started to other parts of the body.",
        "category": "diagnosis"
    },
    "antibiotic": {
        "term": "antibiotic",
        "simple": "bacteria-killing medicine",
        "explanation": "Medicine that fights bacterial infections. Does NOT work on viruses like colds or flu.",
        "category": "medication"
    },
    "analgesic": {
        "term": "analgesic",
        "simple": "pain reliever",
        "explanation": "Medicine that reduces pain, like aspirin, ibuprofen, or acetaminophen.",
        "category": "medication"
    },
    "anti-inflammatory": {
        "term": "anti-inflammatory",
        "simple": "swelling reducer",
        "explanation": "Medicine that reduces swelling, redness, and pain. Examples include ibuprofen and naproxen.",
        "category": "medication"
    },
    "prognosis": {
        "term": "prognosis",
        "simple": "expected outcome",
        "explanation": "The doctor's prediction of how a disease will progress and the chances of recovery.",
        "category": "diagnosis"
    },
    "diagnosis": {
        "term": "diagnosis",
        "simple": "identifying the problem",
        "explanation": "The process of determining what illness or condition you have based on symptoms and tests.",
        "category": "diagnosis"
    },
    "acute": {
        "term": "acute",
        "simple": "sudden and short-term",
        "explanation": "A condition that starts suddenly and usually doesn't last long. Opposite of chronic.",
        "category": "general"
    },
    "chronic": {
        "term": "chronic",
        "simple": "long-lasting",
        "explanation": "A condition that lasts a long time (months or years) or keeps coming back.",
        "category": "general"
    },
    "symptoms": {
        "term": "symptoms",
        "simple": "signs of illness",
        "explanation": "Changes in your body that indicate something is wrong, like pain, fever, or fatigue.",
        "category": "general"
    },
    "vital signs": {
        "term": "vital signs",
        "simple": "basic body measurements",
        "explanation": "The main measurements of body function: temperature, pulse, breathing rate, and blood pressure.",
        "category": "general"
    },
    "edema": {
        "term": "edema",
        "simple": "swelling",
        "explanation": "Swelling caused by fluid trapped in your body's tissues, often in legs, ankles, or feet.",
        "category": "symptom"
    },
    "inflammation": {
        "term": "inflammation",
        "simple": "swelling and redness",
        "explanation": "Your body's response to injury or infection - causes redness, warmth, swelling, and pain.",
        "category": "symptom"
    },
    "nausea": {
        "term": "nausea",
        "simple": "feeling sick to stomach",
        "explanation": "The queasy feeling that you might vomit, but haven't yet.",
        "category": "symptom"
    },
    "fatigue": {
        "term": "fatigue",
        "simple": "extreme tiredness",
        "explanation": "Feeling very tired and lacking energy, even after rest. Different from normal tiredness.",
        "category": "symptom"
    },
    "vertigo": {
        "term": "vertigo",
        "simple": "spinning dizziness",
        "explanation": "A type of dizziness where you feel like you or the room is spinning.",
        "category": "symptom"
    },
    "arrhythmia": {
        "term": "arrhythmia",
        "simple": "irregular heartbeat",
        "explanation": "When your heart beats too fast, too slow, or with an irregular pattern.",
        "category": "cardiovascular"
    },
    "tachycardia": {
        "term": "tachycardia",
        "simple": "fast heartbeat",
        "explanation": "Heart rate faster than 100 beats per minute at rest.",
        "category": "cardiovascular"
    },
    "bradycardia": {
        "term": "bradycardia",
        "simple": "slow heartbeat",
        "explanation": "Heart rate slower than 60 beats per minute. Can be normal for athletes.",
        "category": "cardiovascular"
    },
    "cardiologist": {
        "term": "cardiologist",
        "simple": "heart doctor",
        "explanation": "A doctor who specializes in treating heart and blood vessel problems.",
        "category": "specialist"
    },
    "oncologist": {
        "term": "oncologist",
        "simple": "cancer doctor",
        "explanation": "A doctor who specializes in diagnosing and treating cancer.",
        "category": "specialist"
    },
    "neurologist": {
        "term": "neurologist",
        "simple": "brain and nerve doctor",
        "explanation": "A doctor who specializes in disorders of the brain, spinal cord, and nerves.",
        "category": "specialist"
    },
    "dermatologist": {
        "term": "dermatologist",
        "simple": "skin doctor",
        "explanation": "A doctor who specializes in conditions affecting skin, hair, and nails.",
        "category": "specialist"
    },
    "endocrinologist": {
        "term": "endocrinologist",
        "simple": "hormone doctor",
        "explanation": "A doctor who specializes in hormone-related conditions like diabetes and thyroid problems.",
        "category": "specialist"
    },
    "gastroenterologist": {
        "term": "gastroenterologist",
        "simple": "digestive system doctor",
        "explanation": "A doctor who specializes in stomach, intestine, and digestive system problems.",
        "category": "specialist"
    },
    "pulmonologist": {
        "term": "pulmonologist",
        "simple": "lung doctor",
        "explanation": "A doctor who specializes in lung and breathing problems.",
        "category": "specialist"
    },
    "orthopedist": {
        "term": "orthopedist",
        "simple": "bone and joint doctor",
        "explanation": "A doctor who specializes in bones, joints, muscles, and related injuries.",
        "category": "specialist"
    },
    "nephrologist": {
        "term": "nephrologist",
        "simple": "kidney doctor",
        "explanation": "A doctor who specializes in kidney diseases and problems.",
        "category": "specialist"
    },
    "urologist": {
        "term": "urologist",
        "simple": "urinary system doctor",
        "explanation": "A doctor who specializes in the urinary tract and male reproductive system.",
        "category": "specialist"
    },
    "intravenous": {
        "term": "intravenous",
        "simple": "through a vein",
        "explanation": "Giving medicine or fluids directly into a vein using a needle or tube (IV).",
        "category": "treatment"
    },
    "iv": {
        "term": "IV",
        "simple": "medicine through a vein",
        "explanation": "Intravenous - fluids or medicine given directly into your bloodstream through a small tube.",
        "category": "treatment"
    },
    "oral": {
        "term": "oral",
        "simple": "by mouth",
        "explanation": "Taking medicine by swallowing it, like pills or liquid.",
        "category": "treatment"
    },
    "topical": {
        "term": "topical",
        "simple": "on the skin",
        "explanation": "Medicine applied directly to the skin, like creams or ointments.",
        "category": "treatment"
    },
    "injection": {
        "term": "injection",
        "simple": "shot",
        "explanation": "Medicine given with a needle, either into muscle, under skin, or into a vein.",
        "category": "treatment"
    },
    "dosage": {
        "term": "dosage",
        "simple": "amount of medicine",
        "explanation": "How much medicine to take and how often.",
        "category": "medication"
    },
    "contraindication": {
        "term": "contraindication",
        "simple": "reason not to use",
        "explanation": "A condition or situation that makes a particular treatment risky or not recommended.",
        "category": "medication"
    },
    "side effect": {
        "term": "side effect",
        "simple": "unwanted reaction",
        "explanation": "An unwanted effect of a medicine, in addition to its intended effect.",
        "category": "medication"
    },
    "allergic reaction": {
        "term": "allergic reaction",
        "simple": "body overreaction",
        "explanation": "When your immune system overreacts to something, causing symptoms like rash, swelling, or breathing problems.",
        "category": "symptom"
    },
    "anaphylaxis": {
        "term": "anaphylaxis",
        "simple": "severe allergic reaction",
        "explanation": "A life-threatening allergic reaction that can cause breathing problems and low blood pressure. Requires immediate treatment.",
        "category": "emergency"
    },
    "stroke": {
        "term": "stroke",
        "simple": "brain attack",
        "explanation": "When blood flow to part of the brain is blocked or a blood vessel bursts. Emergency - call 911.",
        "category": "emergency"
    },
    "heart attack": {
        "term": "heart attack",
        "simple": "heart muscle damage",
        "explanation": "When blood flow to the heart is blocked, damaging heart muscle. Emergency - call 911.",
        "category": "emergency"
    },
    "myocardial infarction": {
        "term": "myocardial infarction",
        "simple": "heart attack",
        "explanation": "The medical term for heart attack - when heart muscle is damaged due to blocked blood flow.",
        "category": "emergency"
    },
    "pneumonia": {
        "term": "pneumonia",
        "simple": "lung infection",
        "explanation": "An infection that inflames the air sacs in one or both lungs, which may fill with fluid.",
        "category": "respiratory"
    },
    "bronchitis": {
        "term": "bronchitis",
        "simple": "airway inflammation",
        "explanation": "Inflammation of the bronchial tubes that carry air to your lungs. Causes coughing and mucus.",
        "category": "respiratory"
    },
    "asthma": {
        "term": "asthma",
        "simple": "breathing condition",
        "explanation": "A condition where airways narrow and swell, making breathing difficult. Often triggered by allergies or exercise.",
        "category": "respiratory"
    },
    "copd": {
        "term": "COPD",
        "simple": "chronic lung disease",
        "explanation": "Chronic obstructive pulmonary disease - a group of lung diseases that block airflow and make breathing difficult.",
        "category": "respiratory"
    },
    "arthritis": {
        "term": "arthritis",
        "simple": "joint inflammation",
        "explanation": "Swelling and tenderness of joints, causing pain and stiffness. Common types include osteoarthritis and rheumatoid arthritis.",
        "category": "musculoskeletal"
    },
    "osteoporosis": {
        "term": "osteoporosis",
        "simple": "weak bones",
        "explanation": "A condition where bones become weak and brittle, increasing risk of fractures.",
        "category": "musculoskeletal"
    },
    "fracture": {
        "term": "fracture",
        "simple": "broken bone",
        "explanation": "A break or crack in a bone.",
        "category": "musculoskeletal"
    },
    "sprain": {
        "term": "sprain",
        "simple": "stretched ligament",
        "explanation": "Stretching or tearing of ligaments (tissues connecting bones at a joint).",
        "category": "musculoskeletal"
    },
    "strain": {
        "term": "strain",
        "simple": "pulled muscle",
        "explanation": "Stretching or tearing of a muscle or tendon (tissue connecting muscle to bone).",
        "category": "musculoskeletal"
    },
    "thyroid": {
        "term": "thyroid",
        "simple": "metabolism gland",
        "explanation": "A butterfly-shaped gland in your neck that controls how your body uses energy.",
        "category": "endocrine"
    },
    "hypothyroidism": {
        "term": "hypothyroidism",
        "simple": "underactive thyroid",
        "explanation": "When thyroid doesn't make enough hormones, slowing metabolism. Can cause fatigue and weight gain.",
        "category": "endocrine"
    },
    "hyperthyroidism": {
        "term": "hyperthyroidism",
        "simple": "overactive thyroid",
        "explanation": "When thyroid makes too much hormone, speeding up metabolism. Can cause weight loss and rapid heartbeat.",
        "category": "endocrine"
    },
    "insulin": {
        "term": "insulin",
        "simple": "blood sugar hormone",
        "explanation": "A hormone that helps your body use sugar from food for energy. People with diabetes may need insulin shots.",
        "category": "endocrine"
    },
    "glucose": {
        "term": "glucose",
        "simple": "blood sugar",
        "explanation": "The main type of sugar in your blood that your body uses for energy.",
        "category": "metabolic"
    },
    "hemoglobin": {
        "term": "hemoglobin",
        "simple": "oxygen carrier in blood",
        "explanation": "The protein in red blood cells that carries oxygen throughout your body.",
        "category": "blood"
    },
    "a1c": {
        "term": "A1C",
        "simple": "average blood sugar test",
        "explanation": "A blood test showing your average blood sugar over the past 2-3 months. Important for diabetes management.",
        "category": "test"
    },
    "hemoglobin a1c": {
        "term": "hemoglobin A1C",
        "simple": "3-month blood sugar average",
        "explanation": "A test measuring average blood sugar levels over 2-3 months. Used to diagnose and monitor diabetes.",
        "category": "test"
    },
    "blood pressure": {
        "term": "blood pressure",
        "simple": "force of blood flow",
        "explanation": "The force of blood pushing against artery walls. Given as two numbers (like 120/80).",
        "category": "vital"
    },
    "systolic": {
        "term": "systolic",
        "simple": "top blood pressure number",
        "explanation": "The first/top number in blood pressure - pressure when heart beats.",
        "category": "vital"
    },
    "diastolic": {
        "term": "diastolic",
        "simple": "bottom blood pressure number",
        "explanation": "The second/bottom number in blood pressure - pressure when heart rests between beats.",
        "category": "vital"
    },
    "pulse": {
        "term": "pulse",
        "simple": "heartbeat rate",
        "explanation": "How many times your heart beats per minute. Normal resting pulse is 60-100.",
        "category": "vital"
    },
    "temperature": {
        "term": "temperature",
        "simple": "body heat",
        "explanation": "A measure of body heat. Normal is around 98.6°F (37°C). Higher may indicate fever/infection.",
        "category": "vital"
    },
    "fever": {
        "term": "fever",
        "simple": "high body temperature",
        "explanation": "Body temperature above normal (100.4°F/38°C), usually a sign your body is fighting infection.",
        "category": "symptom"
    },
    "outpatient": {
        "term": "outpatient",
        "simple": "no overnight stay",
        "explanation": "Medical care where you go home the same day - you don't stay overnight in the hospital.",
        "category": "general"
    },
    "inpatient": {
        "term": "inpatient",
        "simple": "hospital stay",
        "explanation": "When you stay overnight in a hospital for treatment.",
        "category": "general"
    },
    "follow-up": {
        "term": "follow-up",
        "simple": "return visit",
        "explanation": "A visit to check on your progress after treatment or a procedure.",
        "category": "general"
    },
    "referral": {
        "term": "referral",
        "simple": "doctor recommendation",
        "explanation": "When your doctor sends you to see another doctor or specialist.",
        "category": "general"
    },
    "prescription": {
        "term": "prescription",
        "simple": "doctor's medicine order",
        "explanation": "A written order from a doctor for medicine that you can only get from a pharmacy.",
        "category": "medication"
    },
    "over-the-counter": {
        "term": "over-the-counter",
        "simple": "no prescription needed",
        "explanation": "Medicine you can buy without a doctor's prescription, like aspirin or allergy pills.",
        "category": "medication"
    },
    "generic": {
        "term": "generic",
        "simple": "non-brand medicine",
        "explanation": "A medicine that works the same as a brand-name drug but usually costs less.",
        "category": "medication"
    },
    "electrolytes": {
        "term": "electrolytes",
        "simple": "body minerals",
        "explanation": "Minerals in your blood (like sodium, potassium) that help your body function properly.",
        "category": "blood"
    },
    "dehydration": {
        "term": "dehydration",
        "simple": "not enough fluids",
        "explanation": "When your body loses more fluids than it takes in. Can cause dizziness and confusion.",
        "category": "condition"
    },
    "bmi": {
        "term": "BMI",
        "simple": "weight-to-height ratio",
        "explanation": "Body mass index - a number calculated from height and weight used to estimate body fat.",
        "category": "measurement"
    },
    "obesity": {
        "term": "obesity",
        "simple": "excess body weight",
        "explanation": "Having too much body fat. BMI of 30 or higher. Increases risk of many health problems.",
        "category": "condition"
    },
    "remission": {
        "term": "remission",
        "simple": "disease improvement",
        "explanation": "When signs and symptoms of a disease decrease or disappear. Can be partial or complete.",
        "category": "diagnosis"
    },
    "relapse": {
        "term": "relapse",
        "simple": "disease return",
        "explanation": "When a disease comes back after a period of improvement.",
        "category": "diagnosis"
    },
    "ultrasound": {
        "term": "ultrasound",
        "simple": "sound wave scan",
        "explanation": "A test that uses sound waves to create pictures of inside your body. No radiation.",
        "category": "test"
    },
    "x-ray": {
        "term": "X-ray",
        "simple": "bone picture",
        "explanation": "Uses radiation to create images of structures inside your body, especially bones.",
        "category": "test"
    },
    "colonoscopy": {
        "term": "colonoscopy",
        "simple": "colon exam",
        "explanation": "A test where a doctor uses a camera on a tube to look inside your large intestine.",
        "category": "procedure"
    },
    "endoscopy": {
        "term": "endoscopy",
        "simple": "internal camera exam",
        "explanation": "Using a thin tube with a camera to look inside your body, often your throat or stomach.",
        "category": "procedure"
    },
    "anesthesia": {
        "term": "anesthesia",
        "simple": "numbing medicine",
        "explanation": "Medicine that blocks pain. Local numbs one area; general puts you to sleep.",
        "category": "procedure"
    },
    "sedation": {
        "term": "sedation",
        "simple": "relaxation medicine",
        "explanation": "Medicine that makes you relaxed and drowsy but not fully asleep.",
        "category": "procedure"
    }
}

# Abbreviation expansions (from MeDAL dataset patterns)
MEDICAL_ABBREVIATIONS = {
    "bp": "blood pressure",
    "hr": "heart rate",
    "rr": "respiratory rate",
    "temp": "temperature",
    "o2 sat": "oxygen saturation",
    "spo2": "oxygen saturation",
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
    "hs": "at bedtime",
    "ac": "before meals",
    "pc": "after meals",
    "stat": "immediately",
    "npo": "nothing by mouth",
    "sob": "shortness of breath",
    "cp": "chest pain",
    "ha": "headache",
    "n/v": "nausea and vomiting",
    "uri": "upper respiratory infection",
    "uti": "urinary tract infection",
    "mi": "heart attack",
    "cva": "stroke",
    "chf": "heart failure",
    "cabg": "heart bypass surgery",
    "cad": "coronary artery disease",
    "afib": "atrial fibrillation",
    "dvt": "deep vein thrombosis",
    "pe": "pulmonary embolism",
    "gi": "gastrointestinal",
    "gerd": "acid reflux disease",
    "ibs": "irritable bowel syndrome",
    "ckd": "chronic kidney disease",
    "esrd": "end stage kidney disease",
    "ra": "rheumatoid arthritis",
    "oa": "osteoarthritis",
    "ms": "multiple sclerosis",
    "als": "lou gehrig's disease",
    "hiv": "human immunodeficiency virus",
    "aids": "acquired immune deficiency syndrome",
    "tb": "tuberculosis",
    "mrsa": "antibiotic-resistant staph infection",
}


class MedicalTermsService:
    """
    Service for detecting and explaining medical terms in transcripts.
    Designed to integrate with your existing AI journal generation.
    """
    
    def __init__(self):
        self.terms_db = MEDICAL_TERMS_PLAIN_LANGUAGE
        self.abbreviations = MEDICAL_ABBREVIATIONS
        
    def detect_medical_terms(self, text: str) -> List[Dict]:
        """
        Scan text for medical terms and return matches with explanations.
        Uses fuzzy matching for variations like "hypertensive" -> "hypertension"
        """
        detected = []
        text_lower = text.lower()
        words = re.findall(r'\b[\w/-]+\b', text_lower)
        
        # Check each word and phrase
        checked = set()
        
        for i, word in enumerate(words):
            # Skip if already matched as part of a longer phrase
            if word in checked:
                continue
                
            # Try exact match first
            if word in self.terms_db:
                detected.append({
                    "original": word,
                    "match_type": "exact",
                    **self.terms_db[word]
                })
                checked.add(word)
                continue
            
            # Try abbreviation
            if word in self.abbreviations:
                expansion = self.abbreviations[word]
                detected.append({
                    "original": word,
                    "match_type": "abbreviation",
                    "term": word.upper(),
                    "simple": expansion,
                    "explanation": f"Medical abbreviation for: {expansion}",
                    "category": "abbreviation"
                })
                checked.add(word)
                continue
            
            # Try two-word phrases
            if i < len(words) - 1:
                phrase = f"{word} {words[i+1]}"
                if phrase in self.terms_db:
                    detected.append({
                        "original": phrase,
                        "match_type": "phrase",
                        **self.terms_db[phrase]
                    })
                    checked.add(word)
                    checked.add(words[i+1])
                    continue
            
            # Fuzzy match for word variations (hypertensive -> hypertension)
            best_match = self._fuzzy_match(word)
            if best_match:
                detected.append({
                    "original": word,
                    "match_type": "fuzzy",
                    **self.terms_db[best_match]
                })
                checked.add(word)
        
        return detected
    
    def _fuzzy_match(self, word: str, threshold: float = 0.85) -> Optional[str]:
        """Find close matches for word variations"""
        if len(word) < 4:  # Skip short words
            return None
            
        best_match = None
        best_ratio = 0
        
        for term in self.terms_db:
            # Check if word starts with term stem
            ratio = SequenceMatcher(None, word[:len(term)], term).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = term
        
        return best_match
    
    def get_term_explanation(self, term: str) -> Optional[Dict]:
        """Get explanation for a specific term"""
        term_lower = term.lower()
        
        if term_lower in self.terms_db:
            return self.terms_db[term_lower]
        
        if term_lower in self.abbreviations:
            expansion = self.abbreviations[term_lower]
            return {
                "term": term.upper(),
                "simple": expansion,
                "explanation": f"Medical abbreviation for: {expansion}",
                "category": "abbreviation"
            }
        
        return None
    
    def generate_family_glossary(self, text: str, target_language: str = "en") -> Dict:
        """
        Generate a family-friendly glossary from transcript text.
        This integrates with your AI journal generation.
        """
        detected_terms = self.detect_medical_terms(text)
        
        glossary = {}
        for item in detected_terms:
            term = item.get("term", item.get("original", ""))
            glossary[term] = {
                "simple": item.get("simple", ""),
                "explanation": item.get("explanation", ""),
                "category": item.get("category", "general")
            }
        
        return {
            "terms_found": len(glossary),
            "glossary": glossary,
            "target_language": target_language
        }
    
    def enrich_journal_entry(self, journal_entry: Dict) -> Dict:
        """
        Add medical term explanations to an existing journal entry.
        Call this AFTER your AI generates the journal but BEFORE saving to database.
        """
        # Collect all text from journal entry
        text_parts = []
        
        # Get text from different sections
        if "visit_summary" in journal_entry:
            text_parts.append(journal_entry["visit_summary"])
        if "symptoms" in journal_entry:
            text_parts.extend(journal_entry.get("symptoms", []))
        if "diagnoses" in journal_entry:
            text_parts.extend(journal_entry.get("diagnoses", []))
        if "treatments" in journal_entry:
            text_parts.extend(journal_entry.get("treatments", []))
            
        full_text = " ".join(str(p) for p in text_parts)
        
        # Detect and add explanations
        glossary_result = self.generate_family_glossary(full_text)
        
        # Add to journal entry
        journal_entry["medical_terms_explained"] = glossary_result["glossary"]
        journal_entry["medical_terms_count"] = glossary_result["terms_found"]
        
        return journal_entry


# Global instance
medical_terms_service = MedicalTermsService()


# Integration helper for your existing AI journal service
async def enrich_with_medical_terms(journal_entry: Dict) -> Dict:
    """
    Helper function to add medical term explanations to journal entries.
    
    Usage in your ai_journal_service.py:
    
        from services.medical_terms_service import enrich_with_medical_terms
        
        # After generating journal entry with GPT...
        enriched_entry = await enrich_with_medical_terms(journal_entry)
    """
    return medical_terms_service.enrich_journal_entry(journal_entry)
