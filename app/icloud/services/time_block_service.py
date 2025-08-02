# app/icloud/services/time_block_service.py
from typing import List
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.icloud.models.schemas import TimeBlock
from app.utils.exceptions import DataValidationError
from app.utils.caching import ICacheService
from app.icloud.services.interfaces import ITimeBlockService, ICalDAVClientManager


class TimeBlockService(ITimeBlockService):
    def __init__(self, caching_service: ICacheService, client_manager: 'ICalDAVClientManager'):
        self.caching_service = caching_service
        self.client_manager = client_manager

    def get_available_time_blocks(
        self,
        user_id: int,
        db: Session,
        calendar_id: str,
        start_date: datetime,
        end_date: datetime,
        earliest_time: str,
        latest_time: str
    ) -> List[TimeBlock]:

        cache_key = f"icloud:time_blocks:{user_id}:{calendar_id}:{start_date.isoformat()}:{end_date.isoformat()}"
        cached_blocks = self.caching_service.get(cache_key)
        if cached_blocks:
            return [TimeBlock(**block) for block in cached_blocks]

        if earliest_time >= latest_time:
            raise DataValidationError("earliest_time must be before latest_time")

        client = self.client_manager.get_caldav_client_for_user(db, user_id)
        events = client.fetch_events(calendar_id, start_date, end_date)

        # Parse earliest and latest times
        earliest_hour, earliest_minute = map(int, earliest_time.split(":"))
        latest_hour, latest_minute = map(int, latest_time.split(":"))
        blocks = []
        current_date = start_date
        while current_date <= end_date:
            day_start = current_date.replace(hour=earliest_hour, minute=earliest_minute, second=0, microsecond=0)
            day_end = current_date.replace(hour=latest_hour, minute=latest_minute, second=0, microsecond=0)
            current_time = day_start
            while current_time < day_end:
                block_end = current_time + timedelta(minutes=30)  # Default block size
                if not any(
                    event.start <= block_end and event.end > current_time
                    for event in events
                ):
                    blocks.append(TimeBlock(start=current_time, end=block_end))
                current_time += timedelta(minutes=30)
            current_date += timedelta(days=1)

        self.caching_service.set(
            cache_key,
            [block.model_dump() for block in blocks],
            timeout=3600  # 1 hour
        )

        return blocks