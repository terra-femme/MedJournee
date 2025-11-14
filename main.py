from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from routes import transcribe, translate, tts, journal, combined_translation, live_translation
from fastapi.responses import FileResponse
import os


app = FastAPI(title="MedJournee")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
async def list_routes():
    for route in app.routes:
        print(f"{route.path} → {route.name}")

# Add CORS middleware to allow frontend connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/test")
async def test():
    return {"message": "App is alive"}

app.include_router(transcribe.router, prefix="/transcribe")
app.include_router(translate.router, prefix="/translate")
app.include_router(journal.router, prefix="/journal")
app.include_router(combined_translation.router, prefix="/combined")
app.include_router(live_translation.router, prefix="/live-session")

@app.get("/")
async def serve_html():
    html_path = os.path.join("static", "mobile.html") # this controls your homepage
    return FileResponse(html_path)

