# services/translation_service.py
"""
Enhanced Translation Service for Medical Journal Application

This service provides Google Translate API integration with comprehensive error handling,
structured responses, and detailed logging for debugging medical translation accuracy.

Key Features:
- Environment variable security for API keys
- Comprehensive error handling for API failures
- Structured response format for consistent data handling
- Source language detection for verification
- Medical context optimization
- Detailed logging for debugging translation issues

Legal Compliance Note:
This service processes text that patients have already heard during medical visits,
serving as language assistance rather than content creation, which supports the
legal positioning as assistive technology.
"""

import requests
import os
from dotenv import load_dotenv
from typing import Dict, Any, Optional
import logging

# Configure logging for translation debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class TranslationError(Exception):
    """Custom exception for translation-specific errors"""
    pass

async def translate_text(text: str, target_lang: str, source_lang: Optional[str] = None) -> Dict[str, Any]:
    """
    Translate text using Google Translate API with comprehensive error handling.
    
    This function is designed specifically for medical translation contexts where
    accuracy is crucial and families need reliable language assistance.
    
    Args:
        text (str): The text to translate (typically medical conversation content)
        target_lang (str): Target language code (e.g., 'vi' for Vietnamese, 'es' for Spanish)
        source_lang (Optional[str]): Source language code. If None, Google will auto-detect.
    
    Returns:
        Dict[str, Any]: Structured response containing:
            - translated_text: The translated content
            - source_language: Detected or specified source language
            - target_language: The target language used
            - confidence: Translation confidence (if available)
            - success: Boolean indicating if translation succeeded
            - error_message: Error details if translation failed
    
    Raises:
        TranslationError: When translation fails due to API issues or invalid input
    """
    
    # Input validation
    if not text or not text.strip():
        logger.warning("Empty text provided for translation")
        return {
            "translated_text": "",
            "source_language": "unknown",
            "target_language": target_lang,
            "confidence": 0.0,
            "success": False,
            "error_message": "No text provided for translation"
        }
    
    # Validate target language format
    if not target_lang or len(target_lang.strip()) < 2:
        logger.error(f"Invalid target language code: {target_lang}")
        return {
            "translated_text": text,  # Return original text as fallback
            "source_language": "unknown",
            "target_language": target_lang,
            "confidence": 0.0,
            "success": False,
            "error_message": "Invalid target language code provided"
        }
    
    try:
        # Google Translate API endpoint
        url = "https://translation.googleapis.com/language/translate/v2"
        
        # Get API key from environment variables for security
        api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
        if not api_key:
            logger.error("Google Translate API key not found in environment variables")
            raise TranslationError("Translation service not configured properly")
        
        # Prepare API request parameters
        params = {
            "q": text.strip(),  # Remove leading/trailing whitespace
            "target": target_lang.strip().lower(),
            "key": api_key,
            "format": "text"  # Ensure plain text handling for medical content
        }
        
        # Add source language if specified (helps with accuracy)
        if source_lang:
            params["source"] = source_lang.strip().lower()
        
        # Log translation attempt (without sensitive data)
        logger.info(f"Attempting translation to {target_lang} for text length: {len(text)}")
        
        # Make API request with timeout to prevent hanging
        response = requests.get(url, params=params, timeout=10)
        
        # Check if the API call was successful
        if response.status_code == 200:
            try:
                result = response.json()
                
                # Extract translation data from API response
                translation_data = result["data"]["translations"][0]
                translated_text = translation_data["translatedText"]
                detected_source = translation_data.get("detectedSourceLanguage", "unknown")
                
                # Log successful translation
                logger.info(f"Translation successful: {len(translated_text)} characters")
                
                return {
                    "translated_text": translated_text,
                    "source_language": source_lang if source_lang else detected_source,
                    "target_language": target_lang,
                    "confidence": 0.95,  # Google doesn't provide confidence scores, using high default
                    "success": True,
                    "error_message": None
                }
                
            except (KeyError, IndexError) as parse_error:
                logger.error(f"Failed to parse Google Translate response: {parse_error}")
                raise TranslationError(f"Invalid response format from translation service")
                
        elif response.status_code == 400:
            logger.error(f"Bad request to Google Translate API: {response.text}")
            return {
                "translated_text": text,  # Return original as fallback
                "source_language": "unknown",
                "target_language": target_lang,
                "confidence": 0.0,
                "success": False,
                "error_message": "Invalid translation request - please check language codes"
            }
            
        elif response.status_code == 403:
            logger.error("Google Translate API key invalid or quota exceeded")
            return {
                "translated_text": text,  # Return original as fallback
                "source_language": "unknown", 
                "target_language": target_lang,
                "confidence": 0.0,
                "success": False,
                "error_message": "Translation service unavailable - please try again later"
            }
            
        elif response.status_code == 429:
            logger.warning("Google Translate API rate limit exceeded")
            return {
                "translated_text": text,  # Return original as fallback
                "source_language": "unknown",
                "target_language": target_lang,
                "confidence": 0.0,
                "success": False,
                "error_message": "Translation service temporarily busy - please try again"
            }
            
        else:
            logger.error(f"Google Translate API error: {response.status_code} - {response.text}")
            return {
                "translated_text": text,  # Return original as fallback
                "source_language": "unknown",
                "target_language": target_lang,
                "confidence": 0.0,
                "success": False,
                "error_message": f"Translation service error (code: {response.status_code})"
            }
            
    except requests.exceptions.Timeout:
        logger.error("Translation request timed out")
        return {
            "translated_text": text,  # Return original as fallback
            "source_language": "unknown",
            "target_language": target_lang,
            "confidence": 0.0,
            "success": False,
            "error_message": "Translation request timed out - please check your connection"
        }
        
    except requests.exceptions.ConnectionError:
        logger.error("Failed to connect to translation service")
        return {
            "translated_text": text,  # Return original as fallback
            "source_language": "unknown",
            "target_language": target_lang,
            "confidence": 0.0,
            "success": False,
            "error_message": "Cannot connect to translation service - please check your internet connection"
        }
        
    except TranslationError:
        # Re-raise custom translation errors
        raise
        
    except Exception as unexpected_error:
        logger.error(f"Unexpected translation error: {str(unexpected_error)}")
        return {
            "translated_text": text,  # Return original as fallback
            "source_language": "unknown",
            "target_language": target_lang,
            "confidence": 0.0,
            "success": False,
            "error_message": f"Unexpected error during translation: {str(unexpected_error)}"
        }

