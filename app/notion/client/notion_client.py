# notion/client/notion_client.py
import logging
from typing import List, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.utils.encryption import Encryptor


class NotionClient:
    def __init__(self, encryptor: Encryptor):
        self.encryptor = encryptor
        self.base_url = "https://api.notion.com/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_schema(self, access_token: str, database_id: str) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28"
        }
        response = requests.get(f"{self.base_url}/databases/{database_id}", headers=headers)
        response.raise_for_status()
        logging.info(f"Successfully fetched Notion schema for database {database_id}")
        return response.json().get("properties", {})

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_rows(self, access_token: str, database_id: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28"
        }
        response = requests.post(
            f"{self.base_url}/databases/{database_id}/query",
            headers=headers,
            json={}
        )
        response.raise_for_status()
        logging.info(f"Successfully fetched Notion rows for database {database_id}")
        return response.json().get("results", [])

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def list_databases(self, access_token: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28"
        }
        response = requests.get(f"{self.base_url}/databases", headers=headers)
        response.raise_for_status()
        logging.info("Successfully listed Notion databases")
        return response.json().get("results", [])

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_page_blocks(self, access_token: str, page_id: str) -> List[Dict]:
        from flask import current_app
        import time

        logger = None
        try:
            logger = current_app.extensions['app_context'].get_service('app_logger')
        except Exception:
            pass

        def fetch_children(block_id: str, cursor: Optional[str] = None) -> List[Dict]:
            headers = {
                "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
                "Notion-Version": "2022-06-28"
            }
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            t0 = time.perf_counter()
            resp = requests.get(f"{self.base_url}/blocks/{block_id}/children", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])

            if logger:
                logger.debug(
                    "NOTION_CLIENT.blocks.page",
                    page_or_block_id=block_id,
                    batch_count=len(results),
                    has_more=bool(data.get("has_more")),
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    status_code=resp.status_code,
                )

            if data.get("has_more"):
                results += fetch_children(block_id, data["next_cursor"])

            for block in results:
                if block.get("has_children"):
                    block["children"] = fetch_children(block["id"])

            return results

        t_all0 = time.perf_counter()
        blocks = fetch_children(page_id)
        if logger:
            first_types = list({b.get('type') for b in blocks})[:5]
            logger.info(
                "NOTION_CLIENT.fetched_blocks",
                page_id=page_id,
                blocks_count=len(blocks),
                first_types=first_types,
                duration_ms=int((time.perf_counter() - t_all0) * 1000),
            )
        return blocks

