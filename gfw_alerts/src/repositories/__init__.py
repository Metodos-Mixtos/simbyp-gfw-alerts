"""
Repository pattern for database operations.
"""

from datetime import date, datetime
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy import func
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
            Created or updated AlertStatistics record
        """

        # Respect DB unique constraint on (date, alert_type, alert_source, COALESCE(municipality_code, ''))
        query = session.query(AlertStatistics).filter(
            AlertStatistics.date == date_,
            AlertStatistics.alert_type == alert_type,
            func.coalesce(AlertStatistics.municipality_code, "") == (municipality_code or ""),
        )

        if alert_source is None:
            query = query.filter(AlertStatistics.alert_source.is_(None))
        else:
            query = query.filter(AlertStatistics.alert_source == alert_source)

        existing = query.first()
        if existing:
            existing.alert_count = alert_count
            existing.metadata_json = metadata or {}
            session.flush()
            return existing

        record = AlertStatistics(
            date=date_,
            alert_type=alert_type,
            alert_source=alert_source,
            alert_count=alert_count,
            municipality_code=municipality_code,
            metadata_json=metadata or {},
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
        status: str = 'sent',
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
            status: Delivery status (sent, failed, partial)
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
            metadata_json=metadata or {},
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
