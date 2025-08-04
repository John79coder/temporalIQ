# notion/client/notion_client.py
from typing import List, Dict, Optional
import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import logging

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

    # NEW: Added method for fetching page blocks recursively
    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(requests.RequestException))
    def fetch_page_blocks(self, access_token: str, page_id: str) -> List[Dict]:
        def fetch_children(block_id: str, cursor: Optional[str] = None) -> List[Dict]:
            headers = {"Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
                       "Notion-Version": "2022-06-28"}
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            response = requests.get(f"{self.base_url}/blocks/{block_id}/children", headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if data.get("has_more"):
                results += fetch_children(block_id, data["next_cursor"])
            for block in results:
                if block.get("has_children"):
                    block["children"] = fetch_children(block["id"])
            return results

        results = fetch_children(page_id)
        logging.info(f"Successfully fetched blocks for page {page_id}")
        return results