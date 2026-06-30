# app/notion/smart_mapping/notion_page_engine.py
import json
import re
import time
from typing import Dict, List

from flask import current_app, has_request_context, request, g
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.notion.models.schemas import PartialCandidate
from app.notion.smart_mapping.detector_registry import DetectorRegistry
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


def _get_correlation_id() -> str | None:
    if not has_request_context():
        return None
    return getattr(g, "correlation_id", None) or request.headers.get("X-Correlation-ID")


def _log_event(logger, level, event: str, **fields) -> None:
    payload = {
        "event": event,
        "correlation_id": _get_correlation_id(),
        **fields,
    }
    logger.log(level, json.dumps(payload))


class NotionPageEngine:
    def __init__(
        self,
        caching_service: ICacheService,
        features_service: FeaturesService,
        preferences_service: PreferencesService,
        detector_registry: DetectorRegistry,
    ):
        self.caching_service = caching_service
        self.features_service = features_service
        self.sectionizer = Sectionizer()
        self.aggregator = PageAggregator(preferences_service)
        self.sentence_splitter = SentenceSplitter()
        self.registry = detector_registry
        self.logger = current_app.logger

        self._register_extractors()
        self.extractor_aggregator = FieldDetectorAggregator(self.registry)

    def _register_extractors(self):
        self.registry.register_detector(TitleExtractor(self.features_service))
        self.registry.register_detector(DueDateExtractor(self.features_service))
        self.registry.register_detector(PriorityExtractor(self.features_service))
        self.registry.register_detector(DurationExtractor(self.features_service))
        self.registry.register_detector(UrgencyClassifier(self.features_service))
        self.registry.register_detector(CompletionExtractor(self.features_service))
        self.registry.register_detector(TagExtractor(self.features_service))
        self.registry.register_detector(DescriptionExtractor(self.features_service))

    def generate_candidates(
        self,
        blocks: List[Dict],
        db: Session,
        user_id: int,
        page_id: str,
        force_single_task: bool,
    ) -> List[TaskCandidateData]:
        settings = self.features_service.get_settings(db, user_id)
        start = time.monotonic()

        _log_event(
            self.logger,
            20,  # logging.INFO
            "page_engine.start",
            user_id=user_id,
            page_id=page_id,
            use_ai_page_extraction=settings.use_ai_page_extraction,
            block_count=len(blocks),
        )

        if not settings.use_ai_page_extraction:
            _log_event(
                self.logger,
                20,
                "page_engine.ai_disabled",
                user_id=user_id,
                page_id=page_id,
            )
            return []

        sections = self.sectionizer.segment(blocks)
        _log_event(
            self.logger,
            20,
            "page_engine.sections_created",
            user_id=user_id,
            page_id=page_id,
            section_count=len(sections),
        )

        partials: List[PartialCandidate] = []
        app = current_app._get_current_object()

        for idx, section in enumerate(sections):
            section_start = time.monotonic()
            try:
                extracted = self._extract_from_section(section, db, user_id, app)
                partials.extend(extracted)
                _log_event(
                    self.logger,
                    20,
                    "page_engine.section_extracted",
                    user_id=user_id,
                    page_id=page_id,
                    section_index=idx,
                    partial_count=len(extracted),
                    duration_ms=int((time.monotonic() - section_start) * 1000),
                )
            except Exception as e:
                _log_event(
                    self.logger,
                    40,  # logging.ERROR
                    "page_engine.section_extraction_error",
                    user_id=user_id,
                    page_id=page_id,
                    section_index=idx,
                    error=str(e),
                    duration_ms=int((time.monotonic() - section_start) * 1000),
                )

        _log_event(
            self.logger,
            20,
            "page_engine.partials_aggregated_start",
            user_id=user_id,
            page_id=page_id,
            partial_count=len(partials),
        )

        agg_start = time.monotonic()
        candidates = self.aggregator.aggregate(partials, user_id, page_id, db, sections, force_single_task)
        agg_duration_ms = int((time.monotonic() - agg_start) * 1000)

        _log_event(
            self.logger,
            20,
            "page_engine.partials_aggregated_complete",
            user_id=user_id,
            page_id=page_id,
            candidate_count=len(candidates),
            aggregation_duration_ms=agg_duration_ms,
            total_duration_ms=int((time.monotonic() - start) * 1000),
        )

        return candidates

    def _extract_from_section(
        self,
        section: BlockSection,
        db: Session,
        user_id: int,
        app,
    ) -> List[PartialCandidate]:
        with app.app_context():
            partials: List[PartialCandidate] = []
            extraction_order = 0
            settings = self.features_service.get_settings(db, user_id)

            for block_index, block in enumerate(section.blocks):
                block_start = time.monotonic()
                raw_text = self._extract_text_from_block(block)

                segments = (
                    self.sentence_splitter.split_into_tasks(raw_text)
                    if settings.use_sentence_splitter
                    else [raw_text]
                )

                for segment in segments:
                    if not segment.strip():
                        continue

                    remaining_text = segment
                    span_index = 0
                    iters = 0
                    previous_text = ""

                    while remaining_text and iters < 20:
                        previous_text = remaining_text
                        iters += 1

                        partial = PartialCandidate(confidence=0.5)
                        total_conf = 0.0
                        count = 0

                        for extractor in self.registry.get_detectors():
                            extracted = extractor.extract([self._block_from_text(remaining_text)], db, user_id)

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
                            if extracted.urgency:
                                partial.urgency = extracted.urgency

                            if extracted.confidence:
                                total_conf += extracted.confidence
                                count += 1

                        partial.confidence = total_conf / count if count > 0 else 0.5
                        partial.block_id = block.get("id")
                        partial.block_index = block_index
                        partial.span_index = span_index
                        partial.extraction_order = extraction_order

                        has_signal = any(
                            [
                                partial.title,
                                partial.due_date,
                                partial.description,
                                partial.duration,
                                partial.priority,
                                partial.status,
                                partial.tags,
                                partial.urgency != 0.5,
                            ]
                        )

                        if has_signal:
                            partials.append(partial)

                        remaining_text = self._remove_matched_spans(remaining_text, partial)

                        if not has_signal:
                            break

                        if remaining_text == previous_text:
                            _log_event(
                                self.logger,
                                30,  # logging.WARNING
                                "page_engine.no_progress_block",
                                user_id=user_id,
                                block_id=block.get("id"),
                                block_index=block_index,
                            )
                            break

                        span_index += 1
                        extraction_order += 1

                _log_event(
                    self.logger,
                    20,
                    "page_engine.block_extracted",
                    user_id=user_id,
                    block_id=block.get("id"),
                    block_index=block_index,
                    partial_count=len(partials),
                    duration_ms=int((time.monotonic() - block_start) * 1000),
                )

            return partials

    def _remove_matched_spans(self, text: str, partial: PartialCandidate) -> str:
        spans = []

        for field in ["title", "description", "priority", "status"]:
            value = getattr(partial, field, None)
            if value and isinstance(value, str):
                for m in re.finditer(re.escape(value), text):
                    spans.append((m.start(), m.end()))
                    break

        if partial.tags:
            for tag in partial.tags:
                for m in re.finditer(re.escape(tag), text):
                    spans.append((m.start(), m.end()))
                    break

        if partial.due_date and isinstance(partial.due_date, str):
            for m in re.finditer(re.escape(partial.due_date), text):
                spans.append((m.start(), m.end()))
                break

        if partial.duration:
            duration_str = (
                f"{partial.duration} minutes"
                if partial.duration < 60
                else f"{partial.duration // 60} hours"
            )
            for m in re.finditer(re.escape(duration_str), text):
                spans.append((m.start(), m.end()))
                break

        if not spans:
            return text

        spans.sort()
        cleaned = []
        last_end = -1

        for start, end in spans:
            if start >= last_end:
                cleaned.append((start, end))
                last_end = end

        new_text = text
        for start, end in reversed(cleaned):
            new_text = new_text[:start] + new_text[end:]

        return re.sub(r"\s{2,}", " ", new_text).strip()

    def _block_from_text(self, text: str) -> dict:
        return {"type": "paragraph", "text": [{"plain_text": text}]}

    def _extract_text_from_block(self, block: dict) -> str:
        if not isinstance(block, dict):
            return ""

        block_type = block.get("type")
        main_text = ""

        rich_types = [
            "paragraph",
            "to_do",
            "heading_1",
            "heading_2",
            "heading_3",
            "bulleted_list_item",
            "numbered_list_item",
            "toggle",
            "callout",
            "quote",
            "code",
        ]

        if block_type in rich_types:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            main_text = "".join(rt.get("plain_text", "") for rt in rich_text).strip()

        caption_types = ["image", "video", "embed", "file", "pdf", "equation", "bookmark"]
        if block_type in caption_types:
            caption = block.get(block_type, {}).get("caption", [])
            main_text = "".join(rt.get("plain_text", "") for rt in caption).strip()

        if block_type == "code":
            language = block.get("code", {}).get("language", "")
            if language:
                main_text = f"[{language}] {main_text}"

        child_text = ""
        if block.get("has_children") and "children" in block:
            child_text = " ".join(
                self._extract_text_from_block(child) for child in block["children"] if child
            )

        return (main_text + ("\n" + child_text if child_text else "")).strip()
