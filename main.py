# main.py
"""
MedJournee FastAPI Application

Production-grade medical journal app with:
- Multi-agent pipeline architecture
- Quality gates and self-correction
- Real-time transcription and translation
- Schema-driven design
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from routes import transcribe, translate, tts, journal, combined_translation, live_translation
from routes import realtime_routes, enrollment, appointments, talking_points
import asyncio
import os


# =============================================================================
# TIMEOUT MIDDLEWARE
# =============================================================================

class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Request timeout middleware.

    Ensures all requests complete within a maximum time limit.
    Returns 504 Gateway Timeout if exceeded.
    """

    def __init__(self, app, timeout_seconds: float = 300.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next):
        try:
            # Use asyncio.timeout for Python 3.11+
            async with asyncio.timeout(self.timeout_seconds):
                return await call_next(request)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "error": "Request timeout",
                    "detail": f"Request exceeded maximum time of {self.timeout_seconds}s",
                    "timeout_seconds": self.timeout_seconds
                }
            )


# Create FastAPI app
app = FastAPI(
    title="MedJournee API",
    description="Privacy-first medical journaling for families with language barriers",
    version="2.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://medjournee-backend.onrender.com",  # Render PWA frontend
        "http://localhost:8000",             # Local development
        "http://localhost:3000",             # Local development alternative
        "http://localhost:8080",             # Local development alternative
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Timeout middleware (5 minute max for long-running operations)
app.add_middleware(TimeoutMiddleware, timeout_seconds=300.0)

# Include routers
app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcription"])
app.include_router(translate.router, prefix="/translate", tags=["Translation"])
app.include_router(journal.router, prefix="/journal", tags=["Journal"])
app.include_router(combined_translation.router, prefix="/combined", tags=["Combined"])
app.include_router(live_translation.router, prefix="/live-session", tags=["Live Session"])
app.include_router(realtime_routes.router, prefix="/realtime", tags=["Real-time Pipeline"])
app.include_router(enrollment.router, prefix="/enrollment", tags=["Voice Enrollment"])
app.include_router(appointments.router, prefix="/appointments", tags=["Appointments"])
app.include_router(talking_points.router, prefix="/talking-points", tags=["Talking Points"])


@app.get("/sw.js")
async def serve_service_worker():
    """Serve service worker from root scope"""
    return FileResponse(
        os.path.join("static", "sw.js"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"}
    )


@app.get("/")
async def serve_html():
    """Serve the main application"""
    html_path = os.path.join("static", "mobile.html")
    return FileResponse(html_path)


@app.get("/enroll")
async def serve_enrollment():
    """Serve the voice enrollment page"""
    html_path = os.path.join("static", "enrollment.html")
    return FileResponse(html_path)


@app.get("/api")
async def api_info():
    """API information endpoint"""
    return {
        "name": "MedJournee API",
        "version": "2.0.0",
        "architecture": "multi-agent-pipeline",
        "features": {
            "agents": [
                "TranscriptionAgent - Audio to text with hallucination filtering",
                "DiarizationAgent - Speaker identification (AssemblyAI)",
                "TranslationAgent - Bidirectional translation (FREE)",
                "TerminologyAgent - Medical term detection (offline)",
                "SummarizationAgent - Journal generation with self-correction"
            ],
            "quality_gates": True,
            "retry_logic": True,
            "self_correction": True,
            "state_management": True
        },
        "endpoints": {
            "realtime": {
                "/realtime/instant-transcribe/": "Real-time transcription during recording",
                "/realtime/finalize-session/": "Full processing after recording",
                "/realtime/health/": "Health check"
            },
            "enrollment": {
                "/enroll": "Voice enrollment UI page",
                "/enrollment/enroll": "Enroll a speaker's voice (POST)",
                "/enrollment/list/{family_id}": "List enrolled speakers",
                "/enrollment/delete/{enrollment_id}": "Delete enrollment",
                "/enrollment/test-recognition": "Test voice recognition"
            },
            "appointments": {
                "/appointments/create": "Create new appointment (POST)",
                "/appointments/list/{user_id}": "List all appointments",
                "/appointments/month/{user_id}/{year}/{month}": "Get appointments for calendar month",
                "/appointments/upcoming/{user_id}": "Get upcoming appointments",
                "/appointments/{id}": "Get appointment with talking points",
                "/appointments/{id}/link/{entry_id}": "Link to journal entry"
            },
            "talking_points": {
                "/talking-points/create": "Add talking point to appointment (POST)",
                "/talking-points/appointment/{appointment_id}": "List points for appointment",
                "/talking-points/{id}/toggle": "Toggle done status",
                "/talking-points/reorder": "Reorder points (POST)"
            },
            "legacy": {
                "/transcribe/": "Basic transcription",
                "/translate/": "Basic translation",
                "/journal/": "Journal management",
                "/combined/": "Combined transcription + translation",
                "/live-session/": "Legacy live session"
            }
        }
    }


@app.get("/test")
async def test():
    """Health check endpoint"""
    return {"message": "App is alive", "status": "healthy"}


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus exposition format for scraping.
    """
    from fastapi.responses import Response
    try:
        from telemetry.metrics import get_metrics_collector
        collector = get_metrics_collector()
        return Response(
            content=collector.get_prometheus_metrics(),
            media_type=collector.get_content_type()
        )
    except ImportError:
        return Response(
            content=b"# Telemetry module not available\n",
            media_type="text/plain"
        )


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    print("=" * 60)
    print("MedJournee API Starting")
    print("=" * 60)
    print("Architecture: Multi-Agent Pipeline (Production)")
    print("Features:")
    print("  - Quality Gates: Validate output at each stage")
    print("  - Retry Logic: Exponential backoff on failures")
    print("  - Self-Correction: Agents critique and fix output")
    print("  - State Management: Full pipeline tracking")
    print("=" * 60)
    print("Agents:")
    print("  1. TranscriptionAgent - Audio to text (Whisper)")
    print("  2. DiarizationAgent - Speaker identification (AssemblyAI)")
    print("  3. TranslationAgent - Bidirectional (FREE deep-translator)")
    print("  4. TerminologyAgent - Medical terms (offline dictionary)")
    print("  5. SummarizationAgent - Journal generation (GPT-4)")
    print("=" * 60)
    print("Routes:")
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'name'):
            print(f"  {route.path} -> {route.name}")
    print("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
