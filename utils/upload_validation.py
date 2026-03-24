# utils/upload_validation.py
"""
Audio file upload validation.

Checks content type and file size before the file is passed to any agent
or external API. Call this at the top of every endpoint that accepts an
UploadFile audio argument.

Why read into memory here?
--------------------------
FastAPI's UploadFile is a streaming object — there is no size property until
the body has been consumed. We read the full bytes once here, check the size,
then reset the read pointer to 0 so downstream code can call file.read()
normally without knowing validation already occurred.

The 50 MB ceiling is well above Whisper's 25 MB limit, giving room for the
finalize-session full-recording blob while still blocking runaway uploads.
"""

from fastapi import HTTPException, UploadFile

# Browsers may report any of these for recorded audio depending on codec and OS.
# "application/octet-stream" is a fallback when the browser can't determine the type.
# "video/webm" occurs on some Chromium builds even for audio-only WebM recordings.
ALLOWED_AUDIO_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "audio/webm",
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/m4a",
        "audio/aac",
        "audio/x-m4a",
        "video/webm",
        "application/octet-stream",
    }
)

MAX_AUDIO_BYTES: int = 50 * 1024 * 1024  # 50 MB


async def validate_audio_upload(file: UploadFile) -> bytes:
    """
    Validate content type and size of an uploaded audio file.

    Parameters
    ----------
    file : UploadFile
        The incoming file from a FastAPI Form/File parameter.

    Returns
    -------
    bytes
        The full file contents (already read). The file's internal read
        pointer is reset to 0 before returning.

    Raises
    ------
    HTTPException 415
        If the content type is set and is not in the allowed set.
    HTTPException 413
        If the file exceeds MAX_AUDIO_BYTES (50 MB).
    """
    content_type = (file.content_type or "").lower().split(";")[0].strip()

    if content_type and content_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported media type '{content_type}'. "
                "Accepted types: audio/webm, audio/wav, audio/mp4, "
                "audio/m4a, audio/aac, audio/ogg"
            ),
        )

    data = await file.read()

    if len(data) > MAX_AUDIO_BYTES:
        size_mb = len(data) / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({size_mb:.1f} MB). "
                f"Maximum allowed size is {MAX_AUDIO_BYTES // (1024 * 1024)} MB."
            ),
        )

    await file.seek(0)
    return data
