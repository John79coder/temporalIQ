from flask import Blueprint, request, jsonify, g
from datetime import datetime, timedelta
from app.analytics.services.event_tracker import EventTracker
from app.analytics.services.metrics_aggregator import MetricsAggregator
from app.analytics.models.schemas import (
    UserEventIn, UserEventOut, MetricsSummary,
    EventAggregateOut
)
from app.utils.endpoint_utils import verify_jwt
from app.utils.exceptions import DataValidationError, format_error_response
from app.extensions import db

bp = Blueprint('analytics', __name__, url_prefix='/analytics')

# Initialize services
event_tracker = EventTracker()
metrics_aggregator = MetricsAggregator()


@bp.route('/events', methods=['POST'])
@verify_jwt
def track_event():
    """Track a user event"""
    try:
        data = request.get_json()

        # Validate input
        event_data = UserEventIn(**data)

        # Ensure user can only track their own events
        if event_data.user_id != g.current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        # Track the event
        event_tracker.track(
            user_id=event_data.user_id,
            event_name=event_data.event_name,
            properties=event_data.properties,
            timestamp=event_data.timestamp
        )

        return jsonify({"status": "tracked"}), 201

    except DataValidationError as e:
        error_response, status = format_error_response(e, 400)
        return jsonify(error_response), status
    except Exception as e:
        error_response, status = format_error_response(e, 500)
        return jsonify(error_response), status


@bp.route('/events/batch', methods=['POST'])
@verify_jwt
def track_batch_events():
    """Track multiple events at once"""
    try:
        data = request.get_json()
        events = data.get('events', [])

        if not events or len(events) > 100:
            return jsonify({"error": "Invalid batch size (1-100 events)"}), 400

        tracked = 0
        for event_data in events:
            try:
                event = UserEventIn(**event_data)

                # Ensure user can only track their own events
                if event.user_id != g.current_user.id:
                    continue

                event_tracker.track(
                    user_id=event.user_id,
                    event_name=event.event_name,
                    properties=event.properties,
                    timestamp=event.timestamp
                )
                tracked += 1

            except Exception:
                continue  # Skip invalid events

        # Flush the buffer
        event_tracker.flush()

        return jsonify({
            "status": "tracked",
            "events_tracked": tracked
        }), 201

    except Exception as e:
        error_response, status = format_error_response(e, 500)
        return jsonify(error_response), status


@bp.route('/metrics/<int:user_id>', methods=['GET'])
@verify_jwt
def get_user_metrics(user_id: int):
    """Get metrics for a user"""
    try:
        # Ensure user can only access their own metrics
        if user_id != g.current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        # Get query parameters
        days = request.args.get('days', 30, type=int)

        # Get metrics
        metrics = event_tracker.get_user_metrics(user_id, days)

        return jsonify(metrics), 200

    except Exception as e:
        error_response, status = format_error_response(e, 500)
        return jsonify(error_response), status


@bp.route('/metrics/<int:user_id>/summary', methods=['GET'])
@verify_jwt
def get_metrics_summary(user_id: int):
    """Get aggregated metrics summary"""
    try:
        # Ensure user can only access their own metrics
        if user_id != g.current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        # Get date range from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not start_date:
            start_date = datetime.utcnow().date() - timedelta(days=30)
        else:
            start_date = datetime.fromisoformat(start_date).date()

        if not end_date:
            end_date = datetime.utcnow().date()
        else:
            end_date = datetime.fromisoformat(end_date).date()

        # Get summary
        summary = metrics_aggregator.get_user_metrics_summary(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )

        return jsonify(summary), 200

    except Exception as e:
        error_response, status = format_error_response(e, 500)
        return jsonify(error_response), status


@bp.route('/events/<int:user_id>', methods=['GET'])
@verify_jwt
def get_user_events(user_id: int):
    """Get raw events for a user"""
    try:
        # Ensure user can only access their own events
        if user_id != g.current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        # Get query parameters
        limit = min(request.args.get('limit', 100, type=int), 1000)
        event_name = request.args.get('event_name')

        # Get events from the repository
        from app.analytics.repositories.event_repository import EventRepository
        repo = EventRepository()

        events = repo.get_user_events(
            db=db.session,
            user_id=user_id,
            event_names=[event_name] if event_name else None,
            limit=limit
        )

        # Convert to schema
        events_out = [
            UserEventOut.from_orm(event).dict()
            for event in events
        ]

        return jsonify(events_out), 200

    except Exception as e:
        error_response, status = format_error_response(e, 500)
        return jsonify(error_response), status