# tests/utils/custom_client.py
from flask.testing import FlaskClient


class CSRFClient(FlaskClient):
    @property
    def csrf_token(self):
        response = self.post("/auth/test-session", json={})
        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch CSRF token: {response.status_code} - {response.data.decode()}")
        data = response.get_json()
        if not data or "csrf_token" not in data:
            raise RuntimeError(f"Invalid CSRF response: {response.data.decode()}")
        return data["csrf_token"]
