# app/utils/security.py
from typing import Any
import json

from  app.utils.encryption import Encryptor
from app.utils.exceptions import ServiceUnavailableError, wrap_external_error

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class SecurityService:
    def __init__(self):
        try:
            self.encryptor = Encryptor()
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to initialize encryptor")

    def encrypt_data(self, data: Any) -> str:
        try:
            return self.encryptor.encrypt(json.dumps(data))
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Encryption failed")

    def decrypt_data(self, encrypted_data: str) -> Any:
        try:
            return json.loads(self.encryptor.decrypt(encrypted_data))
        except Exception as e:
            raise wrap_external_error(e, ServiceUnavailableError, "Decryption failed")