import os
import re
from typing import List

import spacy
from flask import current_app
from transformers import T5Tokenizer, T5ForConditionalGeneration


class ProcessorResult:
    def __init__(self, segments: List[str], confidence: float = 1.0):
        self.segments = segments
        self.confidence = confidence


class SentenceSplitter:
    def __init__(self):
        self.model_dir = current_app.config.get("MODEL_DIR", ".")
        self.model_path = os.path.join(self.model_dir, "en_core_web_md")
        self.nlp = None

        T5_CHECKPOINT = "unikei_t5-base-split-and-rephrase"
        checkpoint_path = os.path.join(self.model_dir, T5_CHECKPOINT)
        self.tokenizer = T5Tokenizer.from_pretrained(checkpoint_path)
        self.t5_model = T5ForConditionalGeneration.from_pretrained(checkpoint_path)

    def split_with_spacy(self, sentence: str) -> ProcessorResult:

        if not self.nlp:
            self.nlp = spacy.load(self.model_path)

        doc = self.nlp(sentence)
        verbs = [tok for tok in doc if tok.pos_ == "VERB" and tok.dep_ in ("ROOT", "conj")]
        segments = []

        if verbs:
            for v in verbs:
                subtree = " ".join([t.text for t in v.subtree])
                segments.append(subtree)
        if not segments:
            segments = [sentence]
        return ProcessorResult(segments, confidence=0.8)

    def split_with_t5(self, sentence: str, max_output_segments=5) -> ProcessorResult:
        input_text = f"split: {sentence}"
        inputs = self.tokenizer(input_text, return_tensors="pt", truncation=True, max_length=256)
        outputs = self.t5_model.generate(inputs.input_ids, num_beams=4, max_length=256, early_stopping=True)
        decoded = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        # assume output sentences are separated by newline or ". "
        raw_segments = re.split(r'\.\s+|\n', decoded)
        segments = [seg.strip() for seg in raw_segments if seg.strip()]
        return ProcessorResult(segments, confidence=0.9)

    def ensemble_split(self, sentence: str) -> List[str]:
        # Run both processors
        spa = self.split_with_spacy(sentence)
        t5 = self.split_with_t5(sentence)
        # Merge unique results
        seg_set = {}
        for pr in (t5, spa):
            for seg in pr.segments:
                seg_norm = seg.strip().lower()
                seg_set[seg_norm] = seg_set.get(seg_norm, 0) + pr.confidence
        # Sort by cumulative confidence
        sorted_segs = sorted(seg_set.items(), key=lambda kv: -kv[1])
        selected = [seg for seg, _ in sorted_segs]
        # Filter: only include splits if more than one distinct segment
        if len(selected) <= 1:
            return [sentence.strip()]
        return selected

    def split_into_tasks(self, sentence: str) -> List[str]:
        segments = self.ensemble_split(sentence)
        # Further verify segments are substantive
        final = [seg for seg in segments if len(seg.split()) >= 2]
        return final or [sentence.strip()]

    # Example usage:
    if __name__ == "__main__":
        examples = [
            "Email John about the budget, then schedule the call for next Monday.",
            "Submit report and update CRM records."
        ]
        for ex in examples:
            print("Input:", ex)
            print("Tasks:", split_into_tasks(ex))
