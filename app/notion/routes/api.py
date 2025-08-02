# app/notion/routes/api.py
from typing import Type

from flask import Blueprint, request, jsonify, g, current_app
from pydantic import ValidationError as PydanticValidationError
from app.utils.endpoint_utils import verify_jwt, csrf_protected
from app.utils.exceptions import DataValidationError, NotionError, DatabaseError, ServiceUnavailableError, AuthError, \
    format_error_response, make_handled_error_response, wrap_external_error
from app.extensions import limit, limiter
from app.notion.client.notion_client import NotionClient
from app.notion.models.schemas import NotionTokenIn, NotionTokenOut, FieldMappingIn, FieldMappingOut, TaskCandidateOut, \
    DatabaseOut

bp = Blueprint("notion", __name__, url_prefix="/notion")

def get_notion_connection(user_id: int):
    return current_app.extensions['app_context'].get_service('notion_auth_service').get_connection(g.db, user_id)

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
        error_response, status_code = format_error_response(DataValidationError(str(e)), 400)
        return make_handled_error_response(DataValidationError, error_response, status_code)

    try:
        conn = current_app.extensions['app_context'].get_service('notion_auth_service').store_access_token(g.db, data)
        current_app.extensions['app_context'].get_service('caching_service').delete(f"notion:databases:{data.user_id}")
        return jsonify(NotionTokenOut.model_validate(conn).model_dump())
    except DatabaseError as e:
        error_response, status_code = format_error_response(e, 500)
        return make_handled_error_response(DatabaseError, str(e), status_code)
    except ServiceUnavailableError as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)
    except NotionError as e:
        error_response, status_code = format_error_response(NotionError(str(e)), 401)
        return make_handled_error_response(NotionError, error_response, 500)
    except Exception as e:
        return make_handled_error_response(Type[Exception], str(e), 500)

@bp.route("/map-schema", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("5 per minute"))
def map_schema():
    try:
        data = FieldMappingIn(**request.json)
    except PydanticValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)

    if data.user_id != g.current_user.id:
        return make_handled_error_response(AuthError, "Unauthorized access", 403)

    try:
        result = current_app.extensions['app_context'].get_service('mapping_service').store_mapping(g.db, data)
        current_app.extensions['app_context'].get_service('caching_service').set(
            f"notion:mapping:{data.user_id}:{data.notion_db_id}",
            result.to_dict(),
            timeout=604800  # 7 days
        )
        for field, concept in [("title_field", "title"), ("due_date_field", "due_date"), ("duration_field", "duration")]:
            corrected = getattr(data, field)
            if corrected:
                current_app.extensions['app_context'].get_service('feedback_service').log_feedback(g.db, data.user_id, data.notion_db_id, corrected, concept)
        return jsonify(FieldMappingOut.model_validate(result).model_dump())
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)

from flask import Response

@bp.route("/generate-candidates", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def generate() -> Response:
    data = request.json
    database_id = data.get("database_id")

    if not database_id:
        return make_handled_error_response(DataValidationError, "Missing database_id", 400)

    try:
        conn = get_notion_connection(g.current_user.id)
        if not conn:
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
                schema_cache_key,
                schema,
                timeout=604800
            )

        rows_cache_key = f"notion:rows:{database_id}"
        rows = current_app.extensions['app_context'].get_service('caching_service').get(rows_cache_key)

        if not rows:
            try:
                rows = client().fetch_rows(token, database_id)
            except NotionError as e:
                return make_handled_error_response(NotionError, f"Failed to fetch Notion rows: {str(e)}", 400)

            current_app.extensions['app_context'].get_service('caching_service').set(
                rows_cache_key,
                rows,
                timeout=3600
            )

        task_candidate_data = current_app.extensions['app_context'].get_service('mapping_engine').generate_candidates(
            {"schema": schema, "rows": rows}, g.db, g.current_user.id, database_id
        )

        task_candidates = current_app.extensions['app_context'].get_service('mapping_service').save_task_candidates(g.db, task_candidate_data)

        return jsonify([
            TaskCandidateOut.model_validate(c).model_dump(mode="json")
            for c in task_candidates
        ])
    except NotionError as e:
        return make_handled_error_response(NotionError, str(e), 400)
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except DataValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except ServiceUnavailableError as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)
    except Exception as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)