def get_supported_languages() -> Dict[str, str]:
    """
    Get a dictionary of supported language codes for the medical journal app.
    
    Returns:
        Dict[str, str]: Language codes mapped to language names
    """
    return {
        "en": "English",
        "vi": "Vietnamese (Tiếng Việt)",
        "es": "Spanish (Español)",
        "zh": "Chinese (中文)",
        "fr": "French (Français)",
        "de": "German (Deutsch)",
        "it": "Italian (Italiano)",
        "pt": "Portuguese (Português)",
        "ja": "Japanese (日本語)",
        "ko": "Korean (한국어)",
        "ar": "Arabic (العربية)",
        "hi": "Hindi (हिन्दी)",
        "ru": "Russian (Русский)"
    }

def validate_language_code(lang_code: str) -> bool:
    """
    Validate if a language code is supported by the application.
    
    Args:
        lang_code (str): Language code to validate
        
    Returns:
        bool: True if language code is supported, False otherwise
    """
    supported_languages = get_supported_languages()
    return lang_code.lower() in supported_languages

# Testing function for development
async def test_translation_service():
    """
    Test function to verify translation service is working correctly.
    This function helps ensure the service works before integrating with the main app.
    """
    test_cases = [
        {"text": "Hello, how are you feeling today?", "target": "vi"},
        {"text": "Please take this medication twice daily", "target": "es"},
        {"text": "Your blood pressure is normal", "target": "zh"}
    ]
    
    print("Testing Translation Service...")
    for test in test_cases:
        result = await translate_text(test["text"], test["target"])
        print(f"Original: {test['text']}")
        print(f"Translated ({test['target']}): {result['translated_text']}")
        print(f"Success: {result['success']}")
        print("-" * 50)

# Module initialization message
print("Enhanced translation service loaded with comprehensive error handling")