# tests/icloud/test_models.py
from app.icloud.models.entities import iCloudConnection, CalendarSelection
from app.icloud.repositories.repository import ICloudRepository
from app.utils.encryption import Encryptor


def test_icloud_connection_creation(db_session, test_user):
    user, _ = test_user

    encryptor = Encryptor()
    encrypted_password = encryptor.encrypt("test-password")

    conn = iCloudConnection(
        user_id=user.id,
        encrypted_app_password=encrypted_password
    )

    db_session.add(conn)
    db_session.commit()

    assert conn.id is not None
    assert conn.encrypted_app_password == encrypted_password
    assert conn.created_at is not None
    assert conn.is_active is True


def test_calendar_selection_default(db_session, test_user):
    user, _ = test_user

    repo = ICloudRepository()

    calendar_selection_01 = CalendarSelection(
        user_id=user.id,
        calendar_id="cal1",
        display_name="Calendar1",
        is_default=True
    )

    repo.save_calendar_selection(db_session, calendar_selection_01)

    calendar_selection_02 = CalendarSelection(
        user_id=user.id,
        calendar_id="cal2",
        display_name="Calendar2",
        is_default=True
    )

    repo.save_calendar_selection(db_session, calendar_selection_02)

    updated_sel1 = db_session.query(CalendarSelection).filter_by(calendar_id="cal1").first()
    updated_sel2 = db_session.query(CalendarSelection).filter_by(calendar_id="cal2").first()

    assert updated_sel1.is_default is False
    assert updated_sel2.is_default is True
