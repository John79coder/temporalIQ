import pytest
from app.notion.smart_mapping.sentence_task_splitter.task_splitter import SentenceSplitter

@pytest.fixture
def sentence_splitter():
    return SentenceSplitter()

def test_split_with_spacy_single_clause(sentence_splitter):
    result = sentence_splitter.split_with_spacy("Email the client.")
    assert len(result.segments) == 1
    assert "Email" in result.segments[0]

def test_split_with_spacy_multiple_verbs(sentence_splitter):
    result = sentence_splitter.split_with_spacy("Review the document and submit the report.")
    assert len(result.segments) >= 2
    assert any("submit" in seg for seg in result.segments)

def test_split_with_t5_long_sentence(sentence_splitter):
    result = sentence_splitter.split_with_t5("Call Bob, then check the finances, and finally write the report.")
    assert len(result.segments) >= 2
    assert all(len(seg) > 10 for seg in result.segments)

def test_ensemble_split_combines_spacy_and_t5(sentence_splitter):
    result = sentence_splitter.ensemble_split("Draft the proposal, review the budget, and schedule a meeting.")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert any("proposal" in seg for seg in result)

def test_split_into_tasks_final_output(sentence_splitter):
    sentence = "Clean the whiteboard, organize the bookshelf, and email Sarah."
    tasks = sentence_splitter.split_into_tasks(sentence)
    assert len(tasks) >= 2
    assert all(len(task.split()) >= 2 for task in tasks)
