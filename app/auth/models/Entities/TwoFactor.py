from app.extensions import db
from app.auth.models.entities import TimestampMixin


class UserTwoFactor(db.Model, TimestampMixin):
    __tablename__ = "user_two_factor"

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )

    secret = db.Column(
        db.String,
        nullable=True,
    )

    enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
    )

    backup_codes = db.Column(
        db.ARRAY(db.String),
        nullable=True,
    )

    user = db.relationship(
        "User",
        backref=db.backref(
            "two_factor",
            uselist=False,
            cascade="all, delete-orphan",
        ),
    )

    @staticmethod
    def from_dict(data: dict) -> "UserTwoFactor":
        entity = UserTwoFactor()
        entity.user_id = data.get("user_id")
        entity.secret = data.get("secret")
        entity.enabled = data.get("enabled", False)
        entity.backup_codes = data.get("backup_codes")
        entity.created_at = data.get("created_at")
        entity.updated_at = data.get("updated_at")
        return entity