@bp.route("/databases", methods=["GET"])
@verify_jwt
@limiter.limit(limit("5 per minute"))
def list_databases():
    conn = get_notion_connection(g.current_user.id)
    if not conn:
        return make_handled_error_response(NotionError, "No Notion connection found", 500)

    try:
        cache_key = f"notion:databases:{g.current_user.id}"
        databases = current_app.extensions['app_context'].get_service('caching_service').get(cache_key)
        if not databases:
            try:
                databases = client().list_databases(conn.access_token)
            except Exception as e:
                return make_handled_error_response(NotionError, "Failed to list Notion databases", 500)

            current_app.extensions['app_context'].get_service('caching_service').set(
                cache_key,
                databases,
                timeout=86400  # 1 day
            )

        return jsonify([
            DatabaseOut(
                id=entry["id"],
                title=entry.get("title", [{}])[0].get("plain_text", "Untitled")
            ).model_dump()
            for entry in databases
        ])

    except NotionError as e:
        return make_handled_error_response(NotionError, str(e), 500)
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, "Database error", 500)

@bp.route("/refresh-token", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("3 per minute"))
def refresh_token():
    try:
        conn = current_app.extensions['app_context'].get_service('notion_auth_service').refresh_token(g.db, g.current_user.id)
        if not conn:
            return make_handled_error_response(NotionError, "Token refresh failed", 400)

        current_app.extensions['app_context'].get_service('caching_service').set(
            f"notion:connection:{g.current_user.id}",
            conn.to_dict(),
            timeout=86400,  # 1 day
            encrypt=True
        )

        current_app.extensions['app_context'].get_service('caching_service').delete(f"notion:databases:{g.current_user.id}")
        return jsonify(NotionTokenOut.model_validate(conn).model_dump())

    except (DatabaseError, ServiceUnavailableError, NotionError) as e:
        return make_handled_error_response(type(e), str(e), 500)
    except Exception as e:
        return make_handled_error_response(Type[Exception], str(e), 500)

@bp.route("/preview-mapping", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def preview_mapping():
    database_id = request.json.get("database_id")
    if not database_id:
        return make_handled_error_response(DataValidationError, "Missing database_id", 400)

    conn = get_notion_connection(g.current_user.id)
    if not conn:
        return make_handled_error_response(NotionError, "No Notion connection found", 404)

    try:
        schema_cache_key = f"notion:schema:{database_id}"
        schema = current_app.extensions['app_context'].get_service('caching_service').get(schema_cache_key)

        if not schema:
            try:
                schema = client().fetch_schema(conn.access_token, database_id)
            except Exception as e:
                raise wrap_external_error(e, NotionError, "Failed to fetch Notion schema")
            current_app.extensions['app_context'].get_service('caching_service').set(
                schema_cache_key,
                schema,
                timeout=604800  # 7 days
            )

        matches = current_app.extensions['app_context'].get_service('mapping_engine').preview_field_matches(schema, g.db, g.current_user.id)

        return jsonify([
            {
                "notion_field": m.notion_field,
                "matched_concept": m.matched_concept,
                "confidence": m.confidence,
                "rationale": m.rationale
            } for m in matches
        ])

    except NotionError as e:
        return jsonify(format_error_response(e, 500))
    except DatabaseError as e:
        return jsonify(format_error_response(e, 500))
    except Exception as e:
        return jsonify(format_error_response(e, 500))

# NEW: Added endpoint for page-based candidate generation, mirroring database flow but for pages
@bp.route("/pages/generate-candidates", methods=["POST"])
@verify_jwt
@csrf_protected
@limiter.limit(limit("2 per minute"))
def generate_from_page() -> Response:
    data = request.json
    page_id = data.get("page_id")
    if not page_id:
        return make_handled_error_response(DataValidationError, "Missing page_id", 400)

    try:
        conn = get_notion_connection(g.current_user.id)
        if not conn:
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
                blocks_cache_key,
                blocks,
                timeout=3600
            )

        candidates = current_app.extensions['app_context'].get_service('page_extraction_engine').generate_candidates(
            blocks, g.db, g.current_user.id, page_id
        )

        current_app.extensions['app_context'].get_service('mapping_service').save_task_candidates(g.db, candidates)

        return jsonify([
            TaskCandidateOut.model_validate(c).model_dump(mode="json")
            for c in candidates
        ])
    except NotionError as e:
        return make_handled_error_response(NotionError, str(e), 400)
    except DatabaseError as e:
        return make_handled_error_response(DatabaseError, str(e), 500)
    except DataValidationError as e:
        return make_handled_error_response(DataValidationError, str(e), 400)
    except ServiceUnavailableError as e:
        return make_handled_error_response(ServiceUnavailableError, str(e), 500)