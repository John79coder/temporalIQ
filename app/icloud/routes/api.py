# app/icloud/routes/api.py
from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError

from app import limiter
from app.extensions import limit
from app.icloud.models.schemas import (
    iCloudConnectIn,
    iCloudConnectOut,
    CalendarListOut,
    EventListOut,
    EventCreateIn,
    EventCreateOut,
    AvailableTimeBlocksIn,
    AvailableTimeBlocksOut,
    ScheduleBlocksIn,
    ScheduleBlocksOut
)
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, CalendarError, DatabaseError, \
    ServiceUnavailableError, make_handled_error_response
from app.utils.time_zone import TimeZone

bp = Blueprint("icloud", __name__, url_prefix="/icloud")


@bp.route("/connect", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def connect_icloud():
    try:
        data = iCloudConnectIn(**request.get_json())
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        current_app.extensions['app_context'].get_service('client_manager').connect_to_icloud(g.db, g.current_user.id,
                                                                                              data.app_password)
        return jsonify(iCloudConnectOut(message="iCloud connection saved.").model_dump()), 200
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 404 if "No iCloud connection" in str(e) else 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/calendars", methods=["GET"])
@verify_jwt
@limiter.limit(limit("30 per minute"))
def list_calendars():
    try:
        calendars = current_app.extensions['app_context'].get_service('event_service').list_user_calendars(
            g.current_user.id, g.db)
        return jsonify(CalendarListOut(calendars=calendars).model_dump()), 200
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/events", methods=["GET"])
@verify_jwt
@limiter.limit(limit("60 per minute"))
def get_events():
    try:
        calendar_id = request.args.get("calendar_id")
        start = request.args.get("start")
        end = request.args.get("end")
        if not all([calendar_id, start, end]):
            return make_handled_error_response(DataValidationError,
                                               "Missing required parameters: calendar_id, start, end", 400)
        start_iso = TimeZone.parse_utc_datetime("start", start)
        end_iso = TimeZone.parse_utc_datetime("end", end)
        events = current_app.extensions['app_context'].get_service('event_service').fetch_user_events(g.current_user.id,
                                                                                                      g.db, calendar_id,
                                                                                                      start_iso,
                                                                                                      end_iso)
        return jsonify(EventListOut(events=events).model_dump()), 200
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 500)
    except (DatabaseError, ServiceUnavailableError, DataValidationError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/events", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("20 per minute"))
def create_event():
    # NEW: Check calendar write capability and quota
    entitlements = current_app.extensions['app_context'].get_service('entitlements_service')

    if not entitlements.has_capability(g.db, g.current_user.id, 'calendar_write'):
        return jsonify({
            "error": "capability_required",
            "message": "Calendar writes require a paid subscription",
            "upgrade_url": "/billing/upgrade?feature=calendar_write",
            "recommended_tier": "starter"
        }), 403

    quota_check = entitlements.check_quota(g.db, g.current_user.id, 'calendar_writes', 1)
    if not quota_check.allowed:
        return jsonify({
            "error": "quota_exceeded",
            "message": f"Monthly calendar write limit reached ({quota_check.limit} events)",
            "remaining": quota_check.remaining,
            "reset_date": quota_check.reset_date.isoformat(),
            "upgrade_options": quota_check.upgrade_options,
            "credit_pack_url": "/billing/credits?type=calendar_writes" if quota_check.credit_pack_available else None
        }), 429

    try:
        data = EventCreateIn(**request.get_json())
        current_app.extensions['app_context'].get_service('event_service').write_scheduled_event(
            g.current_user.id, g.db, data.calendar_id, data.event
        )

        # NEW: Increment usage after successful writing
        success, error = entitlements.increment_usage(g.db, g.current_user.id, 'calendar_writes', 1)
        if not success:
            # Log but don't fail the request since write already succeeded
            current_app.extensions['app_context'].get_service('logging_service').error(
                f"Failed to increment calendar write usage: {error}",
                user_id=g.current_user.id
            )

        return jsonify(EventCreateOut(message="Event written to iCloud.").model_dump()), 200
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/update", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def update_icloud_connection():
    try:
        data = iCloudConnectIn(**request.get_json())
        current_app.extensions['app_context'].get_service('client_manager').update_connection(g.db, g.current_user.id,
                                                                                              data.app_password)
        return jsonify(iCloudConnectOut(message="iCloud connection updated.").model_dump()), 200
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/available", methods=["GET"])
@verify_jwt
@limiter.limit(limit("30 per minute"))
def get_available_time_blocks():
    try:
        calendar_id = request.args.get("calendar_id")
        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        earliest_time = request.args.get("earliest_time")
        latest_time = request.args.get("latest_time")
        if earliest_time >= latest_time:
            return make_handled_error_response(DataValidationError, "earliest_time must be before latest_time", 400)
        data = AvailableTimeBlocksIn(
            calendar_id=calendar_id,
            start_date=TimeZone.parse_utc_datetime("start_date", start_date),
            end_date=TimeZone.parse_utc_datetime("end_date", end_date),
            earliest_time=earliest_time,
            latest_time=latest_time
        )
        time_blocks = current_app.extensions['app_context'].get_service('time_block_service').get_available_time_blocks(
            g.current_user.id,
            g.db,
            data.calendar_id,
            data.start_date,
            data.end_date,
            data.earliest_time,
            data.latest_time
        )
        return jsonify(AvailableTimeBlocksOut(time_blocks=time_blocks).model_dump()), 200
    except (PydanticValidationError, ValueError, DataValidationError) as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 400 if "No iCloud connection" in str(e) else 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)


@bp.route("/schedule", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("20 per minute"))
def schedule_blocks():

    entitlements = current_app.extensions['app_context'].get_service('entitlements_service')

    if not entitlements.has_capability(g.db, g.current_user.id, 'calendar_write'):
        return jsonify({
            "error": "capability_required",
            "message": "Calendar writes require a paid subscription",
            "upgrade_url": "/billing/upgrade?feature=calendar_write",
            "recommended_tier": "starter"
        }), 403

    try:
        data = ScheduleBlocksIn(**request.get_json())
        event_count = len(data.events)

        quota_check = entitlements.check_quota(g.db, g.current_user.id, 'calendar_writes', event_count)
        if not quota_check.allowed:
            return jsonify({
                "error": "quota_exceeded",
                "message": f"Not enough quota to write {event_count} events (remaining: {quota_check.remaining})",
                "remaining": quota_check.remaining,
                "reset_date": quota_check.reset_date.isoformat(),
                "upgrade_options": quota_check.upgrade_options,
                "credit_pack_url": "/billing/credits?type=calendar_writes" if quota_check.credit_pack_available else None
            }), 429

        current_app.extensions['app_context'].get_service('event_service').write_scheduled_blocks(
            g.current_user.id, g.db, data.calendar_id, data.events
        )

        # NEW: Increment usage
        success, error = entitlements.increment_usage(g.db, g.current_user.id, 'calendar_writes', event_count)
        if not success:
            current_app.extensions['app_context'].get_service('logging_service').error(
                f"Failed to increment calendar write usage: {error}",
                user_id=g.current_user.id
            )

        return jsonify(ScheduleBlocksOut(message="Events written to iCloud.").model_dump()), 200
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except CalendarError as e:
        return make_handled_error_response(CalendarError, str(e), 500)
    except (DatabaseError, ServiceUnavailableError) as e:
        return make_handled_error_response(e, str(e), 500)