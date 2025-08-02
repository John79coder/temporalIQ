# tests/unit/test_unit.py
from datetime import timedelta

from app.notion.smart_mapping.field_detectors.keyword_matcher import KeywordMatcher
from app.notion.smart_mapping.field_detectors.field_type_heuristics import FieldTypeHeuristics
from app.utils.encryption import Encryptor
from app.scheduling.models.schemas import TimeBlockIn
import pytest

from app.utils.time_zone import TimeZone


def test_keyword_matcher_basic_match():
    detector = KeywordMatcher()
    fields = [{"name": "Due Date", "type": "date"}]
    matches = detector.detect(fields)
    assert any(m.matched_concept == "due_date" and m.confidence == 0.7 for m in matches)

def test_field_type_heuristics_date_detection(features_service, db_session, test_user):

    heuristics_detector = FieldTypeHeuristics(features_service)

    fields = [{"name": "Due Date", "type": "date"}, {"name": "title", "type": "text"}]

    matches = heuristics_detector.detect(fields, None, db_session, test_user[1])

    assert any(match.matched_concept == "due_date" for match in matches)
    assert any(match.matched_concept == "title" for match in matches)

def test_encrypt_decrypt_roundtrip():
    enc = Encryptor()
    data = "sensitive"
    encrypted_data = enc.encrypt(data)
    decrypted_data = enc.decrypt(encrypted_data)
    assert data == decrypted_data

def test_time_block_validator_constraints():
    with pytest.raises(ValueError):
        TimeBlockIn(start=TimeZone.utc_now(), end=TimeZone.utc_now() - timedelta(hours=1))