from transformers import pipeline
clf = pipeline("text-classification", model="KS-Vijay/urgency-model-aura")
print("✅ Model loaded")