import os
import pytest

# Paths relative to the project root
MODEL_CACHE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "ai_models_cache_for_testing")
)

# Define model names and their expected subdirectories
huggingface_models = ["KS-Vijay_urgency-model-aura"]
sentence_transformer_models = ["all-MiniLM-L6-v2"]
spacy_models = ["en_core_web_sm"]


def model_path_exists(model_relative_path):
    return os.path.isdir(os.path.join(MODEL_CACHE_ROOT, model_relative_path))


@pytest.mark.parametrize("model_relative_path", huggingface_models)
def test_huggingface_model_exists(model_relative_path):
    assert model_path_exists(model_relative_path), f"Hugging Face model not found: {model_relative_path}"


@pytest.mark.parametrize("model_relative_path", sentence_transformer_models)
def test_sentence_transformer_model_exists(model_relative_path):
    assert model_path_exists(model_relative_path), f"SentenceTransformer model not found: {model_relative_path}"


@pytest.mark.parametrize("model_relative_path", spacy_models)
def test_spacy_model_exists(model_relative_path):
    assert model_path_exists(model_relative_path), f"spaCy model not found: {model_relative_path}"
