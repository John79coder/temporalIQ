import re
from datetime import datetime, timedelta, timezone
from typing import Optional
import logging


def custom_parse_date(text: str) -> Optional[datetime]:
    """Parse natural language dates to UTC datetime using stdlib."""
    text_lower = text.lower()
    now = datetime.now(timezone.utc)

    # Relative keywords
    if 'tomorrow' in text_lower:
        return now + timedelta(days=1)
    if 'next week' in text_lower:
        return now + timedelta(weeks=1)
    if 'today' in text_lower:
        return now
    if 'next friday' in text_lower:
        days_ahead = (4 - now.weekday()) % 7 + 7
        return now + timedelta(days=days_ahead)

    # Regex for YYYY-MM-DD or MM/DD/YYYY
    date_match = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{2})/(\d{2})/(\d{4})\b', text)
    if date_match:
        try:
            if date_match.group(1):  # YYYY-MM-DD
                return datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)),
                                tzinfo=timezone.utc)
            elif date_match.group(4):  # MM/DD/YYYY
                return datetime(int(date_match.group(6)), int(date_match.group(4)), int(date_match.group(5)),
                                tzinfo=timezone.utc)
        except ValueError as e:
            logging.error(f"Invalid date format in {text}: {str(e)}")
            return None

    # More patterns (e.g., "July 28, 2025")
    try:
        return datetime.strptime(text.strip(), "%B %d, %Y").replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    logging.warning(f"No date parsed from: {text}")
    return None