# app/notion/smart_mapping/field_detectors/llm_detector.py
from sqlalchemy.orm.session import Session
from app.notion.smart_mapping.field_detectors.base import FieldDetector
from app.notion.smart_mapping.models import FieldMatch
from app.utils.exceptions import wrap_external_error, ServiceUnavailableError
from typing import List
import openai
import os
import json
from app.utils.logging_service import LoggingService
from app.features.services.service import FeaturesService


class LLMDetector(FieldDetector):
    def __init__(self, features_service: FeaturesService, logging_service: LoggingService):
        self.features_service = features_service
        self.logging_service = logging_service
        api_key = os.getenv("OPENAI_API_KEY")
        self.client = openai.OpenAI(api_key=api_key) if api_key else None

    def detect(self, fields: list[dict], rows: List[dict] = None, db: Session = None, user_id: int = None) -> list[FieldMatch]:
        if not self.client:
            raise ServiceUnavailableError("OpenAI API key not configured")

        user_ai_settings = self.features_service.get_settings(db, user_id)
        use_llm_mapping = user_ai_settings.use_llm_mapping

        if not use_llm_mapping:
            return []  # Skip if toggled off

        try:
            schema_str = "\n".join([f"- {f['name']}: type={f['type']}" for f in fields])
            row_sample = rows[:5] if rows else []  # Limit to 5 for prompt size
            rows_str = "\nSample rows: " + "\n".join([str(row.get('properties', {})) for row in row_sample]) if row_sample else ""

            prompt = f"""
Map these Notion fields to task concepts like title, due_date, duration, priority, status, etc.
Schema:
{schema_str}
{rows_str}
Output JSON object: {{"matches": [{{"notion_field": "field_name", "matched_concept": "concept", "confidence": 0.0-1.0, "rationale": "explanation"}}]}}
Resolve ambiguities, e.g., if multiple dates, pick the most likely due_date and explain.
"""
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                response_format={"type": "json_object"}
            )
            matches_json = response.choices[0].message.content
            self.logging_service.info(f"Raw LLM response: {matches_json}", user_id=user_id)

            try:
                matches_list = json.loads(matches_json)
                if isinstance(matches_list, dict):
                    matches_list = matches_list.get('matches', []) or list(matches_list.values())[0] if len(matches_list) == 1 else []
                return [FieldMatch(**m) for m in matches_list]
            except json.JSONDecodeError as e:
                self.logging_service.error(f"Failed to parse LLM response JSON: {str(e)}", user_id=user_id)
                raise wrap_external_error(e, ServiceUnavailableError, "Invalid LLM response format")
            except (TypeError, ValueError) as e:
                self.logging_service.error(f"Failed to process LLM matches: {str(e)}", user_id=user_id)
                raise wrap_external_error(e, ServiceUnavailableError, "Invalid LLM match data")
        except openai.APIError as e:
            self.logging_service.error(f"OpenAI API error: {str(e)}", user_id=user_id)
            raise wrap_external_error(e, ServiceUnavailableError, "OpenAI API call failed")
        except openai.RateLimitError as e:
            self.logging_service.error(f"OpenAI rate limit exceeded: {str(e)}", user_id=user_id)
            raise wrap_external_error(e, ServiceUnavailableError, "OpenAI rate limit exceeded")
        except Exception as e:
            self.logging_service.error(f"Unexpected error in LLM detection: {str(e)}", user_id=user_id)
            raise wrap_external_error(e, ServiceUnavailableError, "LLM mapping failed")