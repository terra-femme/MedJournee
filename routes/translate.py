from fastapi import APIRouter
from models.text_input import TextInput
from services.translation_service import translate_text

router = APIRouter()

@router.post("/")
async def translate(input: TextInput):
    result = await translate_text(input.text, input.target_lang)
    return result

@router.get("/")
def test_translate():
    return {"message": "Translate router is loaded"}