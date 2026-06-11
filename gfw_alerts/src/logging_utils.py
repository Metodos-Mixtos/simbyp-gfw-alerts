"""
Database logging utilities for GFW alerts.

Handles logging of alert statistics and report metadata.
Gracefully handles cases where database is disabled.
"""

from datetime import date, datetime
from typing import Optional, Dict, Any
import logging

from src.database import session_scope, is_database_enabled
from src.repositories import AlertStatisticsRepository, ReportSentRepository

logger = logging.getLogger(__name__)


def log_alert_statistics(
    alert_date: date,
    alert_type: str,
    alert_source: Optional[str] = None,
    alert_count: int = 0,
    municipality_code: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Log alert statistics to database.
    
    Args:
        alert_date: Date of alerts
        alert_type: Type of alert (e.g., 'weekly_alerts', 'monthly_built_area')
        alert_source: Source of alert data (e.g., 'gfw', 'psa')
        alert_count: Number of alerts
        municipality_code: Optional Colombian DIVIPOLA code
        metadata: Optional JSON metadata
    
    Returns:
        True if logged successfully, False if database disabled or error
    """
    if not is_database_enabled():
        logger.debug("Database logging disabled. Skipping alert_statistics log.")
        return False
    
    try:
        with session_scope() as session:
            if session is None:
                logger.warning("Failed to get database session. Skipping alert_statistics log.")
                return False
            
            record = AlertStatisticsRepository.create(
                session=session,
                date_=alert_date,
                alert_type=alert_type,
                alert_source=alert_source,
                alert_count=alert_count,
                municipality_code=municipality_code,
                metadata=metadata,
            )
            logger.info(f"✅ Logged alert statistics: {alert_date} {alert_type} ({alert_count} alerts)")
            return True
    
    except Exception as e:
        logger.error(f"Failed to log alert statistics: {e}")
        return False


def log_report_sent(
    alert_type: str,
    report_title: str,
    report_date: Optional[date] = None,
    report_url: Optional[str] = None,
    status: str = 'generated',
    recipient_count: int = 0,
    metadata: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
) -> Optional[str]:
    """
    Log report sent to database.
    
    Args:
        alert_type: Type of alert (e.g., 'weekly_alerts', 'monthly_built_area')
        report_title: Title of the report
        report_date: Date the report covers
        report_url: GCS URL or path to report
        status: Delivery status (default: 'generated')
        recipient_count: Number of recipients
        metadata: Optional JSON metadata
        error_message: Optional error message
    
    Returns:
        Report ID (UUID string) if logged successfully, None if database disabled or error
    """
    if not is_database_enabled():
        logger.debug("Database logging disabled. Skipping reports_sent log.")
        return None
    
    try:
        with session_scope() as session:
            if session is None:
                logger.warning("Failed to get database session. Skipping reports_sent log.")
                return None
            
            record = ReportSentRepository.create(
                session=session,
                alert_type=alert_type,
                report_title=report_title,
                report_date=report_date,
                report_url=report_url,
                status=status,
                recipient_count=recipient_count,
                metadata=metadata,
                error_message=error_message,
            )
            logger.info(f"✅ Logged report: {report_title} (status={status})")
            return str(record.id)
    
    except Exception as e:
        logger.error(f"Failed to log report: {e}")
        return None
