import os
import shutil
from flask import current_app
from sentence_transformers import SentenceTransformer
from transformers import pipeline, T5Tokenizer, T5ForConditionalGeneration
import joblib
import torch

# Model names
MODEL_NAMES = [
    "KS-Vijay/urgency-model-aura",
    "unikei/t5-base-split-and-rephrase",
    "all-MiniLM-L6-v2"
]
PKL_FILES = [
    "ridge_duration_model.pkl",
    "task_prioritizer_model.pkl",
    "learned_model.pkl"
]

# Get MODEL_DIR from Flask config
def get_model_dir():
    return os.path.abspath(current_app.config.get("MODEL_DIR", "ai_models"))

# Set HF_HOME for Hugging Face models
os.environ["HF_HOME"] = get_model_dir()

def clear_model_cache():
    model_dir = get_model_dir()
    paths_to_try = [
        os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub", f"models--{model.replace('/', '--')}") for model in MODEL_NAMES
    ] + [os.path.join(model_dir, model) for model in MODEL_NAMES]
    for path in paths_to_try:
        if os.path.exists(path):
            try:
                print(f"🧹 Removing: {path}")
                shutil.rmtree(path)
            except Exception as e:
                print(f"⚠️ Could not delete {path}: {e}")
    # Clear .pkl files
    for pkl_file in PKL_FILES:
        pkl_path = os.path.join(model_dir, pkl_file)
        if os.path.exists(pkl_path):
            try:
                print(f"🧹 Removing: {pkl_path}")
                os.remove(pkl_path)
            except Exception as e:
                print(f"⚠️ Could not delete {pkl_path}: {e}")

def load_model():
    try:
        model_dir = get_model_dir()
        print(f"🚀 Loading models using model dir '{model_dir}'...")

        # Load Hugging Face models
        urgency_classifier = pipeline(
            "text-classification",
            model="KS-Vijay/urgency-model-aura",
            cache_dir=model_dir,
            local_files_only=True
        )
        t5_tokenizer = T5Tokenizer.from_pretrained(
            "unikei/t5-base-split-and-rephrase",
            cache_dir=model_dir,
            local_files_only=True
        )
        t5_model = T5ForConditionalGeneration.from_pretrained(
            "unikei/t5-base-split-and-rephrase",
            cache_dir=model_dir,
            local_files_only=True
        )
        sentence_transformer = SentenceTransformer(
            "all-MiniLM-L6-v2",
            cache_folder=model_dir,
            local_files_only=True
        )

        # Move Hugging Face models to device
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        t5_model.to(device)
        sentence_transformer.to(device)
        print(f"✅ Hugging Face models loaded to device: {device}")

        # Load .pkl files
        ridge_duration_model = joblib.load(os.path.join(model_dir, "ridge_duration_model.pkl"))
        task_prioritizer_model = joblib.load(os.path.join(model_dir, "task_prioritizer_model.pkl"))
        learned_model = joblib.load(os.path.join(model_dir, "learned_model.pkl"))
        print(f"✅ .pkl models loaded from: {model_dir}")

        return {
            "urgency_classifier": urgency_classifier,
            "t5_tokenizer": t5_tokenizer,
            "t5_model": t5_model,
            "sentence_transformer": sentence_transformer,
            "ridge_duration_model": ridge_duration_model,
            "task_prioritizer_model": task_prioritizer_model,
            "learned_model": learned_model
        }
    except Exception as e:
        print("❌ Failed to load models:")
        print(e)
        return None

if __name__ == "__main__":
    from app import create_app
    app = create_app()
    with app.app_context():

        models = load_model()
        if models:
            sentence = "Finish my AI scheduling system"
            embedding = models["sentence_transformer"].encode(sentence)
            print(f"🧠 Embedding shape: {embedding.shape}")