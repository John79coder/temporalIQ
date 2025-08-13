# tests/icloud/test_repositories.py
from app.icloud.models.entities import iCloudConnection
from app.icloud.repositories.repository import ICloudRepository
from app.utils.encryption import Encryptor


def test_save_icloud_connection(db_session, test_user):
    user, _ = test_user

    icloud_repository = ICloudRepository()

    encryptor = Encryptor()
    encrypted = encryptor.encrypt("test-password")

    icloud_connection = iCloudConnection(user_id=user.id, encrypted_app_password=encrypted)
    icloud_repository.save_icloud_connection(db_session, icloud_connection)

    retrieved = db_session.query(iCloudConnection).filter_by(user_id=user.id).first()

    assert retrieved.encrypted_app_password == encrypted
    assert retrieved.is_active is True


def test_update_icloud_connection(db_session, test_user):
    user, _ = test_user

    icloud_repository = ICloudRepository()

    encryptor = Encryptor()

    old_encrypted = encryptor.encrypt("old-password")

    icloud_connection = iCloudConnection(user_id=user.id, encrypted_app_password=old_encrypted)

    db_session.add(icloud_connection)
    db_session.commit()

    old_updated_at = icloud_connection.updated_at

    new_encrypted = encryptor.encrypt("new-password")

    updated = icloud_repository.update_icloud_connection(db_session, user.id, new_encrypted)

    assert updated.encrypted_app_password == new_encrypted
    assert updated.updated_at > old_updated_at
