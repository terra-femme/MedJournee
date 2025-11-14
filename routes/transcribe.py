from fastapi import APIRouter, UploadFile
from services.whisper_service import transcribe_audio
from routes import transcribe

router = APIRouter()

@router.post("/")
async def transcribe(file: UploadFile):
    transcript = await transcribe_audio(file)
    return {"transcript": transcript}

@router.get("/")
async def test_transcribe():
    return {"message": "Transcription service is up and running."}  