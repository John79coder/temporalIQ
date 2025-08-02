from transformers import pipeline

def test_model_exists():
    try:
        clf = pipeline("text-classification", model="KS-Vijay/urgency-model-aura")
        print("✅ Model loaded successfully")
    except Exception as e:
        print("❌ Failed to load model:", e)

def test_model_load_isolated():
    import ssl
    print("ssl.SSLContext:", ssl.SSLContext)
    from transformers import pipeline
    clf = pipeline("text-classification", model="KS-Vijay/urgency-model-aura")
    assert clf is not None