# app/auth/session_manager/service.py
import logging
import pickle

from passlib.context import CryptContext
from sqlalchemy.orm.session import Session

from app.auth.session_manager.repository import UserRepository
import jwt
from config import Config
from app.utils.caching import ICacheService
from app.utils.time_zone import TimeZone
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import requests
from typing import Optional
from app.utils.exceptions import AuthError, DatabaseError, wrap_external_error
from app.auth.models.entities import User


from app.features.services.service import FeaturesService

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthenticationService:
    def __init__(self, user_repo: UserRepository, caching_service: ICacheService, features_service: FeaturesService):
        self.user_repo = user_repo
        self.caching_service = caching_service
        self.features_service = features_service
        self.apple_jwks_url = "https://appleid.apple.com/auth/keys"
        self.failed_login_threshold = 5  # Configurable if needed

    def update_verified(self, db: Session, user_id: int) -> Optional[User]:

        try:
            user = self.user_repo.update_verified(db, user_id)
            if not user:
                raise AuthError("User not found")

            # Invalidate cache after successful update
            self.caching_service.delete(f"auth:user:email:{user.email}")

            return user
        except AuthError as e:
            raise
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to update user verification status")


    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        try:
            return pwd_context.verify(plain, hashed)
        except (ValueError, TypeError) as e:
            logging.warning(f"Password verification failed due to invalid input: {str(e)}")
            return False
        except Exception as e:
            raise wrap_external_error(e, AuthError, "Password verification failed")

    def create_user(self, db, email: str, password: str) -> User:
        # Explicit duplicate check
        if self.user_repo.get_by_email(db, email):
            raise AuthError("Email already exists")
        hashed = self.hash_password(password)
        try:
            user = self.user_repo.create(db, email, hashed)
        except Exception as e:
            raise wrap_external_error(e, DatabaseError, "Failed to create user")
        self.features_service.create_default_settings(db, user.id)
        self.caching_service.delete(f"auth:user:email:{email}")
        return user

    def authenticate_user(self, db, email: str, password: str):
        cache_key = f"auth:user:email:{email}"
        user = None
        try:
            cached_user = self.caching_service.get(cache_key)
            if cached_user:
                user = User.from_dict(cached_user)
        except (pickle.PickleError, TypeError) as e:
            logging.warning(f"Cache retrieval failed for key {cache_key}: {str(e)}")

        if not user:
            try:
                user = self.user_repo.get_by_email(db, email)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")
            if user:
                self.caching_service.set(
                    cache_key,
                    user.__dict__,
                    timeout=300
                )

        if user:
            if user.failed_logins >= self.failed_login_threshold:
                self.log_anomaly("login_failed", {"email": email})
                raise AuthError("Account locked due to too many failed attempts")
            if self.verify_password(password, user.hashed_password):
                # Reset failed logins on success
                self.user_repo.update_failed_logins(db, user.id, 0)
                return user
            else:
                # Increment failed logins on failure
                new_count = user.failed_logins + 1
                self.user_repo.update_failed_logins(db, user.id, new_count)
                self.log_anomaly("login_failed", {"email": email})
                return None
        self.log_anomaly("login_failed", {"email": email})
        return None

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def _fetch_apple_jwks(self):
        try:
            with requests.Session() as session:
                return session.get(self.apple_jwks_url).json()
        except requests.RequestException as e:
            logging.error(f"Failed to fetch Apple JWKS: {str(e)}")
            raise wrap_external_error(e, AuthError, "Failed to fetch Apple JWKS")

    def authenticate_apple_user(self, db, id_token: str, jwks: dict = None):
        try:
            if jwks is None:
                jwks = self._fetch_apple_jwks()
            header = jwt.get_unverified_header(id_token)
            key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
            decoded = jwt.decode(
                id_token,
                key,
                algorithms=["RS256"],
                issuer="https://appleid.apple.com",
                audience=Config.APPLE_CLIENT_ID
            )
            email = decoded["email"]
            try:
                user = self.user_repo.get_by_email(db, email)
            except Exception as e:
                raise wrap_external_error(e, DatabaseError, "Failed to retrieve user")
            if not user:
                try:
                    user = self.user_repo.create(db, email, "")
                    user.is_verified = True
                    user.updated_at = TimeZone.utc_now()
                    db.commit()
                    self.features_service.create_default_settings(db, user.id)
                    self.caching_service.delete(f"auth:user:email:{email}")
                except Exception as e:
                    raise wrap_external_error(e, DatabaseError, "Failed to create Apple user")
            return user
        except (jwt.InvalidTokenError, ValueError, TypeError) as e:
            self.log_anomaly("apple_auth_failed", {"error": str(e)})
            raise wrap_external_error(e, AuthError, "Apple JWT verification failed")


    @staticmethod
    def log_anomaly(event_type: str, details: dict):
        extra = {"event_type": event_type, "details": details, "timestamp": TimeZone.utc_now().isoformat()}
        logging.error("ANOMALY", extra=extra)