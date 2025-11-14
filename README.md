# MedJournee

An AI-powered medical conversation transcription and translation tool designed to bridge language barriers between healthcare providers and patients. Uses OpenAI Whisper for speech-to-text and Google Translate API for real-time multilingual translation.

## 🎯 The Problem

In the US healthcare system, language barriers affect 25 million people with limited English proficiency. These patients face:
- Increased medical errors and adverse events
- Lower quality of care and patient satisfaction
- Difficulty understanding diagnoses, treatment plans, and medication instructions
- Family members struggling to participate in care decisions

Medical interpreters aren't always available, and families often need to review conversations later. MedJournee aims to provide an AI-assisted tool to help families understand and document important medical conversations.

## 🏥 Use Case

A family member attending a doctor's appointment can:
1. Record the medical conversation (with consent)
2. Get real-time transcription via Whisper AI
3. Translate the conversation to their preferred language
4. Review and save the transcript for future reference

**Target Users**: Families with limited English proficiency navigating the US healthcare system

## 🛠️ Tech Stack

- **Speech Recognition**: OpenAI Whisper (local processing)
- **Translation**: Google Translate API
- **Backend**: Python with FastAPI
- **Frontend**: (Planned) React or vanilla JavaScript
- **Database**: (Planned) SQLite for transcript storage

## ✨ Current Implementation

- ✅ Whisper AI integration for audio transcription
- ✅ FastAPI backend structure
- ✅ Audio file upload and processing pipeline
- 🚧 Translation integration (in progress)
- 🚧 Privacy-preserving architecture (see challenges below)

## 🔒 Privacy Challenges & Development Pause

**Status**: Development paused for privacy architecture redesign

### Current Challenge: Balancing Translation Quality with Data Privacy

This project has surfaced a critical design tension:

**The Problem:**
- **Google Translate API** provides superior translation quality but requires sending potentially sensitive medical data (PHI) to Google's servers
- **Local translation models** (like MarianMT, NLLB) can run on-device but have significantly lower accuracy for medical terminology
- Medical conversations contain Protected Health Information (PHI) under HIPAA

**Why This Matters:**
Healthcare data is uniquely sensitive. A system that:
- Sends PHI to third-party servers without proper safeguards violates patient trust and potentially HIPAA
- Uses inaccurate local translation could lead to dangerous misunderstandings in medical contexts
- Both outcomes are unacceptable for a healthcare application

### Potential Solutions Being Researched

1. **De-identification Pipeline**: Strip PHI before translation (names, dates, locations, MRNs)
   - Challenge: Maintaining conversation context and coherence

2. **On-premise Translation Models**: Fine-tune local models on medical terminology
   - Challenge: Requires significant compute resources and medical translation datasets

3. **Hybrid Approach**: Local processing for sensitive terms, API for general language
   - Challenge: Complex architecture, potential for inconsistent translations

4. **Business Associate Agreement (BAA)**: Use HIPAA-compliant translation service
   - Challenge: Cost considerations, limited free-tier options for learning project

### Next Steps

- Research HIPAA-compliant translation APIs with developer tiers
- Experiment with medical-domain fine-tuned local translation models
- Implement de-identification pipeline for testing
- Consult with healthcare privacy experts on architecture decisions

## 🎓 What This Project Demonstrates

Even though development is paused, this project showcases:
- **Healthcare compliance awareness**: Understanding HIPAA and PHI protection requirements
- **Responsible AI development**: Recognizing when to pause rather than deploy an insecure solution
- **Problem-solving approach**: Identifying trade-offs and researching multiple solution paths
- **AI integration**: Successfully implemented Whisper for accurate medical speech recognition
- **Domain knowledge**: Understanding that healthcare applications require higher standards than typical software

## 🚀 Running the Current Implementation

**Note**: This project is incomplete and should not be used with real patient data.

```bash
# Clone repository
git clone https://github.com/terra-femme/MedJournee.git
cd MedJournee

# Install dependencies
pip install -r requirements.txt

# Run backend (transcription only)
python backend/main.py
```

## 🔮 Future Vision (Post-Privacy Solution)

Once privacy architecture is resolved:
- Real-time conversation transcription and translation
- Mobile application for easy recording
- Transcript storage with encryption
- Export functionality for sharing with healthcare providers
- Multi-speaker detection and labeling
- Medical terminology glossary for complex terms
- Integration with patient portals

## 💡 Why This Matters

This pause in development represents the reality of healthcare software engineering: **privacy and patient safety must come first**. Building something that works is easy. Building something that works *safely* in healthcare requires careful consideration and sometimes, patience.

## 🤝 Feedback Welcome

If you have experience with:
- HIPAA-compliant API solutions
- Medical NLP and translation
- Privacy-preserving AI architectures
- Healthcare software development

I'd love to hear your thoughts! Open an issue or reach out.

## 📧 Contact

Kris - [terra-femme](https://github.com/terra-femme)

---

*Building with privacy and patient safety as non-negotiable requirements*
