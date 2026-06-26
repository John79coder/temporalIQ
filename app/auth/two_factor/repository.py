# app/auth/two_factor/repository.py
from typing import Optional

from sqlalchemy.orm import Session

from app.auth.models.Entities.TwoFactor import UserTwoFactor
from app.repositories.base import AbstractRepository
from app.utils.exceptions import DatabaseError, wrap_external_error
from app.utils.security import pwd_context
from app.utils.time_zone import TimeZone


class TwoFactorRepository(AbstractRepository):
    """
    Persist and retrieve 2FA state.

    Responsibilities:
        - Read and write the user_two_factor table.

    Not responsible for:
        - Generating secrets, QR codes, or backup codes.
        - Verifying TOTP tokens.
        - Any business rules about when 2FA may be enabled or disabled.
    """

    # ------------------------------------------------------------------
    # Private helper
    # ------------------------------------------------------------------

    @staticmethod
    def _get(db: Session, user_id: int) -> Optional[UserTwoFactor]:
        """Raw fetch — no exception wrapping. Used internally only."""
        return (
            db.query(UserTwoFactor)
            .filter(UserTwoFactor.user_id == user_id)
            .first()
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_user_id(db: Session, user_id: int) -> Optional[UserTwoFactor]:
        """Return the 2FA row for a user, or None if it does not exist."""
        try:
            return TwoFactorRepository._get(db, user_id)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to retrieve 2FA record")

    @staticmethod
    def exists(db: Session, user_id: int) -> bool:
        """Return True if a 2FA row exists for the user."""
        try:
            return (
                db.query(UserTwoFactor.user_id)
                .filter(UserTwoFactor.user_id == user_id)
                .first()
            ) is not None
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to check 2FA record existence")

    @staticmethod
    def is_enabled(db: Session, user_id: int) -> bool:
        """Return True if 2FA is both set up and enabled for the user."""
        try:
            record = UserTwoFactorRepository._get(db, user_id)
            return record is not None and record.enabled
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to check 2FA enabled status")

    @staticmethod
    def count_backup_codes(db: Session, user_id: int) -> int:
        """Return the number of remaining backup codes for the user."""
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None or not record.backup_codes:
                return 0
            return len(record.backup_codes)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to count backup codes")

    @staticmethod
    def get_or_create(db: Session, user_id: int) -> UserTwoFactor:
        """
        Return the existing row, or insert a blank one and return it.

        Removes the need for callers to duplicate the
        'does it exist? create it' pattern.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record:
                return record

            with db.begin(nested=True):
                record = UserTwoFactor(user_id=user_id, enabled=False)
                db.add(record)
                db.flush()
                db.refresh(record)
            return record
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to get or create 2FA record")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    @staticmethod
    def set_secret(db: Session, user_id: int, secret: str) -> UserTwoFactor:
        """
        Persist a newly generated TOTP secret.

        Creates the row if it does not exist.
        Replaces any existing secret.
        Does NOT enable 2FA — that is the job of enable().
        """
        try:
            record = TwoFactorRepository.get_or_create(db, user_id)
            with db.begin(nested=True):
                record.secret = secret
                record.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(record)
            return record
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to persist 2FA secret")

    @staticmethod
    def clear_secret(db: Session, user_id: int) -> Optional[UserTwoFactor]:
        """
        Clear the TOTP secret without disabling or touching backup codes.

        Used when a setup flow is abandoned — the row stays, the
        half-initialised secret is removed, enabled remains False.
        No-op if the row does not exist.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None:
                return None
            with db.begin(nested=True):
                record.secret = None
                record.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(record)
            return record
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to clear 2FA secret")

    @staticmethod
    def enable(db: Session, user_id: int, hashed_backup_codes: list[str]) -> UserTwoFactor:
        """
        Mark 2FA as enabled and store the hashed backup codes.

        Raises DatabaseError if:
            - No row exists (set_secret must be called first).
            - The row has no secret (cannot enable without a secret).

        The caller (TwoFactorService) is responsible for:
            - Generating plaintext codes.
            - Hashing them before passing them here.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None:
                raise DatabaseError(f"No 2FA record found for user {user_id}")
            if not record.secret:
                raise DatabaseError(f"Cannot enable 2FA for user {user_id}: no secret is set")

            with db.begin(nested=True):
                record.enabled = True
                record.backup_codes = hashed_backup_codes
                record.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(record)
            return record
        except DatabaseError:
            raise
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to enable 2FA")

    @staticmethod
    def disable(db: Session, user_id: int) -> Optional[UserTwoFactor]:
        """
        Reset the 2FA state for a user.

        Sets enabled = False, secret = NULL, backup_codes = NULL.
        Leaves the row in place so get_or_create() remains idempotent.
        No-op (returns None) if the row does not exist — disabling
        something that was never set up is not an error.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None:
                return None
            with db.begin(nested=True):
                record.enabled = False
                record.secret = None
                record.backup_codes = None
                record.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(record)
            return record
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to disable 2FA")

    @staticmethod
    def set_backup_codes(db: Session, user_id: int, hashed_backup_codes: list[str]) -> UserTwoFactor:
        """
        Replace the stored backup codes.

        Used by TwoFactorService.regenerate_backup_codes().
        The caller is responsible for hashing the codes before passing them here.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None:
                raise DatabaseError(f"No 2FA record found for user {user_id}")
            with db.begin(nested=True):
                record.backup_codes = hashed_backup_codes
                record.updated_at = TimeZone.utc_now()
                db.flush()
                db.refresh(record)
            return record
        except DatabaseError:
            raise
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to update backup codes")

    @staticmethod
    def consume_backup_code(db: Session, user_id: int, entered_code: str) -> bool:
        """
        Attempt to consume a backup code.

        Retrieves hashed codes, compares against entered_code,
        removes the matching hash, and persists the remainder.

        Returns True if a code matched and was consumed, False otherwise.

        The repository owns the persistence concern here. The service
        does not need to handle the list mutation.
        """
        try:
            record = TwoFactorRepository._get(db, user_id)
            if record is None or not record.backup_codes:
                return False

            for i, hashed in enumerate(record.backup_codes):
                if pwd_context.verify(entered_code, hashed):
                    remaining = list(record.backup_codes)
                    remaining.pop(i)
                    with db.begin(nested=True):
                        record.backup_codes = remaining
                        record.updated_at = TimeZone.utc_now()
                        db.flush()
                        db.refresh(record)
                    return True

            return False
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to consume backup code")

    @staticmethod
    def delete(db: Session, user_id: int) -> None:
        """
        Delete the 2FA row entirely.

        Prefer disable() for normal account management.
        Use delete() only when the user account itself is being removed,
        or when a full hard-reset is explicitly required.
        No-op if the row does not exist.
        """
        try:
            with db.begin(nested=True):
                db.query(UserTwoFactor).filter(UserTwoFactor.user_id == user_id).delete()
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to delete 2FA record")