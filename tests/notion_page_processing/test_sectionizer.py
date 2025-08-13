import pytest

from app.notion.smart_mapping.sectionizer import Sectionizer, BlockSection


@pytest.fixture
def sectionizer():
    return Sectionizer()


def test_segment_with_heading_splits(sectionizer):
    blocks = [
        {"type": "heading_1", "text": [{"plain_text": "First Task"}]},
        {"type": "paragraph", "text": [{"plain_text": "This is the first task."}]},
        {"type": "heading_2", "text": [{"plain_text": "Second Task"}]},
        {"type": "to_do", "text": [{"plain_text": "This is the second task."}]}
    ]
    sections = sectionizer.segment(blocks)
    assert isinstance(sections, list)
    assert all(isinstance(s, BlockSection) for s in sections)
    assert len(sections) == 3
    assert any("First Task" in b.get("text", [{}])[0].get("plain_text", "") for b in sections[0].blocks)
