# app/auth/two_factor/Service.py
import base64
import secrets
from io import BytesIO

import pyotp
import qrcode
from sqlalchemy.orm.session import Session

from app.auth.session_manager.repository import UserRepository
from app.auth.two_factor.repository import TwoFactorRepository
from app.utils.exceptions import AuthError
from app.utils.security import pwd_context


class TwoFactorService:
    """
    All knowledge of the 2FA workflow lives here.

    Responsibilities:
        - Orchestrate setup, verification, login, and management flows.
        - Generate secrets, QR codes, and backup codes.
        - Hash backup codes before persistence.
        - Verify TOTP tokens.

    Not responsible for:
        - Any database queries or mutations (delegated to TwoFactorRepository).
        - User lookup beyond what is needed to obtain an email for the provisioning URI
          (delegated to UserRepository).
    """

    ISSUER = "TemporalIQ"
    BACKUP_CODE_COUNT = 10
    BACKUP_CODE_BYTES = 8

    def __init__(
        self,
        two_factor_repo: TwoFactorRepository,
        user_repo: UserRepository,
    ):
        self.two_factor_repo = two_factor_repo
        self.user_repo = user_repo

    # ------------------------------------------------------------------
    # Public workflow methods
    # ------------------------------------------------------------------

    def setup(self, db: Session, user_id: int) -> dict:
        """
        Begin the 2FA setup flow.

        Generates a TOTP secret, persists it (without enabling 2FA),
        and returns the QR code and manual entry key for the frontend.

        2FA is NOT enabled at this point — the user must call verify_setup()
        with a valid TOTP code to complete setup.

        Raises:
            AuthError — if the user does not exist, or if 2FA is already enabled.

        Returns:
            {
                "qr_code":          str  — data:image/png;base64,... for the QR image
                "manual_entry_key": str  — the raw base32 secret for manual entry
                "issuer":           str  — the issuer name shown in authenticator apps
            }
        """
        user = self.user_repo.get_by_id(db, user_id)
        if not user:
            raise AuthError("User not found")

        if self.two_factor_repo.is_enabled(db, user_id):
            raise AuthError("2FA is already enabled — disable it before starting setup again")

        secret = self._generate_secret()
        self.two_factor_repo.set_secret(db, user_id, secret)

        provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email,
            issuer_name=self.ISSUER,
        )
        qr_code = self._build_qr(provisioning_uri)

        return {
            "qr_code": qr_code,
            "manual_entry_key": secret,
            "issuer": self.ISSUER,
        }

    def verify_setup(self, db: Session, user_id: int, verification_code: str) -> list[str]:
        """
        Complete the 2FA setup flow.

        Verifies that the user can produce a valid TOTP code from the secret
        that was stored during setup(), then enables 2FA and issues backup codes.

        Raises:
            AuthError — if setup was not initiated, 2FA is already enabled,
                        or the verification code is invalid.

        Returns:
            list[str] — plaintext backup codes (shown to the user once, then discarded)
        """
        record = self.two_factor_repo.get_by_user_id(db, user_id)
        if not record or not record.secret:
            raise AuthError("2FA setup not initiated — call setup() first")

        if record.enabled:
            raise AuthError("2FA is already enabled")

        if not self._verify_totp(record.secret, verification_code):
            raise AuthError("Invalid verification code")

        plaintext_codes = self._generate_backup_codes()
        hashed_codes = self._hash_backup_codes(plaintext_codes)

        self.two_factor_repo.enable(db, user_id, hashed_codes)

        return plaintext_codes

    def verify_login(self, db: Session, user_id: int, code: str) -> bool:
        """
        Verify a 2FA code during the login flow.

        Accepts either a TOTP code or a backup code.

        Raises:
            AuthError — if 2FA is not enabled for this user.

        Returns:
            True  — code is valid (TOTP or backup code matched)
            False — code is invalid
        """
        record = self.two_factor_repo.get_by_user_id(db, user_id)
        if not record or not record.enabled:
            raise AuthError("2FA is not enabled for this account")

        if self._verify_totp(record.secret, code):
            return True

        return self.two_factor_repo.consume_backup_code(db, user_id, code)

    def regenerate_backup_codes(self, db: Session, user_id: int) -> list[str]:
        """
        Replace backup codes with a fresh set.

        Raises:
            AuthError — if 2FA is not enabled, or the record has no secret
                        (guards against corrupted rows).

        Returns:
            list[str] — plaintext backup codes (shown to the user once, then discarded)
        """
        record = self.two_factor_repo.get_by_user_id(db, user_id)
        if not record or not record.enabled:
            raise AuthError("2FA is not enabled for this account")
        if not record.secret:
            raise AuthError("2FA record is in an invalid state — secret is missing")

        plaintext_codes = self._generate_backup_codes()
        hashed_codes = self._hash_backup_codes(plaintext_codes)

        self.two_factor_repo.set_backup_codes(db, user_id, hashed_codes)

        return plaintext_codes

    def status(self, db: Session, user_id: int) -> dict:
        """
        Return the current 2FA status for a user.

        Returns:
            {
                "enabled":         bool
                "codes_remaining": int
            }
        """
        record = self.two_factor_repo.get_by_user_id(db, user_id)
        if not record:
            return {"enabled": False, "codes_remaining": 0}

        return {
            "enabled": record.enabled,
            "codes_remaining": self.two_factor_repo.count_backup_codes(db, user_id),
        }

    def disable(self, db: Session, user_id: int) -> None:
        """
        Disable 2FA for a user and clear all 2FA state.

        The repository resets enabled, secret, and backup_codes to their
        null/default values. The row is retained.
        """
        self.two_factor_repo.disable(db, user_id)

    # ------------------------------------------------------------------
    # Private helpers — behaviour, no persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def _generate_backup_codes() -> list[str]:
        return [
            secrets.token_urlsafe(TwoFactorService.BACKUP_CODE_BYTES)
            for _ in range(TwoFactorService.BACKUP_CODE_COUNT)
        ]

    @staticmethod
    def _hash_backup_codes(plaintext_codes: list[str]) -> list[str]:
        return [pwd_context.hash(code) for code in plaintext_codes]

    @staticmethod
    def _verify_totp(secret: str, code: str) -> bool:
        try:
            return pyotp.TOTP(secret).verify(code, valid_window=1)
        except Exception:
            return False

    @staticmethod
    def _build_qr(provisioning_uri: str) -> str:
        """
        Convert a provisioning URI into a base64-encoded PNG data URI.

        Returns:
            str — "data:image/png;base64,..."
        """
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buffer = BytesIO()
        img.save(buffer, format="PNG")

        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()