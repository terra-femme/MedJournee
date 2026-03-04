#!/usr/bin/env python3
"""
Unit Tests for API Routes

Tests for routes:
- costs.py
- appointments.py
- talking_points.py

Usage:
    pytest tests/test_routes.py -v
    pytest tests/test_routes.py::TestCostsRoutes -v
    pytest tests/test_routes.py -k "test_get" -v
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Must mock before importing main
sys.modules['supabase'] = Mock()
sys.modules['supabase'].create_client = Mock()
sys.modules['supabase'].Client = Mock

# Mock other external dependencies
sys.modules['openai'] = Mock()
sys.modules['openai'].OpenAI = Mock

# Now import FastAPI test client and main app
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client with mocked dependencies"""
    # Set environment variables
    with patch.dict('os.environ', {
        'SUPABASE_URL': 'https://test.supabase.co',
        'SUPABASE_KEY': 'test-key',  # pragma: allowlist secret
        'SUPABASE_SERVICE_KEY': 'test-service-key',  # pragma: allowlist secret
        'OPENAI_API_KEY': 'test-openai-key',  # pragma: allowlist secret
        'ASSEMBLYAI_API_KEY': 'test-assemblyai-key',  # pragma: allowlist secret
        'JWT_SECRET_KEY': 'test-jwt-secret',  # pragma: allowlist secret
        'ENVIRONMENT': 'testing'
    }):
        # Mock the database client creation
        with patch('services.database_service.create_client') as mock_create:
            mock_supabase = Mock()
            mock_create.return_value = mock_supabase

            # Import main after mocking
            from main import app
            return TestClient(app)


class TestHealthEndpoints:
    """Test basic health check endpoints"""

    def test_health_check(self, client):
        """Test /test endpoint returns healthy status"""
        response = client.get("/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "message" in data

    def test_api_info(self, client):
        """Test /api endpoint returns API information"""
        response = client.get("/api")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "MedJournee API"
        assert "version" in data
        assert "endpoints" in data


class TestSecurityHeaders:
    """Test security headers are present on responses"""

    def test_security_headers_present(self, client):
        """Test that security headers are added to responses"""
        response = client.get("/test")

        assert response.status_code == 200
        # Check for security headers
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "X-Frame-Options" in response.headers
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_cors_headers_present(self, client):
        """Test CORS headers on API endpoints"""
        response = client.get("/api", headers={"Origin": "http://localhost:3000"})

        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


class TestCostsRoutes:
    """Test /costs endpoints"""

    def test_get_session_costs_endpoint_exists(self, client):
        """Test that the session costs endpoint exists"""
        # This will return an error since we don't have real data,
        # but it should not be a 404 (endpoint exists)
        response = client.get("/costs/session/test-session-123")
        # Should be 200, 404 (not found), or 500 (server error) - NOT 404 for route not found
        assert response.status_code != 404

    def test_get_user_costs_endpoint_exists(self, client):
        """Test that the user costs endpoint exists"""
        response = client.get("/costs/user/test-user")
        assert response.status_code != 404


class TestAppointmentsRoutes:
    """Test /appointments endpoints"""

    def test_list_appointments_endpoint_exists(self, client):
        """Test that list appointments endpoint exists"""
        response = client.get("/appointments/list/test-user")
        # 404 is for "user not found", not "route not found"
        # Check it's not the FastAPI "Not Found" HTML response
        assert response.status_code != 404 or "detail" in response.json()

    def test_get_appointment_endpoint_exists(self, client):
        """Test that get appointment endpoint exists"""
        response = client.get("/appointments/apt-123")
        assert response.status_code != 404

    def test_create_appointment_endpoint_exists(self, client):
        """Test that create appointment endpoint exists"""
        response = client.post("/appointments/create", json={})
        # Should get validation error (422), not route not found
        assert response.status_code in [422, 200, 500]

    def test_get_monthly_appointments_endpoint_exists(self, client):
        """Test that monthly appointments endpoint exists"""
        response = client.get("/appointments/month/test-user/2026/3")
        assert response.status_code != 404


class TestTalkingPointsRoutes:
    """Test /talking-points endpoints"""

    def test_list_talking_points_endpoint_exists(self, client):
        """Test that list talking points endpoint exists"""
        response = client.get("/talking-points/appointment/apt-456")
        assert response.status_code != 404

    def test_create_talking_point_endpoint_exists(self, client):
        """Test that create talking point endpoint exists"""
        response = client.post("/talking-points/create", json={})
        # Should get validation error (422), not route not found
        assert response.status_code in [422, 200, 500]

    def test_toggle_talking_point_endpoint_exists(self, client):
        """Test that toggle talking point endpoint exists"""
        response = client.post("/talking-points/tp-123/toggle")
        assert response.status_code != 404


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
