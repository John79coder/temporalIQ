# app/auth/models/entities.py
from app.extensions import db
from app.utils.time_zone import TimeZone

class TimestampMixin:
    created_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now)
    updated_at = db.Column(db.DateTime(timezone=True), default=TimeZone.utc_now, onupdate=TimeZone.utc_now)


class User(db.Model, TimestampMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True, index=True)
    email = db.Column(db.String, unique=True, index=True, nullable=False)
    hashed_password = db.Column(db.String, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    failed_logins = db.Column(db.Integer, default=0)  # Added for lockout

    __table_args__ = (
        db.CheckConstraint(
            r"email ~ '^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'",
            name="valid_email"
        ),
    )

    @staticmethod
    def from_dict(data: dict) -> 'User':
        user = User()
        user.id = data.get("id")
        user.email = data.get("email")
        user.hashed_password = data.get("hashed_password")
        user.is_verified = data.get("is_verified", False)
        user.failed_logins = data.get("failed_logins", 0)
        user.created_at = data.get("created_at")
        user.updated_at = data.get("updated_at")
        return user

class VerificationToken(db.Model):
    __tablename__ = "verification_tokens"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    token = db.Column(db.String, nullable=False, unique=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)