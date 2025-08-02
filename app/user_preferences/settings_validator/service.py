# user/settings_validator/service.py
from app.user_preferences.models.schemas import PreferencesCreate
import zoneinfo
import logging

class PreferencesValidator:
    def validate(self, prefs: PreferencesCreate) -> list[str]:
        errors = []
        if prefs.block_size_minutes <= 0:
            errors.append("Block size must be greater than zero.")
        if prefs.max_blocks_per_day <= 0:
            errors.append("Max blocks per day must be greater than zero.")
        if prefs.work_hours <= 0:
            errors.append("Work hours must be greater than zero.")
        if prefs.work_hours > (prefs.max_blocks_per_day * prefs.block_size_minutes) / 60:
            errors.append("Work hours exceed available time blocks.")
        if prefs.time_zone and prefs.time_zone not in zoneinfo.available_timezones():
            logging.error(f"Invalid time zone: {prefs.time_zone}")
            errors.append(f"Invalid time zone: {prefs.time_zone}")
        if prefs.block_size_minutes > 1440:
            errors.append("Block size cannot exceed 1440 minutes.")
        return errors