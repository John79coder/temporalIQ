# app/utils/time_zone.py
from datetime import datetime, date, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.utils.exceptions import DataValidationError
from typing import Union
import logging

class TimeZone:
    @staticmethod
    def to_utc(dt: datetime, tz: str) -> datetime:
        try:
            zone = ZoneInfo(tz)
            if dt.tzinfo is None:
                # Attempt to assign timezone and catch DST errors
                try:
                    # Validate by converting and comparing
                    localized = dt.replace(tzinfo=zone)
                    round_trip = localized.astimezone(timezone.utc).astimezone(zone)
                    if round_trip.replace(tzinfo=None) != dt:
                        raise ValueError(f"Non-existent local time due to DST: {dt} in {tz}")
                    dt = localized
                except Exception as inner:
                    logging.error(f"Invalid local datetime (DST or ambiguity): {dt} in {tz}")
                    raise ValueError(f"Invalid local datetime (DST or ambiguity): {dt} in {tz}") from inner
            return dt.astimezone(timezone.utc)
        except ZoneInfoNotFoundError as e:
            logging.error(f"Invalid timezone: {tz}")
            raise ValueError(f"Invalid timezone: {tz}")
        except ValueError as e:
            logging.error(f"Error with timezone '{tz}': {str(e)}")
            raise ValueError(f"Error with timezone '{tz}': {str(e)}")

    @staticmethod
    def to(dt: datetime, tz: str) -> datetime:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(tz))

    @staticmethod
    def is_utc(dt):
        return dt.tzinfo is not None and dt.utcoffset() == timezone.utc.utcoffset(None)

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(ZoneInfo("UTC"))

    @staticmethod
    def parse_utc_datetime(field: str, value: str) -> datetime:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as e:
            logging.error(f"Invalid {field} format: {value}")
            raise DataValidationError(f"{field} must be ISO 8601 (e.g., '2025-07-18T01:49:00Z')")
        if not TimeZone.is_utc(dt):
            logging.error(f"Non-UTC {field}: {value}")
            raise DataValidationError(f"{field} must be in UTC (e.g., '2025-07-18T01:49:00Z')")
        return dt

    @staticmethod
    def serialize_datetime(value: Union[datetime, date, time]) -> str:
        """
        Converts a datetime, date, or time object to an ISO 8601 string in UTC with 'Z' suffix.

        Args:
            value (datetime | date | time): The object to serialize.

        Returns:
            str: ISO 8601 formatted string with 'Z' suffix.

        Raises:
            TypeError: If the value is not a datetime, date, or time object.
        """
        if isinstance(value, datetime):
            return value.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")
        if isinstance(value, (date, time)):
            return value.isoformat()
        raise TypeError(f"Cannot serialize type {type(value).__name__} to JSON")