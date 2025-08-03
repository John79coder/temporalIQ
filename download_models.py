import os
import shutil
import subprocess
from transformers import AutoTokenizer, AutoModel
from sentence_transformers import SentenceTransformer
import spacy
from spacy.cli import download as spacy_download

from config import Config

cache_root = os.path.join(Config.PROJECT_ROOT, "ai_models_cache_for_testing")

# Delete existing contents of cache_root if it exists and is not empty
if os.path.exists(cache_root) and os.listdir(cache_root):
    print(f"[PYTHON] Clearing existing cache directory: {cache_root}")
    shutil.rmtree(cache_root)
os.makedirs(cache_root, exist_ok=True)

def download_hf_transformer(name):
    print(f"[PYTHON] Downloading HF transformer model: {name}")
    tokenizer = AutoTokenizer.from_pretrained(name)
    model = AutoModel.from_pretrained(name)
    save_dir = os.path.join(cache_root, name.replace("/", "_"))
    os.makedirs(save_dir, exist_ok=True)
    tokenizer.save_pretrained(save_dir)
    model.save_pretrained(save_dir)
    print(f"[PYTHON] ✅ Saved to {save_dir}")

def download_sentence_transformer(name):
    print(f"[PYTHON] Downloading SentenceTransformer model: {name}")
    model = SentenceTransformer(name)
    save_dir = os.path.join(cache_root, name.replace("/", "_"))
    os.makedirs(save_dir, exist_ok=True)
    model.save(save_dir)
    print(f"[PYTHON] ✅ Saved to {save_dir}")

def download_spacy_model(name):
    print(f"[PYTHON] Downloading spaCy model: {name}")
    spacy_download(name)
    print(f"[PYTHON] Loading spaCy model: {name}")
    nlp = spacy.load(name)
    target_dir = os.path.join(cache_root, name)
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    print(f"[PYTHON] Exporting spaCy model to: {target_dir}")
    nlp.to_disk(target_dir)
    print(f"[PYTHON] ✅ spaCy model flattened and saved to {target_dir}")

if __name__ == "__main__":
    print("[PYTHON] === Downloading HF transformer ===")
    download_hf_transformer("KS-Vijay/urgency-model-aura")

    print("[PYTHON] === Downloading SentenceTransformer ===")
    download_sentence_transformer("all-MiniLM-L6-v2")

    print("[PYTHON] === Downloading and preparing spaCy model ===")
    download_spacy_model("en_core_web_sm")
