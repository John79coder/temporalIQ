# tests/utils/test_utils.py
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import jwt
from flask import g, jsonify

from app.auth.models.entities import User
from app.utils.encryption import Encryptor
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import format_error_response, DataValidationError


def test_caching_service_set_get(app, caching_service):
    with app.app_context():
        caching_service.set("test-key", {"data": "value"}, timeout=60)
        result = caching_service.get("test-key")
        assert result == {"data": "value"}


def test_encryptor_encrypt_decrypt():
    encryptor = Encryptor()
    data = "test-data"
    encrypted = encryptor.encrypt(data)
    decrypted = encryptor.decrypt(encrypted)
    assert decrypted == data


def test_verify_jwt_decorator(app, db_session):
    with app.app_context():
        user = User(email="test@example.com", hashed_password="hashed", is_verified=True)
        db_session.add(user)
        db_session.commit()
        token = jwt.encode(
            {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            app.config["JWT_SECRET_KEY"],
            algorithm=app.config["JWT_ALGORITHM"]
        )

        @verify_jwt
        def test_jwt_route():
            return jsonify({"success": True})

        app._got_first_request = False
        app.add_url_rule("/test-jwt", view_func=test_jwt_route)
        client = app.test_client()
        response = client.get("/test-jwt", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json["success"] is True
        assert g.current_user.id == user.id


def test_csrf_protected_decorator(app, client, db_session):
    with app.app_context():
        @csrf_protected
        def test_csrf_route():
            return jsonify({"success": True})

        app._got_first_request = False
        app.add_url_rule("/test-csrf", view_func=test_csrf_route, methods=["POST"])
        response = client.post("/test-csrf", json={}, headers={"X-CSRF-Token": client.csrf_token})
        assert response.status_code == 200
        assert response.json["success"] is True


def test_format_error_response():
    error = DataValidationError("Invalid input")
    response, status = format_error_response(error, 400)
    assert response == {"type": "about:blank", "title": "DataValidationError", "status": 400, "detail": "Invalid input"}
    assert status == 400


def test_verify_jwt_expired_token(app, db_session):
    with app.app_context():
        user = User(email="test@example.com", hashed_password="hashed", is_verified=True)
        db_session.add(user)
        db_session.commit()
        token = jwt.encode(
            {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
            app.config["JWT_SECRET_KEY"],
            algorithm=app.config["JWT_ALGORITHM"]
        )

        @verify_jwt
        def test_expired_route():
            return jsonify({"success": True})

        app._got_first_request = False
        app.add_url_rule("/test-expired", view_func=test_expired_route)
        client = app.test_client()
        response = client.get("/test-expired", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "Token expired" in response.json["detail"]


def test_format_error_response_invalid_status():
    error = DataValidationError("Invalid input")
    response, status = format_error_response(error, 999)
    assert response == {"type": "about:blank", "title": "DataValidationError", "status": 999, "detail": "Invalid input"}
    assert status == 999


@patch("app.utils.endpoint_utils.jwt.decode", side_effect=jwt.ExpiredSignatureError)
def test_jwt_expiry_in_protected_routes(mock_decode, app, authorized_client):
    response = authorized_client.post(
        "/notion/connect",
        json={"user_id": 1, "code": "code", "redirect_uri": "http://localhost"},
        headers={"Authorization": "Bearer expired_token", "X-CSRF-Token": authorized_client.csrf_token}
    )
    assert response.status_code == 401
    assert "Token expired" in response.json["detail"]
