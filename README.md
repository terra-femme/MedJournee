# MedJournee

**A privacy-first medical journal app helping families overcome language barriers during healthcare visits**

## Overview

MedJournee is a personal assistive technology that provides real-time transcription, translation, and AI-powered summarization of medical conversations. Designed for families who face language challenges when visiting healthcare providers, the app automatically documents appointments and generates structured journal entries with treatment plans and family-friendly explanations of complex medical terms.

**Key Point**: This is a personal/family-use tool, not a healthcare provider service, which significantly reduces HIPAA compliance complexity.

## Core Features

- **Real-time transcription** using OpenAI Whisper (cloud-based for 95% accuracy with medical terminology)
- **Instant translation** via Google Translate API for multilingual conversations
- **Speaker identification** with color-coded display (blue for providers, green for family/patients)
- **Voice enrollment** using MFCC analysis to improve speaker recognition accuracy
- **AI-powered summaries** with GPT-4 generating structured journal entries
- **Privacy-first design**: Audio processed and immediately deleted, only AI summaries persisted

## Tech Stack

- **Backend**: FastAPI, Python
- **AI/ML**: OpenAI Whisper, GPT-4, AssemblyAI (speaker diarization), librosa (voice features)
- **Translation**: Google Translate API
- **Database**: Google Cloud SQL (MySQL)
- **Frontend**: React Native/Expo (mobile), HTML/JS (web testing interface)

## Current Status

Active development with functional core features including live transcription, translation, speaker diarization, and journal generation. Currently debugging speaker identification accuracy and optimizing the transcription-translation pipeline for real-time conversational flow.

## Privacy & Compliance

Audio is processed in real-time through 8-second chunks and immediately deleted after processing. Only AI-generated summaries are stored in the database, ensuring user privacy while maintaining medical documentation utility.

---

*Built to help families better understand and document their healthcare journey, regardless of language barriers.*
