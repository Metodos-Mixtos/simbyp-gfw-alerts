"""
Repository pattern for database operations.
"""

from datetime import date, datetime
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.orm import Session

from src.models import AlertStatistics, ReportSent


class AlertStatisticsRepository:
    """
    Data access layer for alert statistics.
    """
    
    @staticmethod
    def create(
        session: Session,
        date_: date,
        alert_type: str,
        alert_source: Optional[str],
        alert_count: int,
        municipality_code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AlertStatistics:
        """
        Create and save an alert statistics record.
        
        Args:
            session: Database session
            date_: Date of alerts
            alert_type: Type of alert (weekly_alerts, monthly_built_area, etc.)
            alert_source: Source of alert data (gfw, psa, urban_sprawl, etc.)
            alert_count: Number of alerts
            municipality_code: Optional Colombian DIVIPOLA code
            metadata: Optional JSON metadata
        
        Returns:
            Created AlertStatistics record
        """
        record = AlertStatistics(
            date=date_,
            alert_type=alert_type,
            alert_source=alert_source,
            alert_count=alert_count,
            municipality_code=municipality_code,
            metadata=metadata or {},
        )
        session.add(record)
        session.flush()
        return record


class ReportSentRepository:
    """
    Data access layer for reports sent.
    """
    
    @staticmethod
    def create(
        session: Session,
        alert_type: str,
        report_title: str,
        report_date: Optional[date] = None,
        report_url: Optional[str] = None,
        status: str = 'generated',
        recipient_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> ReportSent:
        """
        Create and save a report sent record.
        
        Args:
            session: Database session
            alert_type: Type of alert (weekly_alerts, monthly_built_area)
            report_title: Title of the report
            report_date: Date the report covers
            report_url: GCS URL or path to report
            status: Delivery status (generated, sent, failed, partial)
            recipient_count: Number of recipients
            metadata: Optional JSON metadata
            error_message: Optional error message
        
        Returns:
            Created ReportSent record
        """
        record = ReportSent(
            alert_type=alert_type,
            report_title=report_title,
            report_date=report_date,
            report_url=report_url,
            status=status,
            recipient_count=recipient_count,
            metadata=metadata or {},
            error_message=error_message,
        )
        session.add(record)
        session.flush()
        return record
    
    @staticmethod
    def update_status(
        session: Session,
        report_id: UUID,
        status: str,
        recipient_count: int = 0,
        error_message: Optional[str] = None,
    ) -> Optional[ReportSent]:
        """
        Update report status (called by email-notifications after sending).
        
        Args:
            session: Database session
            report_id: Report ID
            status: New status
            recipient_count: Updated recipient count
            error_message: Optional error message
        
        Returns:
            Updated ReportSent record or None if not found
        """
        record = session.query(ReportSent).filter(ReportSent.id == report_id).first()
        if record:
            record.status = status
            record.recipient_count = recipient_count
            record.error_message = error_message
            session.flush()
        return record
