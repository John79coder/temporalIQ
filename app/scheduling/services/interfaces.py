# app/scheduling/services/interfaces.py
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from sqlalchemy.orm import Session

from app.icloud.models.schemas import TimeBlock as ICloudTimeBlock
from app.scheduling.models.entities import Task, TimeBlock


class IFreeTimeFinder(ABC):
    @abstractmethod
    def find_free_slots(
            self,
            user_id: int,
            db: Session,
            calendar_id: str,
            start_date: datetime,
            end_date: datetime,
            earliest_time: str,
            latest_time: str
    ) -> List[ICloudTimeBlock]:
        pass


class ITaskPrioritizer(ABC):
    @abstractmethod
    def prioritize_tasks(self, tasks: List[Task], db: Session = None) -> List[Task]:
        pass


class ITimeBlockGenerator(ABC):
    @abstractmethod
    def generate_time_blocks(
            self,
            user_id: int,
            db: Session,
            notion_db_id: str,
            calendar_id: str,
            start_date: datetime,
            end_date: datetime,
            earliest_time: str,
            latest_time: str
    ) -> List[TimeBlock]:
        pass
