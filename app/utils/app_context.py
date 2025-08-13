# app/utils/app_context.py
from typing import Any


class AppContext:
    def __init__(self):
        self.services: dict[str, Any] = {}

    def set_service(self, name: str, service: Any) -> None:
        self.services[name] = service

    def get_service(self, name: str) -> Any:
        return self.services.get(name)
