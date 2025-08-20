# app/utils/service_factory.py
import logging

from flask_caching import Cache

from app.auth.email_verification.repository import TokenRepository
from app.auth.email_verification.service import EmailVerificationService
from app.auth.session_manager.repository import UserRepository
from app.auth.session_manager.service import AuthenticationService
from app.entitlements.repositories.repository import EntitlementsRepository
from app.entitlements.services.entitlements_service import EntitlementsService
from app.features.repositories.repository import FeaturesRepository, AIDataRepository
from app.features.services.ai_data_service import AIDataService
from app.features.services.service import FeaturesService
from app.icloud.repositories.repository import ICloudRepository
from app.icloud.services.client_manager import CalDAVClientManager
from app.icloud.services.event_service import CalDAVEventService
from app.icloud.services.time_block_service import TimeBlockService
from app.notion.auth.service import NotionAuthService
from app.notion.mapping_storage.feedback import FeedbackService, FeedbackRepository
from app.notion.mapping_storage.repository import MappingRepository
from app.notion.mapping_storage.service import MappingService
from app.notion.repositories.repository import NotionAuthRepository
from app.notion.smart_mapping.candidate_generator import CandidateGenerator
from app.notion.smart_mapping.detector_registry import DetectorRegistry
from app.notion.smart_mapping.field_detector_aggregator import FieldDetectorAggregator
from app.notion.smart_mapping.notion_database_engine import NotionDatabaseEngine
from app.notion.smart_mapping.notion_page_engine import NotionPageEngine
from app.notion.smart_mapping.schema_parser import SchemaParser
from app.notion.smart_mapping.task_candidate import TaskCandidateBuilder
from app.scheduling.services.free_time_finder import FreeTimeFinder
from app.scheduling.services.task_prioritizer import TaskPrioritizer
from app.scheduling.services.time_block_generator import TimeBlockGenerator
from app.user_preferences.preferences_store.repository import PreferencesRepository
from app.user_preferences.preferences_store.service import PreferencesService
from app.utils.caching import get_cache_service, ICacheService
from app.utils.encryption import Encryptor
from app.utils.logging_service import LoggingService
from app.utils.security import SecurityService


