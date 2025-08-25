# app/__init__.py
import logging as python_logging
import os
import uuid

from flask_cors import CORS

import click
from flask import Flask, g, jsonify, request
from flask.cli import with_appcontext
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_session import Session

from app.analytics.routes.api import bp as analytics_bp
from app.auth.routes.api import bp as auth_bp
from app.extensions import csrf, mail, limiter, db, cache
from app.features.routes.api import bp as features_bp
from app.icloud.routes.api import bp as icloud_bp
from app.notion.routes.api import bp as notion_bp
from app.scheduling.routes.api import bp as scheduling_bp
from app.user_preferences.routes.api import bp as user_bp
from app.entitlements.routes.api import bp as entitlements_bp
from app.utils.app_context import AppContext
from app.utils.exceptions import AuthError, format_error_response
from app.utils.service_factory import ServiceFactory

from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config["SESSION_TYPE"] = "filesystem" if config_class.TESTING else "redis"
    app.config["SESSION_REDIS"] = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    session_dir = app.config.get("SESSION_FILE_DIR")
    if session_dir:
        os.makedirs(session_dir, exist_ok=True)

    Session(app)

    # Configure CORS for frontend access
    CORS(app,
         origins=[
             "http://localhost:3000",  # Development frontend
             "http://localhost:5173",  # Vite default port
             app.config.get('FRONTEND_BASE_URL', 'http://localhost:3000')
         ],
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         expose_headers=["Content-Type", "Authorization"])

    # Configure standard Python logging (using renamed import)
    log_file = os.path.join(os.path.dirname(__file__), 'app.log')
    file_handler = python_logging.FileHandler(log_file)
    file_handler.setLevel(python_logging.DEBUG)
    file_handler.setFormatter(python_logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    stream_handler = python_logging.StreamHandler()
    stream_handler.setLevel(python_logging.DEBUG)
    stream_handler.setFormatter(python_logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    python_logging.basicConfig(
        level=python_logging.DEBUG if config_class.TESTING else python_logging.ERROR,
        handlers=[file_handler, stream_handler]
    )

    # Log to confirm initialization
    python_logging.getLogger().debug(f"Logging initialized. Writing to {log_file}")

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    python_logging.info(f"Initializing app with database URL: {db_uri}")
    if os.getenv("FLASK_ENV") == "test" and "postgresql" not in db_uri:
        raise ValueError("Non-PostgreSQL database URL detected in test environment")

    # Initialize Flask extensions
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    db.init_app(app)
    cache.init_app(app)
    JWTManager(app)
    Migrate(app, db)

    # Initialize services within the app context
    app.extensions['app_context'] = AppContext()
    with app.app_context():
        services = ServiceFactory.initialize_services(cache)
        for name, service in services.items():
            app.extensions['app_context'].set_service(name, service)

        # Register detectors
        detector_registry = services['mapping_engine'].detector_aggregator.registry
        detector_registry.initialize_default_detectors()

    # Get enhanced logging services from the service factory
    # They should already be initialized by ServiceFactory
    app_logger = app.extensions['app_context'].get_service('app_logger')
    audit_logger = app.extensions['app_context'].get_service('audit_logger')
    event_tracker = app.extensions['app_context'].get_service('event_tracker')
    metrics_aggregator = app.extensions['app_context'].get_service('metrics_aggregator')

    # Only import and initialize if services weren't found
    if not app_logger:
        from app.logging.services.application_logger import ApplicationLogger
        app_logger = ApplicationLogger()
        app.extensions['app_context'].set_service('app_logger', app_logger)

    if not audit_logger:
        from app.logging.services.audit_logger import AuditLogger
        audit_logger = AuditLogger()
        app.extensions['app_context'].set_service('audit_logger', audit_logger)

    if not event_tracker:
        from app.analytics.services.event_tracker import EventTracker
        event_tracker = EventTracker()
        app.extensions['app_context'].set_service('event_tracker', event_tracker)

    if not metrics_aggregator:
        from app.analytics.services.metrics_aggregator import MetricsAggregator
        metrics_aggregator = MetricsAggregator()
        app.extensions['app_context'].set_service('metrics_aggregator', metrics_aggregator)

    # Store logging and analytics instances in app for easy access
    app.logger_instance = app_logger
    app.audit_logger = audit_logger
    app.event_tracker = event_tracker
    app.metrics_aggregator = metrics_aggregator

    # Override Flask's default logger with our enhanced logger
    app.logger = app_logger.get_logger()

    # Add logging middleware for comprehensive request/response logging
    from app.logging.middleware import LoggingMiddleware
    app.wsgi_app = LoggingMiddleware(app.wsgi_app, app_logger)

    # Log application startup
    app_logger.info(
        "Application starting",
        environment=config_class.__name__,
        database_url=db_uri.split('@')[-1] if '@' in db_uri else "local"
    )

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(notion_bp)
    app.register_blueprint(icloud_bp)
    app.register_blueprint(scheduling_bp)
    app.register_blueprint(features_bp)
    app.register_blueprint(entitlements_bp)
    app.register_blueprint(analytics_bp)

    # Request lifecycle hooks
    @app.before_request
    def before_request():
        """Set up request context and logging"""
        # Generate unique request ID
        g.request_id = str(uuid.uuid4())

        # Set up database session
        g.db = db.session
        g.cache = {}

        # Log request (detailed logging handled by middleware)
        if hasattr(app, 'logger_instance'):
            app.logger_instance.log_request()

        # Track user activity if authenticated
        if hasattr(g, 'current_user') and g.current_user and hasattr(app, 'event_tracker'):
            app.event_tracker.track(
                user_id=g.current_user.id,
                event_name="api_request",
                properties={
                    "endpoint": request.endpoint,
                    "method": request.method
                }
            )

    @app.after_request
    def after_request(response):
        """Log response and add custom headers"""
        # Log response (detailed logging handled by middleware)
        if hasattr(app, 'logger_instance'):
            app.logger_instance.log_response(response)

        # Add request ID to response headers
        if hasattr(g, 'request_id'):
            response.headers['X-Request-ID'] = g.request_id

        # Flush analytics events if buffer is getting full
        if hasattr(app, 'event_tracker'):
            app.event_tracker.flush()

        return response

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        """Clean up database session and caches"""
        if exception and hasattr(app, 'logger_instance'):
            app.logger_instance.error("Request failed with exception", exception=exception)

        db_session = g.pop("db", None)
        if db_session is not None:
            if exception:
                db_session.rollback()
            db.session.remove()

        g.pop("cache", None)

        # Ensure analytics events are flushed
        if hasattr(app, 'event_tracker'):
            app.event_tracker.flush()

    # Error handlers
    @app.errorhandler(AuthError)
    def handle_auth_error(error):
        """Handle authentication errors with logging"""
        if hasattr(app, 'logger_instance'):
            app.logger_instance.warning(f"Authentication error: {str(error)}")

        # Log to audit log
        if hasattr(app, 'audit_logger'):
            app.audit_logger.log_security_event(
                event_type="auth_error",
                severity="warning",
                description=str(error),
                user_id=getattr(g, 'current_user', {}).get('id') if hasattr(g, 'current_user') else None
            )

        error_response, status_code = format_error_response(error, 401)
        from flask.helpers import make_response
        return make_response(jsonify(error_response), status_code)

    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle 404 errors"""
        if hasattr(app, 'logger_instance'):
            app.logger_instance.info(f"404 Not Found: {request.path}")

        error_response = {
            "type": "about:blank",
            "title": "Not Found",
            "status": 404,
            "detail": f"The requested URL {request.path} was not found on the server."
        }
        return jsonify(error_response), 404

    @app.errorhandler(500)
    def handle_internal_error(error):
        """Handle internal server errors"""
        if hasattr(app, 'logger_instance'):
            app.logger_instance.error("Internal server error", exception=error)

        # Log to audit log for security monitoring
        if hasattr(app, 'audit_logger'):
            app.audit_logger.log_security_event(
                event_type="internal_error",
                severity="error",
                description=str(error),
                user_id=getattr(g, 'current_user', {}).get('id') if hasattr(g, 'current_user') else None
            )

        error_response = {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "An internal error occurred. Please try again later."
        }
        return jsonify(error_response), 500

    # CLI Commands
    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Initialize the database (for dev/MVP environments only)."""
        try:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.info("Initializing database")
            db.create_all()
            click.echo("✅ Database initialized.")
            if hasattr(app, 'logger_instance'):
                app.logger_instance.info("Database initialized successfully")
        except Exception as e:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.error("Failed to initialize database", exception=e)
            click.echo(f"❌ Failed to initialize database: {e}")
            raise

    @app.cli.command("rotate-logs")
    @with_appcontext
    def rotate_logs():
        """Manually rotate log files"""
        try:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.info("Manual log rotation triggered")
                for handler in app.logger_instance.get_logger().handlers:
                    if hasattr(handler, 'doRollover'):
                        handler.doRollover()
            click.echo("✅ Logs rotated successfully.")
        except Exception as e:
            click.echo(f"❌ Failed to rotate logs: {e}")

    @app.cli.command("aggregate-metrics")
    @with_appcontext
    def aggregate_metrics():
        """Manually trigger metrics aggregation"""
        try:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.info("Manual metrics aggregation triggered")
            if hasattr(app, 'metrics_aggregator'):
                app.metrics_aggregator.run_aggregation()
            click.echo("✅ Metrics aggregated successfully.")
        except Exception as e:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.error("Failed to aggregate metrics", exception=e)
            click.echo(f"❌ Failed to aggregate metrics: {e}")

    # Health check endpoint
    @app.route("/health")
    def health_check():
        """Health check endpoint for monitoring"""
        try:
            # Check database connectivity
            db.session.execute("SELECT 1")

            # Check cache connectivity
            cache.get("health_check")

            return jsonify({
                "status": "healthy",
                "timestamp": g.request_id if hasattr(g, 'request_id') else None,
                "environment": config_class.__name__
            }), 200
        except Exception as e:
            if hasattr(app, 'logger_instance'):
                app.logger_instance.error("Health check failed", exception=e)
            return jsonify({
                "status": "unhealthy",
                "error": str(e)
            }), 503

    # Test endpoint for error handling (only in development)
    if config_class.TESTING or app.debug:
        @app.route("/__test_auth_error")
        def test_auth_error():
            from app.utils.exceptions import AuthError
            raise AuthError("Manual test")

        @app.route("/__test_500_error")
        def test_500_error():
            raise Exception("Manual 500 error test")

    # Log successful initialization
    if hasattr(app, 'logger_instance'):
        app.logger_instance.info(
            "Application initialized successfully",
            blueprints_registered=len(app.blueprints),
            environment=config_class.__name__
        )

    return app