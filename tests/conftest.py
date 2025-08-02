# tests/conftest.py
import logging
import os
import uuid
import pytest
from flask_session import Session
from passlib.context import CryptContext
from app import create_app
from app.extensions import db, cache as cache_instance
from config import TestingConfig
from app.utils.service_factory import ServiceFactory
from flask_jwt_extended import create_access_token
from tests.utils.custom_client import CSRFClient
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DEFAULT_TEST_PASSWORD = "Secure123!"
PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")

def pytest_configure(config):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)
    print(f"Set working directory to: {os.getcwd()}")

@pytest.fixture
def user_cache():
    return {}

@pytest.fixture
def user_factory(db_session, user_cache, authentication_service):
    def create_user():
        if 'user' not in user_cache:
            user_cache['user'] = authentication_service.create_user(db_session, f"{uuid.uuid4().hex}@example.com", DEFAULT_TEST_PASSWORD)

        return user_cache['user']

    return create_user

@pytest.fixture(autouse=True)
def clear_user_cache(user_cache):
    user_cache.clear()

def create_test_database():
    test_db_url = "postgresql://postgres:postgres@localhost:5432/testdb"
    db_name = test_db_url.split("/")[-1]
    base_url = "/".join(test_db_url.split("/")[:-1]) + "/postgres"
    try:
        conn = psycopg2.connect(base_url)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        # Terminate any open connections to the database
        cursor.execute(f"""
            SELECT pg_terminate_backend(pg_stat_activity.pid)
            FROM pg_stat_activity
            WHERE pg_stat_activity.datname = '{db_name}' AND pid <> pg_backend_pid();
        """)
        # Drop the database if it exists
        cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
        # Create a new database
        cursor.execute(f"CREATE DATABASE {db_name}")
        cursor.close()
        conn.close()
    except Exception as e:
        raise Exception(f"Failed to create test database: {e}")
    return test_db_url

@pytest.fixture(scope="session")
def app():
    os.environ.pop("DATABASE_URL", None)
    os.environ["TEST_DATABASE_URL"] = create_test_database()
    os.environ["FLASK_ENV"] = "test"
    os.environ["ENCRYPTION_KEY"] = TestingConfig.ENCRYPTION_KEY
    print(f"Current working directory: {os.getcwd()}")
    app = create_app(config_class=TestingConfig)
    with app.app_context():
        # Check if SQLAlchemy is already registered
        if "sqlalchemy" not in app.extensions:
            db.init_app(app)
        # Initialize Migrate for flask db upgrade
        from flask_migrate import Migrate
        Migrate(app, db)
        app.config["SESSION_TYPE"] = "filesystem"
        app.config["SQLALCHEMY_DATABASE_URI"] = os.environ["TEST_DATABASE_URL"]
        Session(app)
        db.create_all()
        # Log to confirm app setup
        logging.getLogger().debug("App fixture initialized")
        services = ServiceFactory.initialize_services(cache_instance)
        for name, service in services.items():
            app.extensions['app_context'].set_service(name, service)
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope="function", autouse=True)
def clean_database(app):
    with app.app_context():
        try:
            import app.auth.models.entities
            import app.notion.models.entities
            import app.user_preferences.models.entities
            import app.icloud.models.entities
            import app.notion.smart_mapping.models
            db.session.remove()
            db.drop_all()
            db.create_all()
            for tbl in reversed(db.metadata.sorted_tables):
                db.session.execute(tbl.delete())
            db.session.commit()
            # Log to confirm database cleanup
            logging.getLogger().debug("Database cleaned up")
        except Exception as e:
            logging.error(f"Database cleanup failed in clean_database(app) fixture: {e}")
            raise

@pytest.fixture(scope="function", autouse=True)
def reset_app_state(app):
    with app.app_context():
        app._got_first_request = False
        yield

@pytest.fixture(scope="function", autouse=True)
def clean_cache(app):
    with app.app_context():
        cache_service = app.extensions['app_context'].get_service('caching_service')
        cache_service.clear_all()
        yield

@pytest.fixture
def db_session(app):
    with app.app_context():
        yield db.session

@pytest.fixture
def client(app):
    app.test_client_class = CSRFClient
    client = app.test_client()

    # Access any route to initiate session
    with app.app_context():
        with client.session_transaction() as sess:
            pass  # force session creation

    return client


@pytest.fixture
def authorized_client(app, db_session, user_factory):
    app.test_client_class = CSRFClient
    client = app.test_client()

    # Force session creation before using client
    with app.app_context():
        with client.session_transaction():
            pass

        user = user_factory()

        try:
            if "flask-jwt-extended" not in app.extensions:
                raise RuntimeError("JWTManager not initialized in Flask app")
            access_token = create_access_token(
                identity=str(user.id), additional_claims={"is_verified": True}
            )
        except Exception as e:
            raise RuntimeError(f"Failed to create access token: {str(e)}") from e

        client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer {access_token}'

    return client

@pytest.fixture
def test_user(user_factory):
    user = user_factory()
    return user, user.id

@pytest.fixture(scope="function")
def ai_data_service(app):
    with app.app_context():
        ai_data_service = app.extensions['app_context'].get_service('ai_data_service')
        yield ai_data_service

@pytest.fixture
def features_service(app):
    with app.app_context():
        features_service = app.extensions['app_context'].get_service('features_service')
        yield features_service

@pytest.fixture
def preferences_service(app):
    with app.app_context():
        preferences_service = app.extensions['app_context'].get_service('preferences_service')
        yield preferences_service

@pytest.fixture
def logging_service(app):
    with app.app_context():
        logging_service = app.extensions['app_context'].get_service('logging_service')
        # Log to confirm fixture setup
        logging_service.info("LoggingService fixture created")
        yield logging_service

@pytest.fixture
def user_preference_service(app):
    with app.app_context():
        user_preference_service = app.extensions['app_context'].get_service('user_preference_service')
        yield user_preference_service

@pytest.fixture
def caching_service(app):
    with app.app_context():
        cache_service = app.extensions['app_context'].get_service('caching_service')
        yield cache_service

@pytest.fixture
def mapping_engine(app):
    with app.app_context():
        mapping_engine = app.extensions['app_context'].get_service('mapping_engine')
        yield mapping_engine

@pytest.fixture(scope="session", autouse=True)
def patch_model_metadata():
    from app.notion.models.entities import NotionConnection
    NotionConnection.__table__.extend_existing = True

@pytest.fixture
def authentication_service(app):
    with app.app_context():
        authentication_service = app.extensions['app_context'].get_service('authentication_service')
        yield authentication_service

@pytest.fixture
def encryptor(app):
    with app.app_context():
        encryptor = app.extensions['app_context'].get_service('encryptor')
        yield encryptor