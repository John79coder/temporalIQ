# app/scheduling/routes/api.py
from typing import List

from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential
from werkzeug.exceptions import BadRequest

from app.features.models.entities import AITrainingEvent
from app.features.models.schemas import SlotChoiceInput, SlotChoiceLabel, DurationLogInput, DurationLogLabel
from app.features.services.ai_data_service import AIDataService
from app.icloud.models.schemas import EventWriteRequest
from app.logging import ApplicationLogger
from app.scheduling.models.entities import Task
from app.scheduling.models.schemas import SchedulePreviewIn, TimeBlockOut, ScheduleConfirmIn, TimeBlockIn
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import AppError
from app.utils.exceptions import DataValidationError, CalendarError, DatabaseError, make_handled_error_response, \
    ServiceUnavailableError, wrap_external_error


class RollbackError(DatabaseError):
    """Raised when rollback fails for iCloud events."""
    pass


bp = Blueprint("scheduling", __name__, url_prefix="/scheduling")


@verify_jwt
@csrf_protected
@bp.route("/preview", methods=["POST"])
def preview_schedule():
    """Generate a preview of time blocks for scheduling."""
    # NEW: Check AI generation quota for time block generation
    entitlements = current_app.extensions['app_context'].get_service('entitlements_service')

    quota_check = entitlements.check_quota(g.db, g.current_user.id, 'ai_generations', 1)
    if not quota_check.allowed:
        return jsonify({
            "error": "quota_exceeded",
            "message": f"Monthly AI generation limit reached ({quota_check.limit} generations)",
            "remaining": quota_check.remaining,
            "reset_date": quota_check.reset_date.isoformat(),
            "upgrade_options": quota_check.upgrade_options,
            "credit_pack_url": "/billing/credits?type=ai_generations" if quota_check.credit_pack_available else None
        }), 429

    try:
        json_data = request.get_json()
        schedule_preview_input = SchedulePreviewIn(**json_data)
    except (BadRequest, PydanticValidationError) as e:
        logging_service = current_app.extensions['app_context'].get_service('logging_service')
        logging_service.error("Invalid input for schedule preview", user_id=None, extra={"error": str(e)})
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        time_blocks = current_app.extensions['app_context'].get_service('time_block_generator').generate_time_blocks(
            schedule_preview_input.user_id,
            g.db,
            schedule_preview_input.notion_db_id,
            schedule_preview_input.calendar_id,
            schedule_preview_input.start_date,
            schedule_preview_input.end_date,
            schedule_preview_input.earliest_time,
            schedule_preview_input.latest_time
        )

        # NEW: Increment usage after successful generation
        success, error = entitlements.increment_usage(g.db, g.current_user.id, 'ai_generations', 1)
        if not success:
            current_app.extensions['app_context'].get_service('logging_service').error(
                f"Failed to increment AI generation usage: {error}",
                user_id=g.current_user.id
            )

        return jsonify(
            {"time_blocks": [TimeBlockOut.model_validate(tb).model_dump(mode="json") for tb in time_blocks]}
        )
    except (CalendarError, DatabaseError, ServiceUnavailableError) as e:
        logging_service = current_app.extensions['app_context'].get_service('logging_service')
        logging_service.error("Failed to generate schedule preview", user_id=schedule_preview_input.user_id,
                              extra={"error": str(e)})
        return make_handled_error_response(type(e), str(e), 500)
    except Exception as e:
        logging_service = current_app.extensions['app_context'].get_service('logging_service')
        logging_service.error("Unexpected error in schedule preview", user_id=schedule_preview_input.user_id,
                              extra={"error": str(e)})
        return make_handled_error_response(AppError, str(e), 500)

@bp.route("/confirm", methods=["POST"])
@verify_jwt
@csrf_protected
def confirm_schedule():
    """Confirm and write scheduled time blocks to iCloud."""
    logging_service = current_app.extensions['app_context'].get_service('logging_service')
    try:
        json_data = request.get_json()
        data = ScheduleConfirmIn(**json_data)
    except (BadRequest, PydanticValidationError) as e:
        logging_service.error("Invalid input for schedule confirm", user_id=None, extra={"error": str(e)})
        return make_handled_error_response(DataValidationError, str(e), 400)

    event_service = current_app.extensions['app_context'].get_service('event_service')
    ai_data_service = current_app.extensions['app_context'].get_service('ai_data_service')
    uids = []
    try:
        tasks = g.db.query(Task).filter(Task.user_id == data.user_id,
                                        Task.id.in_([tb.task_id for tb in data.time_blocks if tb.task_id])).all()
        task_map = {task.id: task for task in tasks}
        uids = _write_events(g.db, data.user_id, data.calendar_id, data.time_blocks, task_map, event_service,
                             logging_service)
        _log_training_events(g.db, data.user_id, data.time_blocks, task_map, ai_data_service, logging_service)
        g.db.commit()
        return jsonify({"message": "Schedule confirmed and written to iCloud."}), 200
    except (CalendarError, DatabaseError, ServiceUnavailableError, SQLAlchemyError, ValueError) as e:
        _rollback_on_failure(g.db, data.user_id, data.calendar_id, uids, event_service, logging_service)
        logging_service.error("Failed to confirm schedule", user_id=data.user_id,
                              extra={"error": str(e), "block_count": len(data.time_blocks),
                                     "task_count": len(task_map)})
        return make_handled_error_response(type(e), str(e), 500)
    except Exception as e:
        _rollback_on_failure(g.db, data.user_id, data.calendar_id, uids, event_service, logging_service)
        logging_service.error("Unexpected error in schedule confirm", user_id=data.user_id,
                              extra={"error": str(e), "block_count": len(data.time_blocks),
                                     "task_count": len(task_map)})
        return make_handled_error_response(AppError, str(e), 500)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _delete_event_with_retry(client, calendar_id: str, uid: str, logging_service: ApplicationLogger, user_id: int):
    """Retry deleting an event from iCloud."""
    client.delete_event(calendar_id, uid)
    logging_service.info("Rollback: Deleted event", user_id=user_id, extra={"uid": uid, "calendar_id": calendar_id})


