#!/usr/bin/env python3
"""
Tests for the 2026-03-24 security amendments.

Covers:
    - Audit Step 2: JWT authentication on all data routes
    - Audit Step 4: Audio upload validation (content-type, file size)
    - Audit Step 8: CORS method/header restrictions + /metrics protection

Run:
    pytest tests/test_security_amendments.py -v
"""

import io
import time
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import jwt

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# Mock heavy external dependencies before any app import
# ─────────────────────────────────────────────────────────────────────────────
sys.modules["supabase"] = Mock()
sys.modules["supabase"].create_client = Mock()
sys.modules["supabase"].Client = Mock
sys.modules["openai"] = Mock()
sys.modules["openai"].OpenAI = Mock

# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

TEST_JWT_SECRET = "test-supabase-jwt-secret-for-testing-only"  # pragma: allowlist secret
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


def make_token(
    user_id: str = TEST_USER_ID,
    secret: str = TEST_JWT_SECRET,
    expired: bool = False,
    bad_audience: bool = False,
) -> str:
    """Generate a signed JWT for test use."""
    now = int(time.time())
    payload = {
        "sub": user_id,
        "aud": "wrong-audience" if bad_audience else "authenticated",
        "iat": now,
        "exp": now - 10 if expired else now + 3600,
        "role": "authenticated",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_headers(token: str | None = None) -> dict:
    """Return Authorization header dict for an HTTP test client."""
    t = token if token is not None else make_token()
    return {"Authorization": f"Bearer {t}"}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient with auth configured and external services mocked."""
    env = {
        "SUPABASE_URL": "https://test.supabase.co",
        "SUPABASE_KEY": "test-anon-key",                        # pragma: allowlist secret
        "SUPABASE_SERVICE_KEY": "test-service-key",             # pragma: allowlist secret
        "SUPABASE_JWT_SECRET": TEST_JWT_SECRET,                 # pragma: allowlist secret
        "OPENAI_API_KEY": "test-openai-key",                    # pragma: allowlist secret
        "ASSEMBLYAI_API_KEY": "test-assemblyai-key",            # pragma: allowlist secret
        "METRICS_API_KEY": "test-metrics-key",                  # pragma: allowlist secret
        "ENVIRONMENT": "testing",
    }
    with patch.dict("os.environ", env):
        with patch("services.database_service.create_client") as mock_db:
            mock_db.return_value = Mock()
            from fastapi.testclient import TestClient
            from main import app
            yield TestClient(app, raise_server_exceptions=False)


def tiny_audio(content_type: str = "audio/webm") -> tuple:
    """Return (filename, file-like, content_type) for a minimal upload."""
    return ("test.webm", io.BytesIO(b"\x00" * 10), content_type)


# ─────────────────────────────────────────────────────────────────────────────
# Audit Step 2 — Authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthMissingToken:
    """All data endpoints must reject requests with no token."""

    def test_appointments_list_no_token(self, client):
        r = client.get("/appointments/list/some-user")
        assert r.status_code == 403, f"Expected 403, got {r.status_code}"

    def test_appointments_create_no_token(self, client):
        r = client.post("/appointments/create", data={
            "user_id": "u1", "family_id": "f1", "scheduled_date": "2026-04-01"
        })
        assert r.status_code == 403

    def test_talking_points_list_no_token(self, client):
        r = client.get("/talking-points/appointment/some-appt")
        assert r.status_code == 403

    def test_talking_points_create_no_token(self, client):
        r = client.post("/talking-points/create", data={
            "appointment_id": "a1", "text": "Ask about medication"
        })
        assert r.status_code == 403

    def test_costs_summary_no_token(self, client):
        r = client.get("/costs/summary/some-user")
        assert r.status_code == 403

    def test_costs_history_no_token(self, client):
        r = client.get("/costs/history/some-user")
        assert r.status_code == 403

    def test_gladia_session_no_token(self, client):
        r = client.post("/gladia/session", json={})
        assert r.status_code == 403

    def test_enrollment_list_no_token(self, client):
        r = client.get("/enrollment/list/some-family")
        assert r.status_code == 403


class TestAuthInvalidToken:
    """Malformed or tampered tokens must be rejected with 401."""

    def test_garbage_token(self, client):
        r = client.get(
            "/appointments/list/u1",
            headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert r.status_code == 401

    def test_expired_token(self, client):
        token = make_token(expired=True)
        r = client.get("/appointments/list/u1", headers=auth_headers(token))
        assert r.status_code == 401
        assert "expired" in r.json()["detail"].lower()

    def test_wrong_audience(self, client):
        token = make_token(bad_audience=True)
        r = client.get("/appointments/list/u1", headers=auth_headers(token))
        assert r.status_code == 401

    def test_wrong_secret(self, client):
        token = make_token(secret="completely-wrong-secret")  # pragma: allowlist secret
        r = client.get("/appointments/list/u1", headers=auth_headers(token))
        assert r.status_code == 401

    def test_malformed_bearer_scheme(self, client):
        """Token provided but with wrong scheme keyword."""
        r = client.get(
            "/appointments/list/u1",
            headers={"Authorization": "Token " + make_token()}
        )
        assert r.status_code == 403


class TestAuthValidToken:
    """Valid tokens must be accepted and requests processed normally."""

    def test_appointments_list_with_token(self, client):
        """Authenticated request reaches the handler (not blocked at auth layer)."""
        with patch("services.appointments_service.AppointmentsService.list_appointments") as mock:
            mock.return_value = []
            r = client.get("/appointments/list/u1", headers=auth_headers())
        # 200 means auth passed and handler ran; 500 means handler ran but service failed
        assert r.status_code in (200, 500), f"Auth blocked a valid token: {r.status_code}"

    def test_costs_summary_with_token(self, client):
        r = client.get("/costs/summary/u1", headers=auth_headers())
        assert r.status_code in (200, 500)

    def test_talking_points_list_with_token(self, client):
        with patch("services.talking_points_service.TalkingPointsService.list_talking_points") as mock:
            mock.return_value = []
            r = client.get("/talking-points/appointment/a1", headers=auth_headers())
        assert r.status_code in (200, 500)


class TestPublicEndpointsUnchanged:
    """Health checks and static pages must remain accessible without auth."""

    def test_root_health(self, client):
        r = client.get("/test")
        assert r.status_code == 200

    def test_api_info(self, client):
        r = client.get("/api")
        assert r.status_code == 200

    def test_realtime_health(self, client):
        r = client.get("/realtime/health/")
        assert r.status_code == 200

    def test_enrollment_health(self, client):
        r = client.get("/enrollment/health")
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Audit Step 4 — Upload validation
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadValidationContentType:
    """Requests with disallowed content types must be rejected with 415."""

    def test_zip_file_rejected(self, client):
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": ("malware.zip", io.BytesIO(b"PK\x03\x04"), "application/zip")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code == 415, f"Expected 415 for zip, got {r.status_code}"

    def test_pdf_file_rejected(self, client):
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": ("doc.pdf", io.BytesIO(b"%PDF"), "application/pdf")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code == 415

    def test_html_file_rejected(self, client):
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": ("x.html", io.BytesIO(b"<html>"), "text/html")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code == 415

    def test_webm_audio_accepted(self, client):
        """audio/webm must not be rejected at the content-type gate."""
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": tiny_audio("audio/webm")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        # 415 means content-type was rejected — that's a failure for a valid type
        assert r.status_code != 415, "audio/webm was wrongly rejected"

    def test_wav_audio_accepted(self, client):
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": tiny_audio("audio/wav")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code != 415

    def test_video_webm_accepted(self, client):
        """Chromium records audio as video/webm — must not be rejected."""
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": tiny_audio("video/webm")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code != 415

    def test_octet_stream_accepted(self, client):
        """Browser fallback type — must not be rejected."""
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": tiny_audio("application/octet-stream")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code != 415


class TestUploadValidationFileSize:
    """Files over 50 MB must be rejected with 413."""

    def test_oversized_file_rejected(self, client):
        big = io.BytesIO(b"\x00" * (51 * 1024 * 1024))  # 51 MB
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": ("big.webm", big, "audio/webm")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code == 413, f"Expected 413 for 51 MB file, got {r.status_code}"

    def test_normal_file_not_rejected_for_size(self, client):
        normal = io.BytesIO(b"\x00" * (1 * 1024 * 1024))  # 1 MB
        r = client.post(
            "/enrollment/enroll",
            headers=auth_headers(),
            files={"audio": ("ok.webm", normal, "audio/webm")},
            data={"family_id": "f1", "speaker_name": "Alice"},
        )
        assert r.status_code != 413, "1 MB file was wrongly rejected for size"

    def test_finalize_session_oversized_rejected(self, client):
        """Size validation also covers the main pipeline endpoint."""
        big = io.BytesIO(b"\x00" * (51 * 1024 * 1024))
        r = client.post(
            "/realtime/finalize-session/",
            headers=auth_headers(),
            files={"file": ("session.webm", big, "audio/webm")},
            data={
                "session_id": "s1", "family_id": "f1",
                "user_id": "u1", "patient_name": "Test Patient",
            },
        )
        assert r.status_code == 413


# ─────────────────────────────────────────────────────────────────────────────
# Audit Step 8 — CORS and /metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestCORSRestrictions:
    """CORS preflight must only allow the configured methods and headers."""

    ALLOWED_ORIGIN = "http://localhost:3000"

    def test_preflight_get_allowed(self, client):
        r = client.options(
            "/appointments/list/u1",
            headers={
                "Origin": self.ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert r.status_code == 200
        allow = r.headers.get("access-control-allow-methods", "")
        assert "GET" in allow

    def test_preflight_post_allowed(self, client):
        r = client.options(
            "/appointments/create",
            headers={
                "Origin": self.ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type, Authorization",
            },
        )
        assert r.status_code == 200

    def test_authorization_header_allowed(self, client):
        """Authorization header must appear in access-control-allow-headers."""
        r = client.options(
            "/appointments/list/u1",
            headers={
                "Origin": self.ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        allow_headers = r.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" in allow_headers

    def test_unknown_origin_not_reflected(self, client):
        """An origin not in the allowlist must not be echoed back."""
        r = client.get(
            "/test",
            headers={"Origin": "https://evil.example.com"},
        )
        origin = r.headers.get("access-control-allow-origin", "")
        assert "evil.example.com" not in origin


class TestMetricsProtection:
    """The /metrics endpoint must require a valid X-Metrics-Key header."""

    def test_metrics_no_key_returns_401(self, client):
        r = client.get("/metrics")
        assert r.status_code == 401, f"Expected 401 with no key, got {r.status_code}"

    def test_metrics_wrong_key_returns_401(self, client):
        r = client.get("/metrics", headers={"X-Metrics-Key": "wrong-key"})
        assert r.status_code == 401

    def test_metrics_correct_key_passes(self, client):
        r = client.get("/metrics", headers={"X-Metrics-Key": "test-metrics-key"})
        # 200 = metrics served; 500 = telemetry module error (acceptable in test env)
        assert r.status_code in (200, 500), f"Correct key was rejected: {r.status_code}"
