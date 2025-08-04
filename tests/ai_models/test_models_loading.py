# tests/ai_models/test_models_loading.py
import os

import numpy as np
import pytest

from transformers import AutoTokenizer, AutoModel, AutoConfig  # CHANGED: Added AutoConfig for attn_implementation
from sentence_transformers import SentenceTransformer
from sentence_transformers.models import Transformer, Pooling  # CHANGED: Added for modular loading
import spacy

# Absolute path to the root-relative 'ai_models_cache' directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "..", "ai_models_cache_for_testing"))

@pytest.mark.parametrize("model_name, rel_path", [
    ("HuggingFace urgency classifier", "KS-Vijay_urgency-model-aura"),
    ("SentenceTransformer MiniLM", "all-MiniLM-L6-v2"),
    ("spaCy English small", "en_core_web_md"),
])
def test_model_directory_present(model_name, rel_path):
    path = os.path.join(CACHE_DIR, rel_path)
    assert os.path.isdir(path), f"{model_name} directory missing at {path}"

def test_load_hf_urgency_model():
    path = os.path.join(CACHE_DIR, "KS-Vijay_urgency-model-aura")
    tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
    config = AutoConfig.from_pretrained(path, attn_implementation="eager")  # CHANGED: Added config with eager
    model = AutoModel.from_pretrained(path, config=config, local_files_only=True)  # CHANGED: Passed config
    tokens = tok("Test", return_tensors="pt")
    outputs = model(**tokens)
    assert outputs.last_hidden_state.shape[0] == 1

def test_load_sentence_transformer():
    path = os.path.join(CACHE_DIR, "all-MiniLM-L6-v2")
    # CHANGED: Modular loading to inject attn_implementation
    transformer = Transformer(model_name_or_path=path, model_args={"attn_implementation": "eager"})
    pooling = Pooling(transformer.get_word_embedding_dimension(), pooling_mode='mean')
    model = SentenceTransformer(modules=[transformer, pooling])
    embeddings = model.encode(["Hello world"])
    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape[0] == 1

def test_load_spacy_model():
    path = os.path.join(CACHE_DIR, "en_core_web_sm")
    nlp = spacy.load(path)
    doc = nlp("This is a test sentence.")
    assert len(doc) > 0