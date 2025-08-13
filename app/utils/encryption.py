# app/utils/encryption.py
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.utils.exceptions import ServiceUnavailableError, wrap_external_error
from config import Config, TestingConfig


class Encryptor:
    def __init__(self):
        key = os.getenv("ENCRYPTION_KEY")
        if not key:
            # Use TestingConfig.ENCRYPTION_KEY in test environment, Config.ENCRYPTION_KEY otherwise
            config = TestingConfig if os.getenv("FLASK_ENV") == "test" else Config
            key = config.ENCRYPTION_KEY
            if not key:
                raise ServiceUnavailableError("ENCRYPTION_KEY not set in environment or configuration")
        self.cipher = Fernet(key.encode())

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(InvalidToken))
    def encrypt(self, data: str) -> str:
        try:
            encrypted = self.cipher.encrypt(data.encode()).decode()
            logging.info("Successfully encrypted data")
            return encrypted
        except (InvalidToken, ValueError, TypeError) as e:
            logging.error(f"Encryption failed: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Encryption failed")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(InvalidToken))
    def decrypt(self, encrypted_data: str) -> str:
        try:
            decrypted = self.cipher.decrypt(encrypted_data.encode()).decode()
            logging.info("Successfully decrypted data")
            return decrypted
        except (InvalidToken, ValueError, TypeError) as e:
            logging.error(f"Decryption failed: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Decryption failed")
