# tests/security/test_security.py
from app.icloud.models.entities import iCloudConnection
from app.utils.encryption import Encryptor


def test_encrypted_icloud_password_not_readable(app, db_session, test_user, authorized_client):
    conn = iCloudConnection(user_id=test_user[1], encrypted_app_password=Encryptor().encrypt("pass"))
    db_session.add(conn)
    db_session.commit()
    # Check logs/responses don't expose (mock logging if needed)
    assert "pass" not in str(conn)
    response = authorized_client.get("/icloud/connect")  # Assume endpoint, check response
    assert "pass" not in response.data.decode()


def test_invalid_token_access_denied(client):
    response = client.post("/notion/connect", json={"user_id": 1, "code": "code", "redirect_uri": "http://localhost"},
                           headers={"X-CSRF-Token": client.csrf_token, "Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_xss_prevention_in_routes(authorized_client, app, test_user):
    payload = {"user_id": test_user[1], "block_size_minutes": "<script>alert(1)</script>", "allow_weekends": False,
               "max_blocks_per_day": 16, "work_hours": 7.6}
    response = authorized_client.post("/user/preferences", json=payload)
    assert "<script>" not in response.get_data(as_text=True)
    assert "&lt;script&gt;" in response.get_data(as_text=True) or response.status_code != 200


def test_sql_injection_vulnerability(authorized_client, app):
    payload = {"email": "test'@example.com", "password": "anything"}
    response = authorized_client.post("/auth/login", json=payload,
                                      headers={"X-CSRF-Token": authorized_client.csrf_token})
    assert response.status_code == 401
