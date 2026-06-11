"""
SQLAlchemy ORM models for GFW alerts database schema.
"""

from datetime import datetime
from uuid import uuid4
import uuid

from sqlalchemy import Column, String, Integer, Date, DateTime, JSON, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class AlertStatistics(Base):
    """
    Daily aggregate statistics about alerts.
    
    Tracks alert counts by date, type, source, and location.
    """
    __tablename__ = "alert_statistics"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    date = Column(Date, nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)  # weekly_alerts, monthly_built_area, etc.
    alert_source = Column(String(50), index=True)  # gfw, psa, urban_sprawl
    alert_count = Column(Integer, default=0)
    municipality_code = Column(String(10), index=True)  # Colombian DIVIPOLA code
    metadata = Column(JSON)  # Additional metrics in JSON format
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<AlertStatistics({self.date}, {self.alert_type}, count={self.alert_count})>"


class ReportSent(Base):
    """
    Log of all email reports sent by the system.
    
    Tracks report generation, sending status, and delivery metrics.
    """
    __tablename__ = "reports_sent"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_type = Column(String(50), nullable=False, index=True)  # weekly_alerts, monthly_built_area
    report_title = Column(String(500), nullable=False)
    report_url = Column(String(1000))  # GCS path or URL
    report_date = Column(Date, index=True)  # Date the report covers
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    recipient_count = Column(Integer, default=0)
    status = Column(String(20), default='generated')  # generated, sent, failed, partial
    error_message = Column(String(1000))
    metadata = Column(JSON)  # Alert counts, sources, etc.
    
    __table_args__ = (
        CheckConstraint(
            "status IN ('generated', 'sent', 'failed', 'partial')",
            name="reports_sent_status_check"
        ),
    )
    
    def __repr__(self):
        return f"<ReportSent({self.alert_type}, {self.report_date}, status={self.status})>"
