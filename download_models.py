import os
from pathlib import Path

import spacy
from sentence_transformers import SentenceTransformer
from spacy.cli import download as spacy_download
from transformers import (
    AutoModel,
    AutoTokenizer,
    T5ForConditionalGeneration,
    T5Tokenizer,
)

# Project root is simply the folder containing this script.
PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_ROOT = PROJECT_ROOT / "ai_models_cache"

CACHE_ROOT.mkdir(parents=True, exist_ok=True)


def model_exists(model_name: str) -> bool:
    """Returns True if the model has already been downloaded."""
    return (CACHE_ROOT / model_name.replace("/", "_")).exists()


def spacy_model_exists(model_name: str) -> bool:
    """Returns True if the spaCy model has already been exported."""
    return (CACHE_ROOT / model_name).exists()


def download_hf_transformer(name: str):
    if model_exists(name):
        print(f"[PYTHON] ✓ Already exists: {name}")
        return

    print(f"[PYTHON] Downloading HF transformer model: {name}")

    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name)

    save_dir = CACHE_ROOT / name.replace("/", "_")
    save_dir.mkdir(parents=True, exist_ok=True)

    tokenizer.save_pretrained(save_dir)
    model.save_pretrained(save_dir)

    print(f"[PYTHON] ✅ Saved to {save_dir}")


def download_t5_splitter_model(name: str):
    if model_exists(name):
        print(f"[PYTHON] ✓ Already exists: {name}")
        return

    print(f"[PYTHON] Downloading T5 Split-and-Rephrase model: {name}")

    tokenizer = T5Tokenizer.from_pretrained(name)
    model = T5ForConditionalGeneration.from_pretrained(name)

    save_dir = CACHE_ROOT / name.replace("/", "_")
    save_dir.mkdir(parents=True, exist_ok=True)

    tokenizer.save_pretrained(save_dir)
    model.save_pretrained(save_dir)

    print(f"[PYTHON] ✅ Saved to {save_dir}")


def download_sentence_transformer(name: str):
    if model_exists(name):
        print(f"[PYTHON] ✓ Already exists: {name}")
        return

    print(f"[PYTHON] Downloading SentenceTransformer model: {name}")

    model = SentenceTransformer(name)

    save_dir = CACHE_ROOT / name.replace("/", "_")
    save_dir.mkdir(parents=True, exist_ok=True)

    model.save(save_dir)

    print(f"[PYTHON] ✅ Saved to {save_dir}")


def download_spacy_model(name: str):
    if spacy_model_exists(name):
        print(f"[PYTHON] ✓ Already exists: {name}")
        return

    print(f"[PYTHON] Downloading spaCy model: {name}")

    spacy_download(name)

    print(f"[PYTHON] Loading spaCy model: {name}")

    nlp = spacy.load(name)

    target_dir = CACHE_ROOT / name

    nlp.to_disk(target_dir)

    print(f"[PYTHON] ✅ Saved to {target_dir}")


if __name__ == "__main__":
    print("[PYTHON] Ensuring AI models are available...")

    download_hf_transformer("KS-Vijay/urgency-model-aura")
    download_t5_splitter_model("unikei/t5-base-split-and-rephrase")
    download_sentence_transformer("all-MiniLM-L6-v2")
    download_spacy_model("en_core_web_sm")
    download_spacy_model("en_core_web_md")

    print("[PYTHON] ✅ All required models are available.")