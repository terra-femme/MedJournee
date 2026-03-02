# evaluation/test_cases.py
"""
MEDICAL CONVERSATION TEST CASES

Test fixtures for evaluating the MedJournee pipeline.
Includes:
- Sample medical conversations
- Expected transcription outputs
- Expected medical terms
- Expected medications
- Quality thresholds
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ExpectedSegment:
    """Expected transcript segment"""
    speaker_role: str  # "provider" or "family"
    text_contains: List[str]  # Key phrases that should appear
    language: str = "en"


@dataclass
class TestCase:
    """A single test case for pipeline evaluation"""
    name: str
    description: str
    category: str  # diabetes, cardiac, respiratory, general, etc.

    # Input
    audio_file: Optional[str] = None  # Path to test audio file
    transcript_text: Optional[str] = None  # Or provide direct transcript

    # Expected outputs
    expected_terms: List[str] = field(default_factory=list)
    expected_medications: List[str] = field(default_factory=list)
    expected_segments: List[ExpectedSegment] = field(default_factory=list)
    expected_diagnoses: List[str] = field(default_factory=list)

    # Quality thresholds
    min_transcription_confidence: float = 0.7
    min_translation_quality: float = 0.7
    min_summarization_quality: float = 0.6

    # Test configuration
    source_language: str = "en"
    target_language: str = "vi"
    is_synthetic: bool = True  # True if using synthetic/generated test data

    # Metadata
    difficulty: str = "medium"  # easy, medium, hard
    tags: List[str] = field(default_factory=list)


# =============================================================================
# DIABETES TEST CASES
# =============================================================================

DIABETES_CHECKUP = TestCase(
    name="diabetes_checkup",
    description="Routine diabetes follow-up visit discussing blood sugar management",
    category="diabetes",
    transcript_text="""
    Provider: Good morning, how have you been managing your diabetes?
    Family: His blood sugar has been a bit high in the mornings, around 180.
    Provider: That's higher than we'd like. Are you taking the metformin as prescribed?
    Family: Yes, 500 milligrams twice a day with meals.
    Provider: Good. Let's increase that to 850 milligrams twice daily. Also, make sure
    to check your glucose before breakfast and dinner.
    Family: What should his numbers be?
    Provider: We want fasting glucose below 130, and after meals below 180.
    The A1C should be under 7 percent.
    """,
    expected_terms=["diabetes", "glucose", "A1C", "fasting glucose"],
    expected_medications=["metformin"],
    expected_diagnoses=["diabetes"],
    min_transcription_confidence=0.7,
    tags=["diabetes", "medication-change", "routine"]
)

DIABETES_NEW_DIAGNOSIS = TestCase(
    name="diabetes_new_diagnosis",
    description="New diabetes diagnosis with patient education",
    category="diabetes",
    transcript_text="""
    Provider: Based on your blood tests, your hemoglobin A1C is 8.5, which confirms diabetes.
    Family: Oh no, what does that mean?
    Provider: It means your body isn't processing sugar properly. But we can manage this
    with medication and lifestyle changes. I'm going to start you on metformin.
    Family: Is this something he'll have forever?
    Provider: Diabetes is a chronic condition, but many patients control it well with
    diet, exercise, and medication. Let's start with 500mg of metformin once daily.
    Family: Are there side effects?
    Provider: Some people experience stomach upset initially. Take it with food.
    We'll also need to monitor your kidney function with regular blood tests.
    """,
    expected_terms=["diabetes", "hemoglobin A1C", "chronic", "kidney"],
    expected_medications=["metformin"],
    expected_diagnoses=["diabetes"],
    difficulty="medium",
    tags=["diabetes", "new-diagnosis", "education"]
)


# =============================================================================
# CARDIOVASCULAR TEST CASES
# =============================================================================

HYPERTENSION_FOLLOWUP = TestCase(
    name="hypertension_followup",
    description="Blood pressure management follow-up",
    category="cardiovascular",
    transcript_text="""
    Provider: Let me check your blood pressure. It's 148 over 92, which is still elevated.
    Family: Is that bad? He's been taking his medicine.
    Provider: It's not at goal yet. We want it below 130 over 80. What medication is he on?
    Family: Lisinopril, 10 milligrams.
    Provider: Let's increase that to 20 milligrams daily. Also, try to reduce sodium
    in the diet. Aim for less than 2300 milligrams per day.
    Family: What about exercise?
    Provider: Walking 30 minutes a day would help. We also need to monitor kidney function
    since you're on lisinopril. I'll order a basic metabolic panel.
    """,
    expected_terms=["blood pressure", "hypertension", "sodium", "kidney function"],
    expected_medications=["lisinopril"],
    expected_diagnoses=["hypertension"],
    tags=["cardiovascular", "hypertension", "lifestyle"]
)

CHOLESTEROL_DISCUSSION = TestCase(
    name="cholesterol_discussion",
    description="High cholesterol treatment discussion",
    category="cardiovascular",
    transcript_text="""
    Provider: Your LDL cholesterol is 165, which is too high. HDL is 42.
    Family: What should it be?
    Provider: We want LDL below 100, and HDL above 40. Your HDL is borderline.
    I recommend starting a statin medication, atorvastatin 20mg at bedtime.
    Family: I've heard statins have side effects.
    Provider: Some people experience muscle aches. Let me know if that happens.
    We'll also recheck your liver function in 6 weeks. In the meantime,
    reduce saturated fats and increase fiber in your diet.
    """,
    expected_terms=["cholesterol", "LDL", "HDL", "statin", "liver"],
    expected_medications=["atorvastatin"],
    expected_diagnoses=["hyperlipidemia", "high cholesterol"],
    tags=["cardiovascular", "cholesterol"]
)


# =============================================================================
# RESPIRATORY TEST CASES
# =============================================================================

ASTHMA_VISIT = TestCase(
    name="asthma_management",
    description="Asthma symptom management",
    category="respiratory",
    transcript_text="""
    Provider: How often are you using your rescue inhaler?
    Family: He uses it about 4 times a week, especially at night.
    Provider: That's more than we'd like. If you need it more than twice a week,
    your asthma isn't well controlled. Let's add a daily controller medication.
    I'm prescribing fluticasone, 2 puffs twice daily.
    Family: Is that the same as albuterol?
    Provider: No, albuterol is your rescue inhaler for quick relief. Fluticasone is
    a preventive steroid that you use every day to reduce inflammation.
    Keep using albuterol for sudden symptoms, but hopefully you'll need it less.
    """,
    expected_terms=["asthma", "inhaler", "steroid", "inflammation"],
    expected_medications=["fluticasone", "albuterol"],
    expected_diagnoses=["asthma"],
    tags=["respiratory", "asthma", "controller-medication"]
)


# =============================================================================
# PAIN MANAGEMENT TEST CASES
# =============================================================================

CHRONIC_PAIN = TestCase(
    name="chronic_pain_management",
    description="Chronic back pain management",
    category="pain",
    transcript_text="""
    Provider: How's your back pain been?
    Family: It's still bothering him, about a 6 out of 10 most days.
    Provider: Is the ibuprofen helping?
    Family: A little, but he can't take too much because of his stomach.
    Provider: That's right, we need to be careful with NSAIDs. Let's try
    acetaminophen 650mg every 6 hours as needed. That's safer for the stomach.
    I'm also referring you to physical therapy, twice a week for 6 weeks.
    Family: What about something stronger?
    Provider: Let's try physical therapy first. If that doesn't help, we can
    discuss other options. Avoid heavy lifting and try heat therapy at home.
    """,
    expected_terms=["NSAIDs", "physical therapy", "chronic pain"],
    expected_medications=["ibuprofen", "acetaminophen"],
    expected_diagnoses=["chronic back pain"],
    tags=["pain", "conservative-treatment"]
)


# =============================================================================
# MENTAL HEALTH TEST CASES
# =============================================================================

DEPRESSION_SCREENING = TestCase(
    name="depression_screening",
    description="Depression screening and treatment initiation",
    category="mental_health",
    transcript_text="""
    Provider: You mentioned feeling down lately. Can you tell me more?
    Family: He hasn't been sleeping well and lost interest in things he used to enjoy.
    Provider: How long has this been going on?
    Family: About two months now.
    Provider: Based on what you're describing, this sounds like depression.
    It's a medical condition that we can treat. I'd like to start you on
    sertraline, 50mg once daily in the morning.
    Family: Will that make him drowsy?
    Provider: It shouldn't. Some people feel a bit anxious initially, but that usually
    passes. I also recommend seeing a counselor for talk therapy.
    """,
    expected_terms=["depression", "insomnia", "antidepressant"],
    expected_medications=["sertraline"],
    expected_diagnoses=["depression"],
    difficulty="medium",
    tags=["mental-health", "depression", "new-treatment"]
)


# =============================================================================
# COMPLEX/MULTI-CONDITION TEST CASES
# =============================================================================

COMPLEX_MULTI_CONDITION = TestCase(
    name="complex_multiple_conditions",
    description="Patient with multiple chronic conditions",
    category="complex",
    transcript_text="""
    Provider: Let's review all your conditions today. How's the diabetes?
    Family: His sugars have been better, usually around 140 fasting.
    Provider: Good, the metformin is working. Blood pressure today is 138/85.
    That's improved but still a bit high. Keep taking the lisinopril.
    Family: What about his cholesterol?
    Provider: The atorvastatin brought your LDL down to 95, which is great.
    No muscle pain? Good. Let's continue everything as is. I want to see
    you back in 3 months with labs: A1C, lipid panel, and kidney function.
    Family: Should he see any specialists?
    Provider: Not right now. His conditions are well controlled with primary care.
    """,
    expected_terms=["diabetes", "blood pressure", "cholesterol", "A1C", "kidney"],
    expected_medications=["metformin", "lisinopril", "atorvastatin"],
    expected_diagnoses=["diabetes", "hypertension", "hyperlipidemia"],
    difficulty="hard",
    tags=["complex", "multiple-conditions", "routine-followup"]
)


# =============================================================================
# TEST SUITE COLLECTION
# =============================================================================

MEDICAL_CONVERSATION_TESTS: List[TestCase] = [
    # Diabetes
    DIABETES_CHECKUP,
    DIABETES_NEW_DIAGNOSIS,
    # Cardiovascular
    HYPERTENSION_FOLLOWUP,
    CHOLESTEROL_DISCUSSION,
    # Respiratory
    ASTHMA_VISIT,
    # Pain
    CHRONIC_PAIN,
    # Mental Health
    DEPRESSION_SCREENING,
    # Complex
    COMPLEX_MULTI_CONDITION,
]


def get_test_suite(
    category: str = None,
    difficulty: str = None,
    tags: List[str] = None
) -> List[TestCase]:
    """
    Get filtered test cases.

    Args:
        category: Filter by category (diabetes, cardiovascular, etc.)
        difficulty: Filter by difficulty (easy, medium, hard)
        tags: Filter by tags (must have all specified tags)

    Returns:
        List of matching test cases
    """
    tests = MEDICAL_CONVERSATION_TESTS

    if category:
        tests = [t for t in tests if t.category == category]

    if difficulty:
        tests = [t for t in tests if t.difficulty == difficulty]

    if tags:
        tests = [t for t in tests if all(tag in t.tags for tag in tags)]

    return tests


def get_test_by_name(name: str) -> Optional[TestCase]:
    """Get a specific test case by name."""
    for test in MEDICAL_CONVERSATION_TESTS:
        if test.name == name:
            return test
    return None