class ServiceFactory:
    @staticmethod
    def initialize_services(cache: Cache):
        """Initialize all application services."""
        logger = logging.getLogger(__name__)
        logger.info("Initializing services")

        try:
            security_service = SecurityService()
            logger.info("SecurityService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize SecurityService: {str(e)}")
            raise

        logging_service = LoggingService()
        logger.info("LoggingService initialized")

        try:
            caching_service = get_cache_service(cache, security_service)
            logger.info("CachingService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize CachingService: {str(e)}")
            raise

        # Initialize entitlements service early
        try:
            entitlements_repo = EntitlementsRepository()
            entitlements_service = EntitlementsService(entitlements_repo, caching_service, logging_service)
            logger.info("EntitlementsService initialized")
        except Exception as e:
            logger.error(f"Failed to initialize EntitlementsService: {str(e)}")
            raise

        # Initialize user services first
        try:
            user_services = ServiceFactory._init_user_services(caching_service, logging_service, entitlements_service)
            logger.info("User services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize user services: {str(e)}")
            raise

        # Initialize auth services, passing features_service
        try:
            auth_services = ServiceFactory._init_auth_services(caching_service, user_services['features_service'])
            logger.info("Auth services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize auth services: {str(e)}")
            raise

        # Initialize iCloud services
        try:
            icloud_services = ServiceFactory._init_icloud_services(caching_service, logging_service)
            logger.info("iCloud services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize iCloud services: {str(e)}")
            raise

        # Initialize Notion services
        try:
            notion_services = ServiceFactory._init_notion_services(caching_service, logging_service)
            logger.info("Notion services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Notion services: {str(e)}")
            raise

        # Initialize scheduling services
        try:
            ai_data_repo = AIDataRepository(logging_service)
            ai_data_service = AIDataService(ai_data_repo, logging_service)
            logger.info("AI data services initialized")

            time_block_generator = TimeBlockGenerator(
                caching_service,
                None,  # Will be set after FreeTimeFinder initialization
                None,  # Will be set after TaskPrioritizer initialization
                user_services['features_service'],
                ai_data_service,
                logging_service,
                preferences_service=user_services['preferences_service']
            )

            task_prioritizer = TaskPrioritizer(
                caching_service,
                user_services['features_service'],
                user_services['preferences_service'],
                ai_data_service,
                logging_service
            )

            free_time_finder = FreeTimeFinder(
                caching_service,
                icloud_services['event_service'],
                user_services['features_service'],
                user_services['preferences_service'],
                ai_data_service,
                logging_service,
                time_block_generator
            )

            time_block_generator.free_time_finder = free_time_finder
            time_block_generator.task_prioritizer = task_prioritizer

            scheduling_services = {
                'free_time_finder': free_time_finder,
                'task_prioritizer': task_prioritizer,
                'time_block_generator': time_block_generator,
                'ai_data_service': ai_data_service
            }
            logger.info("Scheduling services initialized")
        except Exception as e:
            logger.error(f"Failed to initialize scheduling services: {str(e)}")
            raise

        # Initialize detector registry and mapping engine
        try:
            features_service = user_services['features_service']
            detector_registry = DetectorRegistry(
                features_service,
                ai_data_service,
                logging_service
            ).initialize_default_detectors()

            detector_aggregator = FieldDetectorAggregator(detector_registry)

            mapping_engine = NotionDatabaseEngine(
                caching_service,
                SchemaParser(),
                detector_aggregator,
                CandidateGenerator(
                    caching_service,
                    TaskCandidateBuilder(user_services['preferences_service'])),
                features_service
            )
            logger.info("Mapping engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize mapping engine: {str(e)}")
            raise

        # Initialize page extraction engine
        try:
            page_extraction_engine = NotionPageEngine(
                caching_service,
                features_service,
                user_services['preferences_service'],
                detector_registry,
                logging_service
            )
            logger.info("Page extraction engine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize page extraction engine: {str(e)}")
            raise

        # Combine all services
        services = {
            **auth_services,
            **icloud_services,
            **notion_services,
            **user_services,
            **scheduling_services,
            'mapping_engine': mapping_engine,
            'page_extraction_engine': page_extraction_engine,
            'logging_service': logging_service,
            'entitlements_service': entitlements_service,
            'caching_service': caching_service
        }

        logger.info("All services initialized successfully")
        return services

    @staticmethod
    def _init_auth_services(caching_service: ICacheService, features_service: FeaturesService):
        """Initialize authentication-related services."""
        user_repo = UserRepository()
        authentication_service = AuthenticationService(user_repo, caching_service, features_service)
        token_repo = TokenRepository()
        email_verification_service = EmailVerificationService(token_repo, caching_service)
        return {
            'authentication_service': authentication_service,
            'email_verification_service': email_verification_service
        }

    @staticmethod
    def _init_icloud_services(caching_service: ICacheService, logging_service: LoggingService):
        """Initialize iCloud-related services."""
        icloud_repo = ICloudRepository()
        client_manager = CalDAVClientManager(caching_service, icloud_repo)
        event_service = CalDAVEventService(caching_service, icloud_repo, client_manager)
        time_block_service = TimeBlockService(caching_service, client_manager)
        return {
            'client_manager': client_manager,
            'event_service': event_service,
            'time_block_service': time_block_service
        }

    @staticmethod
    def _init_notion_services(caching_service: ICacheService, logging_service: LoggingService):
        """Initialize Notion-related services."""
        notion_auth_repo = NotionAuthRepository()
        encryptor = Encryptor()
        notion_auth_service = NotionAuthService(notion_auth_repo, caching_service, encryptor)
        mapping_repo = MappingRepository()
        mapping_service = MappingService(mapping_repo)
        feedback_repo = FeedbackRepository()
        feedback_service = FeedbackService(feedback_repo)
        return {
            'notion_auth_service': notion_auth_service,
            'mapping_service': mapping_service,
            'feedback_service': feedback_service,
            'encryptor': encryptor
        }

    @staticmethod
    def _init_user_services(caching_service: ICacheService, logging_service: LoggingService, entitlements_service: EntitlementsService):
        """Initialize user-related services."""
        preferences_repo = PreferencesRepository()
        preferences_service = PreferencesService(preferences_repo, caching_service)
        features_repo = FeaturesRepository(logging_service)
        # Pass entitlements_service instead of subscriptions_service
        features_service = FeaturesService(features_repo, caching_service, entitlements_service, logging_service)
        return {
            'preferences_service': preferences_service,
            'features_service': features_service
        }