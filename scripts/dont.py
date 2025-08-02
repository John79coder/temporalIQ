import os
import shutil
from sentence_transformers import SentenceTransformer
import torch

# Model and cache settings
MODEL_NAME = "all-MiniLM-L6-v2"
CACHE_DIR = os.path.abspath("models_cache")

def clear_model_cache():
    paths_to_try = [
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub", "models--sentence-transformers--" + MODEL_NAME),
        os.path.join(CACHE_DIR, MODEL_NAME)
    ]
    for path in paths_to_try:
        if os.path.exists(path):
            try:
                print(f"🧹 Removing: {path}")
                shutil.rmtree(path)
            except Exception as e:
                print(f"⚠️ Could not delete {path}: {e}")

def load_model():
    try:
        print(f"🚀 Loading model '{MODEL_NAME}' using cache dir '{CACHE_DIR}'...")
        model = SentenceTransformer(MODEL_NAME, cache_folder=CACHE_DIR)
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model.to(device)
        print(f"✅ Model loaded to device: {device}")
        return model
    except Exception as e:
        print("❌ Failed to load model:")
        print(e)
        return None

if __name__ == "__main__":
    clear_model_cache()
    model = load_model()

    if model:
        sentence = "Finish my AI scheduling system"
        embedding = model.encode(sentence)
        print(f"🧠 Embedding shape: {embedding.shape}")
