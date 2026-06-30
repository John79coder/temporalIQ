# app/notion/routes/api.py
import logging
import uuid
from typing import Type
from urllib.parse import urlencode

from flask import Blueprint, request, jsonify, g, current_app, Response, redirect
from pydantic import ValidationError as PydanticValidationError

from app.extensions import limit, limiter
from app.notion.auth.service import NotionAuthService
from app.notion.client.notion_client import NotionClient
from app.notion.models.schemas import NotionTokenIn, NotionTokenOut, FieldMappingIn, FieldMappingOut, TaskCandidateOut, \
    DatabaseOut
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, NotionError, DatabaseError, ServiceUnavailableError, AuthError, \
    make_handled_error_response, InternalError
from config import Config

logger = logging.getLogger(__name__)

bp = Blueprint("notion", __name__, url_prefix="/notion")


def get_notion_auth_service(user_id: int) -> NotionAuthService:
    return current_app.extensions['app_context'].get_service('notion_auth_service')


def client() -> NotionClient:
    if not hasattr(g, 'notion_client'):
        encryptor = current_app.extensions['app_context'].get_service('encryptor')
        g.notion_client = NotionClient(encryptor)
    return g.notion_client


@bp.route("/connect", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("3 per minute"))
def connect():
    try:
        data = NotionTokenIn(**request.json)
    except PydanticValidationError as e:
        logger.warning("Invalid payload on /connect for user %s: %s", getattr(g, 'current_user', {id: '?'}).id, e)
        return make_handled_error_response(DataValidationError, str(e), 400)

    try:
        conn = current_app.extensions['app_context'].get_service('notion_auth_service').store_access_token(g.db, data)
        logger.info("store_access_token returned")
        current_app.extensions['app_context'].get_service('caching_service').delete(f"notion:databases:{data.user_id}")
        logger.info("Notion token stored for user %s", data.user_id)
        return jsonify(NotionTokenOut.model_validate(conn).model_dump())

    except DatabaseError as e:
        logger.error("Database error storing Notion token for user %s: %s", data.user_id, e)
        return make_handled_error_response(DatabaseError, str(e), 500)
    except ServiceUnavailableError as e:
        logger.error("Service unavailable storing Notion token for user %s: %s", data.user_id, e)
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)
    except NotionError as e:
        logger.warning("Notion error storing token for user %s: %s", data.user_id, e)
        return make_handled_error_response(NotionError, str(e), 400)
    except Exception as e:
        logger.exception("Unexpected error on /connect for user %s", data.user_id)
        return make_handled_error_response(InternalError, str(e), 500)


