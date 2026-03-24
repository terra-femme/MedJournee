from fastapi import APIRouter, Form
from models.text_input import TextInput
from services.translation_service import translate_text, translate_medical_term

router = APIRouter()

@router.post("/")
async def translate(input: TextInput):
    result = await translate_text(input.text, input.target_lang)
    return result

@router.get("/")
def test_translate():
    return {"message": "Translate router is loaded"}

@router.post("/medical-term/")
async def translate_medical_term_endpoint(
    term: str = Form(...),
    target_lang: str = Form(...),
    source_lang: str = Form("auto"),
):
    """
    Translate a medical term or abbreviation with clinical accuracy.

    Checks local abbreviation dictionary first (offline, instant), then falls back
    to Google Translate with a medical context prefix.
    """
    result = await translate_medical_term(term, target_lang, source_lang)
    return result