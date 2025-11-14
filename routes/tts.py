print("TTS router loaded")

from fastapi import APIRouter
from models.text_input import TextInput
from services.tts_service import generate_audio

router = APIRouter()

@router.post("/")
async def tts(input: TextInput):
    audio_url = await generate_audio(input.text, input.target_lang)
    return {"audio_url": audio_url}