@bp.route("/map-schema", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def map_schema():
    try:
        data = FieldMappingIn(**request.json)
    except PydanticValidationError as e:
        logger.warning("Invalid payload on /map-schema: %s", e)
        return make_handled_error_response(DataValidationError, str(e), 400)

    if data.user_id != g.current_user.id:
        logger.warning(
            "Auth mismatch on /map-schema: token user %s attempted to map schema for user %s",
            g.current_user.id, data.user_id
        )
        return make_handled_error_response(AuthError, "Unauthorized access", 403)

    try:
        result = current_app.extensions['app_context'].get_service('mapping_service').store_mapping(g.db, data)
        current_app.extensions['app_context'].get_service('caching_service').set(
            f"notion:mapping:{data.user_id}:{data.notion_db_id}",
            result.to_dict(),
            timeout=604800  # 7 days
        )

        for field, concept in [("title_field", "title"), ("due_date_field", "due_date"),
                                ("duration_field", "duration")]:
            corrected = getattr(data, field)
            if corrected:
                current_app.extensions['app_context'].get_service('feedback_service').log_feedback(
                    g.db, data.user_id, data.notion_db_id, corrected, concept
                )

        logger.info("Schema mapping stored for user %s, database %s", data.user_id, data.notion_db_id)
        return jsonify(FieldMappingOut.model_validate(result).model_dump())

    except DatabaseError as e:
        logger.error("Database error storing schema mapping for user %s: %s", data.user_id, e)
        return make_handled_error_response(DatabaseError, str(e), 500)


@bp.route("/generate-candidates", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def generate() -> Response:
    data = request.json
    database_id = data.get("database_id")
    user_id = g.current_user.id

    if not database_id:
        logger.warning("Missing database_id on /generate-candidates for user %s", user_id)
        return make_handled_error_response(DataValidationError, "Missing database_id", 400)

    try:
        conn = get_notion_auth_service(user_id).get_connection(g.db, user_id)
        if not conn:
            logger.warning("No Notion connection found for user %s", user_id)
            return make_handled_error_response(NotionError, "No Notion connection found", 404)

        token = conn.access_token
        schema_cache_key = f"notion:schema:{database_id}"
        schema = current_app.extensions['app_context'].get_service('caching_service').get(schema_cache_key)

        if not schema:
            try:
                schema = client().fetch_schema(token, database_id)
            except NotionError as e:
                return make_handled_error_response(NotionError, f"Failed to fetch Notion schema: {str(e)}", 400)

            current_app.extensions['app_context'].get_service('caching_service').set(
                schema_cache_key, schema, timeout=604800
            )

        rows_cache_key = f"notion:rows:{database_id}"
        rows = current_app.extensions['app_context'].get_service('caching_service').get(rows_cache_key)

        if not rows:
            try:
                rows = client().fetch_rows(token, database_id)
            except NotionError as e:
                return make_handled_error_response(NotionError, f"Failed to fetch Notion rows: {str(e)}", 400)

            current_app.extensions['app_context'].get_service('caching_service').set(
                rows_cache_key, rows, timeout=3600
            )

        task_candidate_data = current_app.extensions['app_context'].get_service('mapping_engine').generate_candidates(
            {"schema": schema, "rows": rows}, g.db, user_id, database_id
        )

        task_candidates = current_app.extensions['app_context'].get_service('mapping_service').save_task_candidates(
            g.db, task_candidate_data
        )

        logger.info(
            "Generated %d candidates for user %s from database %s",
            len(task_candidates), user_id, database_id
        )
        return jsonify([
            TaskCandidateOut.model_validate(c).model_dump(mode="json")
            for c in task_candidates
        ])

    except NotionError as e:
        logger.warning("Notion error generating candidates for user %s: %s", user_id, e)
        return make_handled_error_response(NotionError, str(e), 400)
    except DatabaseError as e:
        logger.error("Database error generating candidates for user %s: %s", user_id, e)
        return make_handled_error_response(DatabaseError, str(e), 500)
    except DataValidationError as e:
        logger.warning("Validation error generating candidates for user %s: %s", user_id, e)
        return make_handled_error_response(DataValidationError, str(e), 400)
    except ServiceUnavailableError as e:
        logger.error("Service unavailable generating candidates for user %s: %s", user_id, e)
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)
    except Exception:
        logger.exception("Unexpected error generating candidates for user %s, database %s", user_id, database_id)
        return make_handled_error_response(ServiceUnavailableError, "Unexpected error", 500)


@bp.route("/databases", methods=["GET"])
@verify_jwt
@limiter.limit(limit("5 per minute"))
def list_databases():
    user_id = g.current_user.id
    conn = get_notion_auth_service(user_id).get_connection(g.db, user_id)

    if not conn:
        logger.warning("No Notion connection found for user %s on /databases", user_id)
        return make_handled_error_response(NotionError, "No Notion connection found", 500)

    try:
        cache_key = f"notion:databases:{user_id}"
        databases = current_app.extensions['app_context'].get_service('caching_service').get(cache_key)

        if not databases:
            try:
                databases = client().list_databases(conn.access_token)
            except Exception:
                logger.exception("Failed to list Notion databases for user %s", user_id)
                return make_handled_error_response(NotionError, "Failed to list Notion databases", 500)

            current_app.extensions['app_context'].get_service('caching_service').set(
                cache_key, databases, timeout=86400
            )

        return jsonify([
            DatabaseOut(
                id=entry["id"],
                title=entry.get("title", [{}])[0].get("plain_text", "Untitled")
            ).model_dump()
            for entry in databases
        ])

    except NotionError as e:
        logger.warning("Notion error listing databases for user %s: %s", user_id, e)
        return make_handled_error_response(NotionError, str(e), 500)
    except DatabaseError as e:
        logger.error("Database error listing databases for user %s: %s", user_id, e)
        return make_handled_error_response(DatabaseError, "Database error", 500)


@bp.route("/refresh-token", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("3 per minute"))
def refresh_token():
    user_id = g.current_user.id
    try:
        conn = current_app.extensions['app_context'].get_service('notion_auth_service').refresh_token(g.db, user_id)
        if not conn:
            logger.warning("Token refresh returned no connection for user %s", user_id)
            return make_handled_error_response(NotionError, "Token refresh failed", 400)

        current_app.extensions['app_context'].get_service('caching_service').set(
            f"notion:connection:{user_id}",
            conn.to_dict(),
            timeout=86400,
            encrypt=True
        )
        current_app.extensions['app_context'].get_service('caching_service').delete(
            f"notion:databases:{user_id}"
        )
        logger.info("Notion token refreshed for user %s", user_id)
        return jsonify(NotionTokenOut.model_validate(conn).model_dump())

    except (DatabaseError, ServiceUnavailableError, NotionError) as e:
        logger.error("Error refreshing Notion token for user %s: %s", user_id, e)
        return make_handled_error_response(type(e), str(e), 500)
    except Exception:
        logger.exception("Unexpected error refreshing Notion token for user %s", user_id)
        return make_handled_error_response(InternalError, "Unexpected error", 500)


@bp.route("/preview-mapping", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def preview_mapping():
    user_id = g.current_user.id
    database_id = request.json.get("database_id")

    if not database_id:
        logger.warning("Missing database_id on /preview-mapping for user %s", user_id)
        return make_handled_error_response(DataValidationError, "Missing database_id", 400)

    conn = get_notion_auth_service(user_id).get_connection(g.db, user_id)
    if not conn:
        logger.warning("No Notion connection found for user %s on /preview-mapping", user_id)
        return make_handled_error_response(NotionError, "No Notion connection found", 404)

    try:
        schema_cache_key = f"notion:schema:{database_id}"
        schema = current_app.extensions['app_context'].get_service('caching_service').get(schema_cache_key)

        if not schema:
            try:
                schema = client().fetch_schema(conn.access_token, database_id)
            except NotionError as e:
                return make_handled_error_response(NotionError, str(e), 400)

            current_app.extensions['app_context'].get_service('caching_service').set(
                schema_cache_key, schema, timeout=604800
            )

        matches = (current_app.extensions['app_context']
                   .get_service('mapping_engine')
                   .preview_field_matches(schema, g.db, user_id))

        logger.info(
            "Preview mapping returned %d field matches for user %s, database %s",
            len(matches), user_id, database_id
        )
        return jsonify([
            {
                "notion_field": m.notion_field,
                "matched_concept": m.matched_concept,
                "confidence": m.confidence,
                "rationale": m.rationale
            } for m in matches
        ])

    except NotionError as e:
        logger.warning("Notion error on /preview-mapping for user %s: %s", user_id, e)
        return make_handled_error_response(NotionError, str(e), 500)
    except DatabaseError as e:
        logger.error("Database error on /preview-mapping for user %s: %s", user_id, e)
        return make_handled_error_response(DatabaseError, str(e), 500)
    except Exception:
        logger.exception("Unexpected error on /preview-mapping for user %s, database %s", user_id, database_id)
        return make_handled_error_response(InternalError, "Unexpected error", 500)


@bp.route("/pages/generate-candidates", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def generate_from_page() -> Response:
    data = request.json
    page_id = data.get("page_id")
    user_id = g.current_user.id

    if not page_id:
        logger.warning("Missing page_id on /pages/generate-candidates for user %s", user_id)
        return make_handled_error_response(DataValidationError, "Missing page_id", 400)

    force_single_task = data.get("force_single_task", False)

    try:
        conn = get_notion_auth_service(user_id).get_connection(g.db, user_id)
        if not conn:
            logger.warning("No Notion connection found for user %s on /pages/generate-candidates", user_id)
            return make_handled_error_response(NotionError, "No Notion connection found", 404)

        token = conn.access_token
        blocks_cache_key = f"notion:page_blocks:{page_id}"
        blocks = current_app.extensions['app_context'].get_service('caching_service').get(blocks_cache_key)

        if not blocks:
            try:
                blocks = client().fetch_page_blocks(token, page_id)
            except NotionError as e:
                return make_handled_error_response(NotionError, f"Failed to fetch Notion page blocks: {str(e)}", 400)

            current_app.extensions['app_context'].get_service('caching_service').set(
                blocks_cache_key, blocks, timeout=3600
            )

        candidates = current_app.extensions['app_context'].get_service('page_extraction_engine').generate_candidates(
            blocks, g.db, user_id, page_id, force_single_task
        )

        current_app.extensions['app_context'].get_service('mapping_service').save_task_candidates(g.db, candidates)

        logger.info(
            "Generated %d page candidates for user %s from page %s (force_single_task=%s)",
            len(candidates), user_id, page_id, force_single_task
        )
        return jsonify([
            TaskCandidateOut.model_validate(c).model_dump(mode="json")
            for c in candidates
        ])



    except NotionError as e:
        logger.warning("Notion error on /pages/generate-candidates for user %s: %s", user_id, e)
        return make_handled_error_response(NotionError, str(e), 400)

    except DatabaseError as e:
        logger.error("Database error on /pages/generate-candidates for user %s: %s", user_id, e)
        return make_handled_error_response(DatabaseError, str(e), 500)

    except DataValidationError as e:
        logger.warning("Validation error on /pages/generate-candidates for user %s: %s", user_id, e)
        return make_handled_error_response(DataValidationError, str(e), 400)

    except ServiceUnavailableError as e:
        logger.error("Service unavailable on /pages/generate-candidates for user %s: %s", user_id, e)
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)

    except Exception:
        logger.exception("Unexpected error on /pages/generate-candidates for user %s, page %s", user_id, page_id)
        return make_handled_error_response(InternalError, "Unexpected error", 500)


@bp.route("/oauth/callback", methods=["GET"])
def notion_callback():
    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        return f"Notion error: {error}", 400

    if not code:
        return "No code provided", 400

    state = request.args.get("state")
    if not state:
        logger.warning("Missing state parameter on /callback")
        return "Invalid request", 400

    try:
        user_id = current_app.extensions['app_context'].get_service('oauth_state_service').resolve_state(state)
        if not user_id:
            logger.warning("Invalid or expired state on /callback: %s", state)
            return "Invalid request", 400

        token_data = NotionTokenIn(
            user_id=int(user_id),
            code=code,
            redirect_uri=Config.NOTION_REDIRECT_URI
        )

        current_app.extensions['app_context'].get_service('notion_auth_service') \
            .store_access_token(g.db, token_data)

        logger.info("store_access_token returned")

        g.db.commit()

        logger.info("Commit completed")

        logger.info("Redirecting")

        return redirect("http://localhost:3000/onboarding?notion_connected=true")


    except Exception:
        g.db.rollback()
        logger.exception("OAuth callback failed for state %s", state)
        return "Authentication failed", 500


@bp.route("/oauth/start", methods=["GET"])
@verify_jwt
def oauth_start():
    state = str(uuid.uuid4())

    current_app.extensions["app_context"] \
        .get_service("oauth_state_service") \
        .store_state(state, g.current_user.id)

    logger.info(
        "client_id=%r redirect_uri=%r",
        Config.NOTION_CLIENT_ID,
        Config.NOTION_REDIRECT_URI,
    )

    params = urlencode({
        "client_id": Config.NOTION_CLIENT_ID,
        "response_type": "code",
        "owner": "user",
        "redirect_uri": Config.NOTION_REDIRECT_URI,
        "state": state,
    })

    return jsonify({
        "authorize_url": f"https://api.notion.com/v1/oauth/authorize?{params}"
    })


@bp.route("/connection", methods=["GET"])
@verify_jwt
def get_notion_connection():

    notion_auth_service = get_notion_auth_service(g.current_user.id)

    notion_connection = notion_auth_service.get_connection(g.db, g.current_user.id)

    if notion_connection is None:
        logger.info(
            "No Notion connection found for user %s.",
            g.current_user.id,
        )
        return jsonify({
            "connected": False
        }), 200

    logger.info(
        "Retrieved Notion connection for user %s.",
        g.current_user.id,
    )

    return jsonify({
        "connected": True,
        "workspace_id": notion_connection.workspace_id,
        "connected_at": notion_connection.created_at
    })