# app/__init__.py
import logging
import os

from flask import Flask, g, jsonify
from flask_jwt_extended import JWTManager
from flask_migrate import Migrate
from flask_session import Session

from app.auth.routes.api import bp as auth_bp
from app.extensions import csrf, mail, limiter, db, cache
from app.features.routes.api import bp as features_bp
from app.icloud.routes.api import bp as icloud_bp
from app.notion.routes.api import bp as notion_bp
from app.scheduling.routes.api import bp as scheduling_bp
from app.subscriptions.routes.api import bp as subscriptions_bp
from app.user_preferences.routes.api import bp as user_bp
from app.utils.app_context import AppContext
from app.utils.exceptions import AuthError, format_error_response
from app.utils.service_factory import ServiceFactory
from config import Config
import redis

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    app.config["SESSION_TYPE"] = "filesystem" if config_class.TESTING else "redis"
    app.config["SESSION_REDIS"] = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )

    session_dir = app.config.get("SESSION_FILE_DIR")
    if session_dir:
        os.makedirs(session_dir, exist_ok=True)

    Session(app)

    # Configure logging
    log_file = os.path.join(os.path.dirname(__file__), 'app.log')
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    logging.basicConfig(
        level=logging.DEBUG if config_class.TESTING else logging.ERROR,
        handlers=[file_handler, stream_handler]
    )

    # Log to confirm initialization
    logging.getLogger().debug(f"Logging initialized. Writing to {log_file}")

    db_uri = app.config.get("SQLALCHEMY_DATABASE_URI")
    logging.info(f"Initializing app with database URL: {db_uri}")
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

    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(notion_bp)
    app.register_blueprint(icloud_bp)
    app.register_blueprint(scheduling_bp)
    app.register_blueprint(subscriptions_bp)
    app.register_blueprint(features_bp)

    @app.route("/__test_auth_error")
    def test_auth_error():
        from app.utils.exceptions import AuthError
        raise AuthError("Manual test")

    @app.errorhandler(AuthError)
    def handle_auth_error(error):
        logging.debug(f"Handling AuthError: {str(error)}")
        error_response, status_code = format_error_response(error, 401)
        from flask.helpers import make_response
        return make_response(jsonify(error_response), status_code)

    @app.before_request
    def setup_request():
        g.db = db.session
        g.cache = {}

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db_session = g.pop("db", None)
        if db_session is not None:
            db.session.remove()
        g.pop("cache", None)

    return app
