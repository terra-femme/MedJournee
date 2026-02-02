# services/translation_service.py
"""
FREE Translation Service for MedJournee

Uses deep-translator library - FREE Google Translate, no API key needed!
No dependency conflicts with OpenAI/httpx.

Install: pip install deep-translator
"""

from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Try to import deep-translator (free, no conflicts)
try:
    from deep_translator import GoogleTranslator
    FREE_TRANSLATE_AVAILABLE = True
    logger.info("✅ FREE Google Translate loaded via deep-translator")
except ImportError:
    FREE_TRANSLATE_AVAILABLE = False
    logger.warning("⚠️ deep-translator not installed. Run: pip install deep-translator")


async def translate_text(text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Translate text using FREE Google Translate (no API key required).
    """
    
    # Input validation
    if not text or not text.strip():
        return {
            "translated_text": "",
            "source_language": "unknown",
            "target_language": target_lang,
            "success": False,
            "error_message": "No text provided"
        }
    
    if not target_lang or len(target_lang.strip()) < 2:
        return {
            "translated_text": text,
            "source_language": "unknown",
            "target_language": target_lang,
            "success": False,
            "error_message": "Invalid target language"
        }
    
    # Use FREE deep-translator library
    if FREE_TRANSLATE_AVAILABLE:
        return await _translate_free(text, target_lang, source_lang)
    else:
        return await _translate_paid_api(text, target_lang, source_lang)


async def _translate_free(text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Translate using FREE deep-translator library.
    No API key, no quotas, no billing, no dependency conflicts!
    """
    try:
        # Normalize language codes
        target = target_lang.lower().strip()
        source = 'auto'
        
        if source_lang and source_lang.lower() not in ['auto', 'automatic', '']:
            source = source_lang.lower().strip()
        
        # Handle Chinese variants
        if target in ['zh', 'chinese']:
            target = 'zh-CN'
        elif target == 'zh-tw':
            target = 'zh-TW'
        
        # Create translator and translate
        translator = GoogleTranslator(source=source, target=target)
        translated_text = translator.translate(text.strip())
        
        logger.info(f"FREE translate: {len(text)} chars -> {target}")
        
        return {
            "translated_text": translated_text,
            "source_language": source,
            "target_language": target_lang,
            "confidence": 0.95,
            "success": True,
            "error_message": None,
            "method": "free_deep_translator"
        }
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Free translation error: {error_msg}")
        
        return {
            "translated_text": text,
            "source_language": "unknown",
            "target_language": target_lang,
            "success": False,
            "error_message": f"Translation failed: {error_msg}"
        }


async def _translate_paid_api(text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
    """Fallback to paid API if deep-translator not installed"""
    import requests
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    try:
        url = "https://translation.googleapis.com/language/translate/v2"
        api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
        
        if not api_key:
            return {
                "translated_text": text,
                "success": False,
                "error_message": "Install deep-translator: pip install deep-translator"
            }
        
        params = {
            "q": text.strip(),
            "target": target_lang.strip().lower(),
            "key": api_key,
            "format": "text"
        }
        
        if source_lang and source_lang.lower() not in ['auto', '']:
            params["source"] = source_lang.strip().lower()
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            translation_data = result["data"]["translations"][0]
            return {
                "translated_text": translation_data["translatedText"],
                "source_language": translation_data.get("detectedSourceLanguage", source_lang or "unknown"),
                "target_language": target_lang,
                "success": True,
                "method": "paid_api"
            }
        else:
            return {
                "translated_text": text,
                "success": False,
                "error_message": f"API error: {response.status_code}"
            }
            
    except Exception as e:
        return {
            "translated_text": text,
            "success": False,
            "error_message": str(e)
        }


def get_supported_languages() -> Dict[str, str]:
    """Get supported language codes"""
    return {
        "en": "English",
        "vi": "Vietnamese",
        "es": "Spanish",
        "zh-CN": "Chinese Simplified",
        "zh-TW": "Chinese Traditional",
        "fr": "French",
        "de": "German",
        "ja": "Japanese",
        "ko": "Korean",
        "th": "Thai",
        "tl": "Tagalog",
    }


print("Translation service loaded - using FREE deep-translator")
