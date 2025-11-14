from pydantic import BaseModel

class TextInput(BaseModel):
    text: str
    target_lang: str

print("TextInput loaded")