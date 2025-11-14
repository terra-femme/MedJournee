print("Journal router loaded")

from fastapi import APIRouter
from models.journal_entry import JournalEntry

router = APIRouter()

@router.post("/")
async def create_entry(entry: JournalEntry):
    # Deprecated endpoint - journal creation now handled by combined_translation.py
    return {
        "status": "deprecated", 
        "message": "Journal creation moved to /combined/quick-journal-from-segments/"
    }