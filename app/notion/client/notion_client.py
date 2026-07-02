# app/notion/client/notion_client.py

from typing import List, Dict, Optional

import requests
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from app.utils.encryption import Encryptor
from app.utils.exceptions import wrap_external_error, NotionError


class NotionClient:
    def __init__(self, encryptor: Encryptor):
        self.encryptor = encryptor
        self.base_url = "https://api.notion.com/v1"

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2),
           retry=retry_if_exception_type(requests.RequestException))
    def fetch_schema(self, access_token: str, database_id: str) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }

        try:
            response = requests.get(f"{self.base_url}/databases/{database_id}", headers=headers)
            response.raise_for_status()
            return response.json().get("properties", {})

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None

            if status_code in {401, 403, 404}:
                raise NotionError(f"Failed to fetch Notion schema: {e}")

            raise

        except requests.RequestException as e:
            raise wrap_external_error(e, NotionError, "Failed to fetch Notion schema")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2),
           retry=retry_if_exception_type(requests.RequestException))
    def fetch_rows(self, access_token: str, database_id: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }

        try:
            response = requests.post(
                f"{self.base_url}/databases/{database_id}/query",
                headers=headers,
                json={},
            )
            response.raise_for_status()
            return response.json().get("results", [])

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None

            if status_code in {401, 403, 404}:
                raise NotionError(f"Failed to fetch Notion rows: {e}")

            raise

        except requests.RequestException as e:
            raise wrap_external_error(e, NotionError, "Failed to fetch Notion rows")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2),
           retry=retry_if_exception_type(requests.RequestException))
    def list_databases(self, access_token: str) -> List[Dict]:
        headers = {
            "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
            "Notion-Version": "2022-06-28",
        }

        try:
            response = requests.get(f"{self.base_url}/databases", headers=headers)
            response.raise_for_status()
            return response.json().get("results", [])

        except requests.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None

            if status_code in {401, 403, 404}:
                raise NotionError(f"Failed to list Notion databases: {e}")

            raise

        except requests.RequestException as e:
            raise wrap_external_error(e, NotionError, "Failed to list Notion databases")

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2),
           retry=retry_if_exception_type(requests.RequestException))
    def fetch_page_blocks(self, access_token: str, page_id: str) -> List[Dict]:

        def fetch_children(block_id: str, cursor: Optional[str] = None) -> List[Dict]:
            headers_inner = {
                "Authorization": f"Bearer {self.encryptor.decrypt(access_token)}",
                "Notion-Version": "2022-06-28",
            }

            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            try:
                response = requests.get(
                    f"{self.base_url}/blocks/{block_id}/children",
                    headers=headers_inner,
                    params=params,
                )
                response.raise_for_status()

            except requests.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None

                if status_code in {401, 403, 404}:
                    raise NotionError(f"Failed to fetch Notion blocks: {e}")

                raise

            except requests.RequestException as e:
                raise wrap_external_error(e, NotionError, "Failed to fetch Notion blocks")

            data = response.json()
            results = data.get("results", [])

            if data.get("has_more"):
                results += fetch_children(block_id, data["next_cursor"])

            for block in results:
                if block.get("has_children"):
                    block["children"] = fetch_children(block["id"])

            return results

        return fetch_children(page_id)