def _write_events(db: Session, user_id: int, calendar_id: str, blocks: List[TimeBlockIn], task_map: dict, event_service,
                  logging_service: ApplicationLogger) -> List[str]:
    """Write events to iCloud calendar."""
    uids = []
    for block in blocks:
        if block.task_id and block.task_id in task_map:
            task = task_map[block.task_id]
            try:
                event = EventWriteRequest(
                    title=task.title,
                    start=block.start,
                    end=block.end,
                    notes=f"Task: {task.title}",
                    uid=None
                )
                uid = event_service.write_scheduled_event(user_id, db, calendar_id, event)
                uids.append(uid)
            except (CalendarError, DatabaseError) as e:
                logging_service.error("Failed to write event", user_id=user_id, task_id=block.task_id,
                                      extra={"error": str(e)})
                raise
    return uids


def _log_training_events(db: Session, user_id: int, blocks: List[TimeBlockIn], task_map: dict,
                         ai_data_service: AIDataService, logging_service: ApplicationLogger):
    """Log slot choice and duration events to AI training data."""
    """Log slot choice and duration events to AI training data."""
    from app.scheduling.models.policies import get_urgency_float  # NEW: Import utility
    try:
        for block in blocks:
            if block.task_id and block.task_id in task_map:
                task = task_map[block.task_id]
                duration = (block.end - block.start).total_seconds() / 60
                urgency_float = get_urgency_float(task.priority)  # CHANGED: Convert to float using utility
                events = [
                    AITrainingEvent(
                        user_id=user_id,
                        task_id=task.id,
                        event_type='slot_choice',
                        input_json=SlotChoiceInput(
                            slot_start=block.start.isoformat(),
                            urgency=urgency_float,  # CHANGED: Now float
                            duration=duration
                        ).model_dump(),
                        label_json=SlotChoiceLabel(selected=True).model_dump(),
                        source='user_confirm'
                    ),
                    AITrainingEvent(
                        user_id=user_id,
                        task_id=task.id,
                        event_type='duration_log',
                        input_json=DurationLogInput(
                            num_events=len(task_map),
                            day_length_hours=current_app.extensions['app_context'].get_service(
                                'free_time_finder')._get_work_hours(db, user_id),
                            urgency=urgency_float  # CHANGED: Now float from converted priority
                        ).model_dump(),
                        label_json=DurationLogLabel(duration_minutes=duration).model_dump(),
                        source='user_confirm'
                    )
                ]
                for event in events:
                    ai_data_service.log_event(db, event)
    except SQLAlchemyError as e:
        logging_service.error("Failed to log training events", user_id=user_id,
                              task_id=block.task_id if block.task_id else None, extra={"error": str(e)})
        raise wrap_external_error(e, DatabaseError, "Failed to log training events") from e
    except ValueError as e:
        logging_service.error("Invalid training event data", user_id=user_id,
                              task_id=block.task_id if block.task_id else None, extra={"error": str(e)})
        raise wrap_external_error(e, DataValidationError, "Invalid training event data") from e


def _rollback_on_failure(db: Session, user_id: int, calendar_id: str, uids: List[str], event_service,
                         logging_service: ApplicationLogger):
    """Rollback iCloud events on failure."""
    client = event_service.client_manager.get_caldav_client_for_user(db, user_id)
    failed_rollbacks = []
    for uid in uids:
        try:
            confirm_schedule._delete_event_with_retry(client, calendar_id, uid, logging_service, user_id)
        except (CalendarError, ServiceUnavailableError) as del_e:
            logging_service.error("Rollback failed for event", user_id=user_id, extra={"error": str(del_e), "uid": uid})
            failed_rollbacks.append(uid)
    if failed_rollbacks:
        logging_service.error("Incomplete rollback, some events may persist", user_id=user_id,
                              extra={"failed_uids": failed_rollbacks})
        raise RollbackError(f"Failed to rollback all events: {failed_rollbacks}") from None
