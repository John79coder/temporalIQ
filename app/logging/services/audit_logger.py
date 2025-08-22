import logging
from typing import Optional, Dict, Any
from datetime import datetime
from flask import g, request
from sqlalchemy.orm import Session
from app.logging.config import LoggerName
from app.logging.services.application_logger import ApplicationLogger
from app.logging.models.entities import AuditLog
from app.extensions import db


class AuditLogger:
    """
    Specialized logger for security and compliance events
    that need to be persisted to database
    """

    def __init__(self):
        self.app_logger = ApplicationLogger()
        self.logger = self.app_logger.get_logger(LoggerName.AUDIT)

    def log_authentication(
            self,
            event_type: str,
            user_id: Optional[int] = None,
            email: Optional[str] = None,
            success: bool = True,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None
    ):
        """Log authentication events"""

        self._log_event(
            category="authentication",
            event_type=event_type,
            user_id=user_id,
            email=email,
            success=success,
            ip_address=ip_address or self._get_ip_address(),
            user_agent=user_agent or self._get_user_agent(),
            metadata=metadata
        )

    def log_authorization(
            self,
            resource: str,
            action: str,
            user_id: int,
            allowed: bool,
            reason: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None
    ):
        """Log authorization decisions"""

        self._log_event(
            category="authorization",
            event_type=f"{action}_{resource}",
            user_id=user_id,
            success=allowed,
            resource=resource,
            action=action,
            reason=reason,
            metadata=metadata
        )

    def log_data_access(
            self,
            entity_type: str,
            entity_id: Any,
            action: str,
            user_id: int,
            fields_accessed: Optional[list] = None,
            metadata: Optional[Dict[str, Any]] = None
    ):
        """Log data access for compliance"""

        self._log_event(
            category="data_access",
            event_type=f"{action}_{entity_type}",
            user_id=user_id,
            entity_type=entity_type,
            entity_id=str(entity_id),
            action=action,
            fields_accessed=fields_accessed,
            metadata=metadata
        )

    def log_configuration_change(
            self,
            setting_name: str,
            old_value: Any,
            new_value: Any,
            user_id: int,
            metadata: Optional[Dict[str, Any]] = None
    ):
        """Log system configuration changes"""

        self._log_event(
            category="configuration",
            event_type="setting_changed",
            user_id=user_id,
            setting_name=setting_name,
            old_value=str(old_value),
            new_value=str(new_value),
            metadata=metadata
        )

    def log_security_event(
            self,
            event_type: str,
            severity: str,
            description: str,
            user_id: Optional[int] = None,
            ip_address: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None
    ):
        """Log security-related events"""

        self._log_event(
            category="security",
            event_type=event_type,
            severity=severity,
            description=description,
            user_id=user_id,
            ip_address=ip_address or self._get_ip_address(),
            metadata=metadata
        )

    def _log_event(
            self,
            category: str,
            event_type: str,
            user_id: Optional[int] = None,
            success: bool = True,
            **kwargs
    ):
        """Internal method to log and persist audit events"""

        # Log to file
        self.logger.info(
            f"Audit event: {category}/{event_type}",
            extra={
                'extra_fields': {
                    'category': category,
                    'event_type': event_type,
                    'user_id': user_id,
                    'success': success,
                    **kwargs
                }
            }
        )

        # Persist to database
        try:
            # Extract metadata from kwargs
            metadata = kwargs.pop('metadata', {})

            # Add any remaining kwargs to metadata
            for key, value in kwargs.items():
                if key not in ['ip_address', 'user_agent']:
                    metadata[key] = value

            audit_log = AuditLog(
                category=category,
                event_type=event_type,
                user_id=user_id,
                success=success,
                ip_address=kwargs.get('ip_address') or self._get_ip_address(),
                user_agent=kwargs.get('user_agent') or self._get_user_agent(),
                event_metadata=metadata  # Changed from 'metadata' to 'event_metadata'
            )

            db.session.add(audit_log)
            db.session.commit()

        except Exception as e:
            self.logger.error(
                f"Failed to persist audit log: {e}",
                exc_info=True
            )

    def _get_ip_address(self) -> Optional[str]:
        """Get client IP address from request"""
        if request:
            return request.remote_addr
        return None

    def _get_user_agent(self) -> Optional[str]:
        """Get user agent from request"""
        if request:
            return request.headers.get('User-Agent')
        return None