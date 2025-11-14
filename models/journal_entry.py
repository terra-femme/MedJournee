from pydantic import BaseModel

class JournalEntry(BaseModel):
    transcript: str
    translation: str
    audio_url: str
    timestamp: str
    speaker: str