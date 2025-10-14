import os
import re
import time
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
        t0 = time.perf_counter()
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
        pr = ProcessorResult(segments, confidence=0.8)

        try:
            from flask import current_app
            logger = current_app.extensions['app_context'].get_service('app_logger')
            logger.debug(
                "SPLITTER.spacy.done",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                segments_count=len(pr.segments),
                sample=pr.segments[:2]
            )
        except Exception:
            pass
        return pr

    def split_with_t5(self, sentence: str, max_output_segments=5) -> ProcessorResult:
        t0 = time.perf_counter()
        input_text = f"split: {sentence}"
        inputs = self.tokenizer(input_text, return_tensors="pt", truncation=True, max_length=256)
        outputs = self.t5_model.generate(inputs.input_ids, num_beams=4, max_length=256, early_stopping=True)
        decoded = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        raw_segments = re.split(r'\.\s+|\n', decoded)
        segments = [seg.strip() for seg in raw_segments if seg.strip()]
        pr = ProcessorResult(segments, confidence=0.9)

        try:
            from flask import current_app
            logger = current_app.extensions['app_context'].get_service('app_logger')
            logger.debug(
                "SPLITTER.t5.done",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                segments_count=len(pr.segments),
                sample=pr.segments[:2]
            )
        except Exception:
            pass
        return pr

    def ensemble_split(self, sentence: str) -> List[str]:
        t0 = time.perf_counter()
        spa = self.split_with_spacy(sentence)
        t5 = self.split_with_t5(sentence)

        seg_set = {}
        for pr in (t5, spa):
            for seg in pr.segments:
                seg_norm = seg.strip().lower()
                seg_set[seg_norm] = seg_set.get(seg_norm, 0) + pr.confidence

        sorted_segs = sorted(seg_set.items(), key=lambda kv: -kv[1])
        selected = [seg for seg, _ in sorted_segs]
        final = [sentence.strip()] if len(selected) <= 1 else selected

        try:
            from flask import current_app
            logger = current_app.extensions['app_context'].get_service('app_logger')
            logger.debug(
                "SPLITTER.ensemble.done",
                duration_ms=int((time.perf_counter() - t0) * 1000),
                input_len=len(sentence or ""),
                candidates=len(selected),
                selected=len(final),
                sample=final[:2]
            )
        except Exception:
            pass
        return final

    def split_into_tasks(self, sentence: str) -> List[str]:
        t0 = time.perf_counter()
        try:
            from flask import current_app
            logger = current_app.extensions['app_context'].get_service('app_logger')
        except Exception:
            logger = None

        segments = self.ensemble_split(sentence)
        final = [seg for seg in segments if len(seg.split()) >= 2] or [sentence.strip()]

        if logger:
            logger.debug(
                "SPLITTER.final",
                input_len=len(sentence or ""),
                segments_count=len(final),
                sample=final[:3],
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
        return final


