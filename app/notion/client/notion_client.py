# app/notion/client/notion_client.py
import json
import logging
import time
from typing import List, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.utils.encryption import Encryptor
from app.utils.exceptions import wrap_external_error, NotionError
from app.utils.log_event import log_event 

logger = logging.getLogger(__name__)

class NotionClient:
    def __init__(self, encryptor: Encryptor):
        self.encryptor = encryptor
        self.base_url = "https://api.notion.com/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_schema(self, access_token: str, database_id: str) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }
        start = time.monotonic()
        try:
            response = requests.get(f"{self.base_url}/databases/{database_id}", headers=headers)
            response.raise_for_status()
            schema = response.json().get("properties", {})
            log_event(
                logging.INFO,
                "notion_client.fetch_schema_success",
                database_id=database_id,
                property_count=len(schema),
                status_code=response.status_code,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return schema
        except requests.HTTPError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            status_code = e.response.status_code if e.response is not None else None
            if status_code in {401, 403, 404}:
                log_event(
                    logging.ERROR,
                    "notion_client.fetch_schema_non_retryable",
                    database_id=database_id,
                    status_code=status_code,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                raise NotionError(f"Failed to fetch Notion schema: {e}")
            log_event(
                logging.WARNING,
                "notion_client.fetch_schema_retryable",
                database_id=database_id,
                status_code=status_code,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise
        except requests.RequestException as e:
            log_event(
                logging.WARNING,
                "notion_client.fetch_schema_request_error",
                database_id=database_id,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise wrap_external_error(e, NotionError, "Failed to fetch Notion schema")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_rows(self, access_token: str, database_id: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }
        start = time.monotonic()
        try:
            response = requests.post(
                f"{self.base_url}/databases/{database_id}/query",
                headers=headers,
                json={},
            )
            response.raise_for_status()
            rows = response.json().get("results", [])
            log_event(
                logging.INFO,
                "notion_client.fetch_rows_success",
                database_id=database_id,
                row_count=len(rows),
                status_code=response.status_code,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return rows
        except requests.HTTPError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            status_code = e.response.status_code if e.response is not None else None
            if status_code in {401, 403, 404}:
                log_event(
                    logging.ERROR,
                    "notion_client.fetch_rows_non_retryable",
                    database_id=database_id,
                    status_code=status_code,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                raise NotionError(f"Failed to fetch Notion rows: {e}")
            log_event(
                logging.WARNING,
                "notion_client.fetch_rows_retryable",
                database_id=database_id,
                status_code=status_code,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise
        except requests.RequestException as e:
            log_event(
                logging.WARNING,
                "notion_client.fetch_rows_request_error",
                database_id=database_id,
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise wrap_external_error(e, NotionError, "Failed to fetch Notion rows")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def list_databases(self, access_token: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }
        start = time.monotonic()
        try:
            response = requests.get(f"{self.base_url}/databases", headers=headers)
            response.raise_for_status()
            databases = response.json().get("results", [])
            log_event(
                logging.INFO,
                "notion_client.list_databases_success",
                database_count=len(databases),
                status_code=response.status_code,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return databases
        except requests.HTTPError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            status_code = e.response.status_code if e.response is not None else None
            if status_code in {401, 403, 404}:
                log_event(
                    logging.ERROR,
                    "notion_client.list_databases_non_retryable",
                    status_code=status_code,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                raise NotionError(f"Failed to list Notion databases: {e}")
            log_event(
                logging.WARNING,
                "notion_client.list_databases_retryable",
                status_code=status_code,
                error=str(e),
                duration_ms=duration_ms,
            )
            raise
        except requests.RequestException as e:
            log_event(
                logging.WARNING,
                "notion_client.list_databases_request_error",
                error=str(e),
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            raise wrap_external_error(e, NotionError, "Failed to list Notion databases")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_page_blocks(self, access_token: str, page_id: str) -> List[Dict]:
        def fetch_children(block_id: str, cursor: Optional[str] = None) -> List[Dict]:
            headers_inner = {
                "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
                "Notion-Version": "2022-06-28",
            }
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            start_inner = time.monotonic()
            try:
                response = requests.get(
                    f"{self.base_url}/blocks/{block_id}/children",
                    headers=headers_inner,
                    params=params,
                )
                response.raise_for_status()
            except requests.HTTPError as e:
                duration_ms = int((time.monotonic() - start_inner) * 1000)
                status_code = e.response.status_code if e.response is not None else None
                if status_code in {401, 403, 404}:
                    log_event(
                        logging.ERROR,
                        "notion_client.fetch_children_non_retryable",
                        block_id=block_id,
                        status_code=status_code,
                        error=str(e),
                        duration_ms=duration_ms,
                    )
                    raise NotionError(f"Failed to [redacted] blocks: {e}")
                log_event(
                    logging.WARNING,
                    "notion_client.fetch_children_retryable",
                    block_id=block_id,
                    status_code=status_code,
                    error=str(e),
                    duration_ms=duration_ms,
                )
                raise
            except requests.RequestException as e:
                log_event(
                    logging.WARNING,
                    "notion_client.fetch_children_request_error",
                    block_id=block_id,
                    error=str(e),
                    duration_ms=int((time.monotonic() - start_inner) * 1000),
                )
                raise

            data = response.json()
            results = data.get("results", [])
            if data.get("has_more"):
                results += fetch_children(block_id, data["next_cursor"])
            for block in results:
                if block.get("has_children"):
                    block["children"] = fetch_children(block["id"])
            return results

        start = time.monotonic()
        results = fetch_children(page_id)
        log_event(
            logging.INFO,
            "notion_client.fetch_page_blocks_success",
            page_id=page_id,
            top_level_block_count=len(results),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        return results
