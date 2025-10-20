import logging
import re
import time
import uuid
from typing import Dict
from typing import List

from flask import current_app
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.detector_registry import DetectorRegistry, ExtractorRegistry
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.smart_mapping.models import TaskCandidateData
from app.notion.smart_mapping.page_value_extractors.completion_extractor import CompletionExtractor
from app.notion.smart_mapping.page_value_extractors.description_extractor import DescriptionExtractor
from app.notion.smart_mapping.page_value_extractors.due_date_extractor import DueDateExtractor
from app.notion.smart_mapping.page_value_extractors.duration_extractor import DurationExtractor
from app.notion.smart_mapping.page_value_extractors.priority_extractor import PriorityExtractor
from app.notion.smart_mapping.page_value_extractors.tag_extractor import TagExtractor
from app.notion.smart_mapping.page_value_extractors.title_extractor import TitleExtractor
from app.notion.smart_mapping.page_value_extractors.urgency_classifier import UrgencyClassifier
from app.notion.smart_mapping.partial_candidate_stitcher import PageAggregator
from app.notion.smart_mapping.sectionizer import Sectionizer, BlockSection
from app.notion.smart_mapping.sentence_task_splitter.task_splitter import SentenceSplitter
from app.user_preferences.preferences_store.service import PreferencesService
from app.utils.caching import ICacheService


