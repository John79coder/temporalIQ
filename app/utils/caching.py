# app/utils/caching.py
import logging
import os
import pickle
import time
from abc import ABC, abstractmethod
from typing import Any, Optional

import redis
from flask_caching import Cache

from app.utils.exceptions import ServiceUnavailableError, wrap_external_error
from .security import SecurityService


class ICacheService(ABC):
    @abstractmethod
    def set(self, key: str, value: Any, timeout: int = 3600, encrypt: bool = False) -> None:
        pass

    @abstractmethod
    def get(self, key: str, decrypt: bool = False) -> Optional[Any]:
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        pass

    @abstractmethod
    def clear_all(self) -> None:
        pass

    @abstractmethod
    def clear_user_cache(self, user_id: int) -> None:
        pass

    @abstractmethod
    def print_cache(self) -> None:
        pass


class RedisCacheService(ICacheService):
    def __init__(self, cache: Cache, security_service: SecurityService):
        self.cache = cache
        self.security_service = security_service
        logging.getLogger(__name__).info("Initialized RedisCacheService")

    def set(self, key: str, value: Any, timeout: int = 3600, encrypt: bool = False) -> None:
        try:
            if encrypt:
                value = self.security_service.encrypt_data(value)
            serialized = pickle.dumps(value)
            self.cache.set(key, serialized, timeout=timeout)
            logging.getLogger(__name__).info(f"Cache set for key: {key}")
        except redis.RedisError as e:
            logging.getLogger(__name__).error(f"Redis error setting cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to set cache")

    def get(self, key: str, decrypt: bool = False) -> Optional[Any]:
        try:
            serialized = self.cache.get(key)
            if serialized is None:
                logging.getLogger(__name__).info(f"Cache miss for key: {key}")
                return None
            value = pickle.loads(serialized)
            if decrypt:
                value = self.security_service.decrypt_data(value)
            logging.getLogger(__name__).info(f"Cache hit for key: {key}")
            return value
        except (redis.RedisError, pickle.PickleError) as e:
            logging.getLogger(__name__).error(f"Error getting cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to get cache")

    def delete(self, key: str) -> bool:
        try:
            result = self.cache.delete(key)
            logging.getLogger(__name__).info(f"Cache deleted for key: {key}, success: {result}")
            return result
        except redis.RedisError as e:
            logging.getLogger(__name__).error(f"Redis error deleting cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to delete cache")

    def clear_all(self) -> None:
        try:
            cleared = self.cache.clear()
            if not cleared:
                raise ServiceUnavailableError("Failed to clear cache")
            logging.getLogger(__name__).info("Cache cleared successfully")
        except redis.RedisError as e:
            logging.getLogger(__name__).error(f"Redis error clearing cache: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to clear cache")

    def clear_user_cache(self, user_id: int) -> None:
        keys = [
            f"user:{user_id}:preferences",
            f"icloud:connection:{user_id}",
            f"icloud:client:{user_id}",
            f"icloud:default_calendar:{user_id}",
            f"notion:connection:{user_id}",
            f"notion:databases:{user_id}",
        ]
        for key in keys:
            self.delete(key)
        logging.getLogger(__name__).info(f"User cache cleared for user_id: {user_id}")

    def print_cache(self) -> None:
        try:
            logging.getLogger(__name__).info(
                "Redis cache contents cannot be directly printed. Use Redis CLI for inspection.")
        except Exception as e:
            logging.getLogger(__name__).error(f"Error accessing cache: {str(e)}")


class InMemoryCacheService(ICacheService):
    def __init__(self, security_service: SecurityService):
        self.security_service = security_service
        self.store = {}
        self.expires = {}
        logging.getLogger(__name__).info("Initialized InMemoryCacheService")

    def set(self, key: str, value: Any, timeout: int = 3600, encrypt: bool = False) -> None:
        try:
            if encrypt:
                value = self.security_service.encrypt_data(value)
            self.store[key] = pickle.dumps(value)
            self.expires[key] = time.time() + timeout if timeout else None
            logging.getLogger(__name__).info(f"In-memory cache set for key: {key}")
        except pickle.PickleError as e:
            logging.getLogger(__name__).error(f"Pickle error setting in-memory cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to set in-memory cache")

    def get(self, key: str, decrypt: bool = False) -> Optional[Any]:
        try:
            if key in self.store:
                expiry = self.expires.get(key)
                if expiry is None or time.time() < expiry:
                    value = pickle.loads(self.store[key])
                    if decrypt:
                        value = self.security_service.decrypt_data(value)
                    logging.getLogger(__name__).info(f"In-memory cache hit for key: {key}")
                    return value
                del self.store[key]
                del self.expires[key]
                logging.getLogger(__name__).info(f"In-memory cache expired for key: {key}")
            logging.getLogger(__name__).info(f"In-memory cache miss for key: {key}")
            return None
        except (pickle.PickleError, TypeError) as e:
            logging.getLogger(__name__).error(f"Error getting in-memory cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to get in-memory cache")

    def delete(self, key: str) -> bool:
        try:
            if key in self.store:
                del self.store[key]
                del self.expires[key]
                logging.getLogger(__name__).info(f"In-memory cache deleted for key: {key}")
                return True
            logging.getLogger(__name__).info(f"In-memory cache miss for delete key: {key}")
            return False
        except TypeError as e:
            logging.getLogger(__name__).error(f"Error deleting in-memory cache for key {key}: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to delete in-memory cache")

    def clear_all(self) -> None:
        try:
            self.store.clear()
            self.expires.clear()
            logging.getLogger(__name__).info("In-memory cache cleared successfully")
        except TypeError as e:
            logging.getLogger(__name__).error(f"Error clearing in-memory cache: {str(e)}")
            raise wrap_external_error(e, ServiceUnavailableError, "Failed to clear in-memory cache")

    def clear_user_cache(self, user_id: int) -> None:
        keys = [
            f"user:{user_id}:preferences",
            f"icloud:connection:{user_id}",
            f"icloud:client:{user_id}",
            f"icloud:default_calendar:{user_id}",
            f"notion:connection:{user_id}",
            f"notion:databases:{user_id}",
        ]
        for key in keys:
            self.delete(key)
        logging.getLogger(__name__).info(f"In-memory user cache cleared for user_id: {user_id}")

    def print_cache(self) -> None:
        try:
            if not self.store:
                logging.getLogger(__name__).info("In-memory cache is empty")
                return
            for key, serialized_value in self.store.items():
                try:
                    value = pickle.loads(serialized_value)
                    if isinstance(value, str):
                        try:
                            self.security_service.decrypt_data(value)
                        except Exception as e:
                            logging.getLogger(__name__).error(f"Error decrypting cache value for key {key}: {str(e)}")
                            continue
                    logging.getLogger(__name__).info(f"In-memory cache key: {key}, value: {value}")
                except pickle.PickleError as e:
                    logging.getLogger(__name__).error(f"Pickle error deserializing cache for key {key}: {str(e)}")
        except Exception as e:
            logging.getLogger(__name__).error(f"Error accessing in-memory cache: {str(e)}")


def get_cache_service(cache: Cache, security_service: SecurityService) -> ICacheService:
    logger = logging.getLogger(__name__)
    if os.getenv("FLASK_ENV") == "test":
        logger.info("Using InMemoryCacheService for test environment")
        return InMemoryCacheService(security_service)
    logger.info("Using RedisCacheService for non-test environment")
    return RedisCacheService(cache, security_service)
