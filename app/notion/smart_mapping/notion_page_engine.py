import logging
import re
from typing import Dict
from typing import List

from flask import current_app
from sqlalchemy.orm import Session

from app.features.services.service import FeaturesService
from app.logging import ApplicationLogger
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


class NotionPageEngine:
    def __init__(self, caching_service: ICacheService, features_service: FeaturesService,
                 preferences_service: PreferencesService, detector_registry: DetectorRegistry, logging_service: ApplicationLogger):
        self.caching_service = caching_service
        self.features_service = features_service
        self.sectionizer = Sectionizer()
        self.aggregator = PageAggregator(preferences_service)
        self.sentence_splitter = SentenceSplitter()
        self.registry = detector_registry
        self.logging_service = logging_service
        self._register_extractors()
        self.extractor_aggregator = FieldDetectorAggregator(self.registry),

    def _register_extractors(self):
        """Register all page value extractors."""
        self.registry.register_detector(TitleExtractor(self.features_service))
        self.registry.register_detector(DueDateExtractor(self.features_service))
        self.registry.register_detector(PriorityExtractor(self.features_service))
        self.registry.register_detector(DurationExtractor(self.features_service))
        self.registry.register_detector(UrgencyClassifier(self.features_service, self.logging_service))
        self.registry.register_detector(CompletionExtractor(self.features_service))
        self.registry.register_detector(TagExtractor(self.features_service))
        self.registry.register_detector(DescriptionExtractor(self.features_service))

    def generate_candidates(self, blocks: List[Dict], db: Session, user_id: int, page_id: str,
                            force_single_task: bool) -> List[
        TaskCandidateData]:
        settings = self.features_service.get_settings(db, user_id)
        if not settings.use_ai_page_extraction:
            return []  # Or fallback to basic extraction if needed

        sections = self.sectionizer.segment(blocks)
        partials = []
        app = current_app._get_current_object()  # For context (now used in main thread)

        # Run sequentially to avoid thread/mock issues; parallelism can be re-added via config if needed
        for section in sections:
            try:
                partial = self._extract_from_section(section, db, user_id, app)
                partials.extend(partial)
            except Exception as e:
                logging.error(f"Extraction failed for section: {str(e)}")

        candidates = self.aggregator.aggregate(partials, user_id, page_id, db, sections, force_single_task)

        return candidates

    def _extract_from_section(self, section: BlockSection, db: Session, user_id: int, app) -> List[PartialCandidate]:
        with app.app_context():
            partials: List[PartialCandidate] = []
            extraction_order = 0
            settings = self.features_service.get_settings(db, user_id)  # Added: Fetch settings for toggle

            for block_index in range(len(section.blocks)):
                block = section.blocks[block_index]
                raw_text = self._extract_text_from_block(block)  # Now expanded and recursive

                segments = self.sentence_splitter.split_into_tasks(raw_text) if settings.use_sentence_splitter else [
                    raw_text]

                segment_span_base = 0

                for segment in segments:
                    if not segment.strip():
                        continue
                    remaining_text = segment
                    span_index = segment_span_base
                    iters = 0  # New: Iteration counter for safeguard
                    previous_text = ""  # New: Track for progress detection

                    while remaining_text and iters < 20:  # New: Max 20 iterations per segment
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

                        if any([partial.title, partial.due_date, partial.description, partial.duration,
                                partial.priority, partial.status, partial.tags, partial.urgency != 0.5]):
                            partials.append(partial)

                        remaining_text = self._remove_matched_spans(remaining_text, partial)

                        if not any([partial.title, partial.due_date, partial.description, partial.duration,
                                    partial.priority, partial.status, partial.tags, partial.urgency != 0.5]):
                            break

                        if remaining_text == previous_text:
                            logging.warning(
                                f"No progress in extraction for block {block.get('id')}; breaking to prevent stall")
                            break

                        span_index += 1
                        extraction_order += 1

                    segment_span_base = span_index

            return partials

    def _remove_matched_spans(self, text: str, partial: PartialCandidate) -> str:
        """
        Remove substrings from `text` that correspond to fields in the PartialCandidate.
        Attempts exact match removal first. If overlapping spans, removes largest first.
        """
        spans = []
        # Collect spans for all non-None fields
        for field in ['title', 'description', 'priority', 'status']:
            value = getattr(partial, field, None)
            if value and isinstance(value, str):
                pattern = re.escape(value)
                for m in re.finditer(pattern, text):
                    spans.append((m.start(), m.end()))
                    break  # Only first occurrence
        # Tags are a list
        if partial.tags:
            for tag in partial.tags:
                pattern = re.escape(tag)
                for m in re.finditer(pattern, text):
                    spans.append((m.start(), m.end()))
                    break
        # Due date (if stringified in text)
        if partial.due_date and isinstance(partial.due_date, str):
            pattern = re.escape(partial.due_date)
            for m in re.finditer(pattern, text):
                spans.append((m.start(), m.end()))
                break
        # Duration (if stringified, e.g., "2 hours")
        if partial.duration:
            # Approximate duration string (e.g., "2 hours" or "120 minutes")
            duration_str = f"{partial.duration} minutes" if partial.duration < 60 else f"{partial.duration // 60} hours"
            pattern = re.escape(duration_str)
            for m in re.finditer(pattern, text):
                spans.append((m.start(), m.end()))
                break

        if not spans:
            return text

        # Merge and sort spans to avoid overlaps
        spans.sort()
        cleaned_spans = []
        last_end = -1
        for start, end in spans:
            if start >= last_end:
                cleaned_spans.append((start, end))
                last_end = end

        # Remove spans from text
        new_text = text
        for start, end in reversed(cleaned_spans):
            new_text = new_text[:start] + new_text[end:]

        # Cleanup: collapse double spaces, strip
        new_text = re.sub(r'\s{2,}', ' ', new_text).strip()
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
        if block.get('has_children') and 'children' in block:  # Assuming fetch populates children
            child_text = " ".join(self._extract_text_from_block(child) for child in block['children'] if child)

        # Combine: main + children (separated by newline for structure)
        combined = main_text + ("\n" + child_text if child_text else "")
        return combined.strip()