class NotionPageEngine:
    def __init__(self, caching_service: ICacheService, features_service: FeaturesService,
                 preferences_service: PreferencesService, extractor_registry: ExtractorRegistry, logging_service: ApplicationLogger):
        self.caching_service = caching_service
        self.features_service = features_service
        self.sectionizer = Sectionizer()
        self.aggregator = PageAggregator(preferences_service)
        self.sentence_splitter = SentenceSplitter()
        self.registry = extractor_registry
        self.logging_service = logging_service
        self._register_extractors()
        self.extractor_aggregator = FieldDetectorAggregator(self.registry)

    def _new_run_id(self) -> str:
        return uuid.uuid4().hex[:12]

    def _now_ms(self) -> int:
        return int(time.perf_counter() * 1000)

    def _register_extractors(self):
        """Register all page value extractors."""
        self.registry.register_detector(TitleExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(DueDateExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(PriorityExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(DurationExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(CompletionExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(TagExtractor(self.features_service, self.logging_service))
        self.registry.register_detector(DescriptionExtractor(self.features_service, self.logging_service))

    def generate_candidates(
            self,
            blocks: List[Dict],
            db: Session,
            user_id: int,
            page_id: str,
            force_single_task: bool
    ) -> List[TaskCandidateData]:
        settings = self.features_service.get_settings(db, user_id)
        if not settings.use_ai_page_extraction:
            # Behavior unchanged
            return []

        run_id = self._new_run_id()
        t0 = self._now_ms()

        self.logging_service.info(
            "PAGE_ENGINE.begin",
            pipeline_run_id=run_id,
            user_id=user_id,
            page_id=page_id,
            blocks_count=len(blocks) if blocks else 0,
            force_single_task=force_single_task,
        )

        t_seg0 = self._now_ms()
        sections = self.sectionizer.segment(blocks)
        self.logging_service.debug(
            "SECTIONIZER.done",
            pipeline_run_id=run_id,
            sections_count=len(sections),
            is_single_task=all(getattr(s, "is_single_task", False) for s in sections) if sections else False,
            block_counts=[len(s.blocks) for s in sections] if sections else [],
            duration_ms=self._now_ms() - t_seg0,
        )

        partials: List[PartialCandidate] = []
        app = current_app._get_current_object()  # original pattern

        for section_index, section in enumerate(sections):
            try:
                self.logging_service.debug(
                    "PAGE_ENGINE.section.extract",
                    pipeline_run_id=run_id,
                    user_id=user_id,
                    page_id=page_id,
                    section_index=section_index,
                    blocks_in_section=len(section.blocks),
                    is_single_task=getattr(section, "is_single_task", False),
                )
                t_sec0 = self._now_ms()
                extracted = self._extract_from_section(section, db, user_id, app, pipeline_run_id=run_id,
                                                       section_index=section_index)
                self.logging_service.debug(
                    "PAGE_ENGINE.section.done",
                    pipeline_run_id=run_id,
                    section_index=section_index,
                    partials_count=len(extracted),
                    duration_ms=self._now_ms() - t_sec0,
                )
                partials.extend(extracted)
            except Exception as e:
                self.logging_service.error(
                    "PAGE_ENGINE.section.failed",
                    exception=e,
                    pipeline_run_id=run_id,
                    user_id=user_id,
                    page_id=page_id,
                    section_index=section_index,
                )

        t_ag0 = self._now_ms()
        candidates = self.aggregator.aggregate(
            partials, user_id, page_id, db, sections, force_single_task
        )
        self.logging_service.debug(
            "PAGE_ENGINE.aggregate.done",
            pipeline_run_id=run_id,
            partials_count=len(partials),
            candidates_count=len(candidates),
            duration_ms=self._now_ms() - t_ag0,
        )

        self.logging_service.info(
            "PAGE_ENGINE.end",
            pipeline_run_id=run_id,
            user_id=user_id,
            page_id=page_id,
            sections=len(sections),
            partials=len(partials),
            candidates=len(candidates),
            duration_ms=self._now_ms() - t0,
        )
        return candidates

    def _extract_from_section(
            self,
            section,
            db: Session,
            user_id: int,
            app,
            pipeline_run_id: str = None,
            section_index: int = 0
    ) -> List[PartialCandidate]:
        """
        Extract partial candidates from a section's blocks.
        Uses conservative sentence splitting only for genuinely multi-clause text.
        """
        with app.app_context():
            settings = self.features_service.get_settings(db, user_id)
            partials: List[PartialCandidate] = []
            extraction_order = 0

            for block_index, block in enumerate(section.blocks):
                raw_text = self._extract_text_from_block(block)

                if not raw_text or not raw_text.strip():
                    self.logging_service.debug(
                        "PAGE_ENGINE: extracted text from block",
                        block_id=block.get("id"),
                        block_type=block.get("type"),
                        text_len=0,
                        has_children=block.get("has_children", False),
                    )
                    continue

                self.logging_service.debug(
                    "PAGE_ENGINE: extracted text from block",
                    block_id=block.get("id"),
                    block_type=block.get("type"),
                    text_len=len(raw_text),
                    has_children=block.get("has_children", False),
                )

                t_extract0 = self._now_ms()
                self.logging_service.debug(
                    "PAGE_ENGINE.block.text_extracted",
                    pipeline_run_id=pipeline_run_id,
                    section_index=section_index,
                    block_index=block_index,
                    block_id=block.get("id"),
                    raw_len=len(raw_text),
                    duration_ms=self._now_ms() - t_extract0,
                )

                # FIX: Use conservative splitting - only spaCy, no T5 paraphrasing
                segments = self._split_text_conservative(raw_text, settings)

                t_split0 = self._now_ms()
                self.logging_service.debug(
                    "SPLITTER.done",
                    pipeline_run_id=pipeline_run_id,
                    section_index=section_index,
                    block_index=block_index,
                    input_len=len(raw_text),
                    segments_count=len(segments),
                    sample=segments[:2],
                    duration_ms=self._now_ms() - t_split0,
                )

                # Process each segment
                for segment_index, segment_text in enumerate(segments):
                    remaining_text = segment_text.strip()
                    span_index = segment_index

                    # Prevent infinite loops
                    max_iterations = 10
                    iteration = 0

                    while remaining_text and iteration < max_iterations:
                        iteration += 1
                        previous_text = remaining_text

                        # Create partial candidate
                        partial = PartialCandidate(confidence=0.5)
                        total_conf = 0.0
                        count = 0

                        # Run all extractors
                        for extractor in self.registry.get_detectors():
                            try:
                                t_ext0 = self._now_ms()
                                fake_block = self._block_from_text(remaining_text)
                                extracted = extractor.extract([fake_block], db, user_id)

                                # Merge extracted fields into partial
                                if extracted.title:
                                    partial.title = extracted.title
                                if extracted.due_date:
                                    partial.due_date = extracted.due_date
                                if extracted.description:
                                    partial.description = extracted.description
                                if extracted.duration:
                                    partial.duration = extracted.duration
                                if extracted.priority:
                                    partial.priority = extracted.priority
                                if extracted.status:
                                    partial.status = extracted.status
                                if extracted.tags:
                                    partial.tags = extracted.tags
                                if extracted.urgency is not None:
                                    partial.urgency = extracted.urgency

                                total_conf += extracted.confidence
                                count += 1

                                self.logging_service.debug(
                                    "EXTRACTOR.done",
                                    pipeline_run_id=pipeline_run_id,
                                    section_index=section_index,
                                    block_index=block_index,
                                    segment_index=segment_index,
                                    span_index=span_index,
                                    extractor=extractor.__class__.__name__,
                                    has_title=bool(extracted.title),
                                    has_due=bool(extracted.due_date),
                                    has_duration=bool(extracted.duration),
                                    has_priority=bool(extracted.priority),
                                    has_status=bool(extracted.status),
                                    tags_count=len(extracted.tags or []),
                                    duration_ms=self._now_ms() - t_ext0,
                                )
                            except Exception as e:
                                self.logging_service.error(
                                    "EXTRACTOR.failed",
                                    exception=e,
                                    extractor=extractor.__class__.__name__,
                                    pipeline_run_id=pipeline_run_id,
                                )

                        # Calculate average confidence
                        partial.confidence = total_conf / count if count else 0.5

                        # Set metadata
                        partial.block_id = block.get("id")
                        partial.block_index = block_index
                        partial.span_index = span_index
                        partial.extraction_order = extraction_order

                        # Only append if we extracted something meaningful
                        has_content = any([
                            partial.title and partial.title != "Untitled",
                            partial.due_date,
                            partial.description,
                            partial.duration,
                            partial.priority,
                            partial.status,
                            partial.tags,
                            partial.urgency is not None
                        ])

                        if has_content:
                            partials.append(partial)
                            self.logging_service.debug(
                                "PARTIAL.appended",
                                pipeline_run_id=pipeline_run_id,
                                section_index=section_index,
                                block_index=block_index,
                                segment_index=segment_index,
                                span_index=span_index,
                                fields_present=[
                                    f for f in ['title', 'description', 'due_date', 'duration', 'priority', 'status']
                                    if getattr(partial, f, None)
                                ],
                                confidence=partial.confidence,
                            )
                            extraction_order += 1
                            span_index += 1

                        # Remove matched spans from remaining text
                        t_remove0 = self._now_ms()
                        remaining_text = self._remove_matched_spans(remaining_text, partial)

                        self.logging_service.debug(
                            "SPAN_REMOVAL.done",
                            pipeline_run_id=pipeline_run_id,
                            section_index=section_index,
                            block_index=block_index,
                            segment_index=segment_index,
                            span_index=span_index,
                            before_len=len(previous_text),
                            after_len=len(remaining_text),
                            duration_ms=self._now_ms() - t_remove0,
                        )

                        # Break if no progress (avoid infinite loop)
                        if remaining_text == previous_text:
                            break

                        # Break if remaining text is too short to be meaningful
                        if len(remaining_text.strip()) < 3:
                            break

            return partials

    def _remove_matched_spans(self, text: str, partial: PartialCandidate) -> str:
        """
        Remove substrings from `text` that correspond to fields in the PartialCandidate.
        Attempts exact match removal first. If overlapping spans, removes in-order without
        introducing new helpers (keeps original behavior).
        """
        spans = []

        # Collect spans for all non-None string fields (original behavior)
        for field in ['title', 'description', 'priority', 'status']:
            value = getattr(partial, field, None)
            if value and isinstance(value, str):
                pattern = re.escape(value)
                for m in re.finditer(pattern, text):
                    spans.append((m.start(), m.end()))
                    break  # Only the first occurrence (original approach)

        # Tags are a list (original)
        if partial.tags:
            for tag in partial.tags:
                if isinstance(tag, str) and tag:
                    pattern = re.escape(tag)
                    for m in re.finditer(pattern, text):
                        spans.append((m.start(), m.end()))
                        break

        # Due date if stringified in text (original)
        if getattr(partial, "due_date", None) and isinstance(partial.due_date, str):
            pattern = re.escape(partial.due_date)
            for m in re.finditer(pattern, text):
                spans.append((m.start(), m.end()))
                break

        # Duration if stringified in text (original heuristic)
        if getattr(partial, "duration", None):
            try:
                duration = int(partial.duration)
                duration_str = f"{duration} minutes" if duration < 60 else f"{duration // 60} hours"
                pattern = re.escape(duration_str)
                for m in re.finditer(pattern, text):
                    spans.append((m.start(), m.end()))
                    break
            except Exception:
                # If duration isn't an int, do nothing (original tolerance)
                pass

        if not spans:
            return text

        # ORIGINAL: simple merge-by-order to avoid overlapping replacements
        spans.sort()
        cleaned_spans = []
        last_end = -1
        for start, end in spans:
            if start >= last_end:
                cleaned_spans.append((start, end))
                last_end = end

        # NEW: light debug breadcrumb about what will be removed (indexes only)
        try:
            self.logging_service.debug(
                "PAGE_ENGINE: remove matched spans",
                spans_found=len(spans),
                spans_used=len(cleaned_spans),
                preview=text[:120],
            )
        except Exception:
            pass

        # Build result by skipping the spans (original approach)
        result_parts = []
        cursor = 0
        for start, end in cleaned_spans:
            if cursor < start:
                result_parts.append(text[cursor:start])
            cursor = end
        if cursor < len(text):
            result_parts.append(text[cursor:])

        new_text = "".join(result_parts)

        # NEW: post-removal debug (no behavior change)
        try:
            self.logging_service.debug(
                "PAGE_ENGINE: spans removed",
                before_len=len(text),
                after_len=len(new_text),
            )
        except Exception:
            pass

        return new_text

    def _block_from_text(self, text: str) -> dict:
        return {
            "type": "paragraph",
            "text": [{"plain_text": text}]
        }

    def _extract_text_from_block(self, block: dict) -> str:
        """Recursively extracts plain text from a block and its children/caption."""
        if not isinstance(block, dict):
            return ""

        block_type = block.get('type')
        main_text = ""

        # Rich_text types (main content)
        rich_types = [
            'paragraph', 'to_do', 'heading_1', 'heading_2', 'heading_3',
            'bulleted_list_item', 'numbered_list_item', 'toggle', 'callout',
            'quote', 'code'
        ]
        if block_type in rich_types:
            rich_text = block.get(block_type, {}).get('rich_text', [])
            main_text = "".join([rt.get('plain_text', '') for rt in rich_text]).strip()

        # Caption types (for media/non-text)
        caption_types = ['image', 'video', 'embed', 'file', 'pdf', 'equation', 'bookmark']
        if block_type in caption_types:
            caption = block.get(block_type, {}).get('caption', [])  # bookmark uses 'caption' too
            main_text = "".join([rt.get('plain_text', '') for rt in caption]).strip()

        # For code: Optional prepend language for context (e.g., "python: code here")
        if block_type == 'code':
            language = block.get('code', {}).get('language', '')
            if language:
                main_text = f"[{language}] {main_text}"

        # Recurse on children if present (e.g., for toggle/callout/code with nested)
        child_text = ""
        if block.get('has_children') and 'children' in block:  # fetch assumed to populate children
            child_text = " ".join(
                self._extract_text_from_block(child)
                for child in block['children']
                if child
            )

        combined = main_text + ("\n" + child_text if child_text else "")

        # NEW: debug per block (safe & small)
        try:
            self.logging_service.debug(
                "PAGE_ENGINE: extracted text from block",
                block_id=block.get('id'),
                block_type=block_type,
                text_len=len(combined),
                has_children=bool(block.get('has_children')),
            )
        except Exception:
            pass

        return combined.strip()

    def _split_text_conservative(self, text: str, settings) -> List[str]:
        """
        Conservative text splitting using only spaCy dependency parsing.
        Only splits if text contains multiple distinct action verbs with coordination.

        NO T5 paraphrasing - eliminates duplicates and "split:" prefix issue.
        """
        if not text or not text.strip():
            return [""]


        # For short text, don't split (under 15 words)
        word_count = len(text.split())
        if word_count < 15:
            return [text.strip()]

        # Use ONLY spaCy for genuine clause splitting
        try:
            import spacy
            import os

            model_dir = current_app.config.get("MODEL_DIR", ".")
            model_path = os.path.join(model_dir, "en_core_web_md")

            nlp = spacy.load(model_path)
            doc = nlp(text)

            # Find action verbs (exclude auxiliaries and modals)
            auxiliary_lemmas = {"be", "have", "will", "can", "should", "must", "could", "would", "may", "might"}

            action_verbs = [
                tok for tok in doc
                if tok.pos_ == "VERB"
                   and tok.dep_ in ("ROOT", "conj")
                   and tok.lemma_.lower() not in auxiliary_lemmas
            ]

            # Only split if we have 2+ distinct action verbs
            if len(action_verbs) < 2:
                self.logging_service.debug(
                    "SPLITTER.spacy.no_split",
                    input_len=len(text),
                    verb_count=len(action_verbs),
                    reason="insufficient action verbs"
                )
                return [text.strip()]

            # Extract subtrees for each action verb
            segments = []
            for verb in action_verbs:
                subtree = " ".join([t.text for t in verb.subtree])
                if subtree.strip() and len(subtree.split()) >= 3:  # Meaningful segment
                    segments.append(subtree.strip())

            # Return segments only if we got meaningful splits
            if len(segments) >= 2:
                self.logging_service.debug(
                    "SPLITTER.spacy.split",
                    input_len=len(text),
                    segments_count=len(segments),
                    verb_count=len(action_verbs),
                    sample=segments[:2]
                )
                return segments
            else:
                self.logging_service.debug(
                    "SPLITTER.spacy.no_split",
                    input_len=len(text),
                    segments_extracted=len(segments),
                    reason="segments too short"
                )
                return [text.strip()]

        except Exception as e:
            self.logging_service.error(
                "SPLITTER.spacy.failed",
                exception=e,
            )

        # Default: return original text unsplit
        return [text.strip()]
