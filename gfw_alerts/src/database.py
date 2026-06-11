"""
Database connection management for GFW alerts pipeline.

Supports both local development (Cloud SQL Proxy via Unix socket) and Cloud Run (Unix socket).
Uses 4-tier configuration pattern:
1. Environment variables (Cloud Run / pre-injected)
2. DATABASE_URL env var (local development)
3. Fallback to disabled mode if DATABASE_URL not set
"""

import os
from typing import Optional
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine
from sqlalchemy.pool import NullPool, QueuePool

# Global session factory (initialized on first use)
_SessionLocal: Optional[sessionmaker] = None
_engine: Optional[Engine] = None


def _get_database_url() -> Optional[str]:
    """
    Retrieve DATABASE_URL from environment.
    
    Returns:
        DATABASE_URL or None if not set
    """
    return os.getenv("DATABASE_URL")


def _init_engine() -> Optional[Engine]:
    """
    Initialize SQLAlchemy engine with proper configuration for Cloud Run and local dev.
    
    Returns:
        Initialized engine or None if DATABASE_URL not set
    """
    database_url = _get_database_url()
    
    if not database_url:
        print("⚠️  DATABASE_URL not set. Database logging disabled.")
        return None
    
    try:
        # Detect if running on Cloud Run (always use NullPool for stateless containers)
        is_cloud_run = os.getenv("K_SERVICE") is not None
        
        if is_cloud_run:
            print("☁️  Detected Cloud Run environment. Using NullPool for stateless connections.")
            pool_class = NullPool
            pool_kwargs = {}
        else:
            # Local development: use QueuePool with reasonable defaults
            print("💻 Local development environment. Using QueuePool.")
            pool_class = QueuePool
            pool_kwargs = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,  # Test connections before using
                "pool_recycle": 3600,   # Recycle connections every hour
            }
        
        engine = create_engine(
            database_url,
            poolclass=pool_class,
            **pool_kwargs,
            echo=False,
        )
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        print(f"✅ Database connection initialized successfully")
        return engine
    
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        print("   Database logging will be disabled.")
        return None


def get_engine() -> Optional[Engine]:
    """
    Get or initialize the SQLAlchemy engine.
    
    Returns:
        Engine instance or None if database is disabled
    """
    global _engine
    
    if _engine is None:
        _engine = _init_engine()
    
    return _engine


def get_session_factory() -> Optional[sessionmaker]:
    """
    Get or initialize the session factory.
    
    Returns:
        sessionmaker instance or None if database is disabled
    """
    global _SessionLocal
    
    if _SessionLocal is None:
        engine = get_engine()
        if engine is not None:
            _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    return _SessionLocal


def get_session() -> Optional[Session]:
    """
    Get a new database session.
    
    Returns:
        Session instance or None if database is disabled
    """
    factory = get_session_factory()
    
    if factory is None:
        return None
    
    return factory()


@contextmanager
def session_scope():
    """
    Context manager for database sessions with automatic commit/rollback.
    
    Usage:
        with session_scope() as session:
            # Use session
            session.add(obj)
    """
    session = get_session()
    
    if session is None:
        # Database is disabled, yield None
        yield None
        return
    
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        print(f"❌ Database transaction failed: {e}")
        raise
    finally:
        session.close()


def is_database_enabled() -> bool:
    """
    Check if database is enabled and operational.
    
    Returns:
        True if database is available, False otherwise
    """
    return get_engine() is not None


def init_db():
    """
    Initialize database tables (create if not exists).
    Should be called on application startup.
    """
    if not is_database_enabled():
        print("⚠️  Database not enabled. Skipping table initialization.")
        return
    
    try:
        # Import models to register them with Base
        from src.models import Base, AlertStatistics, ReportSent
        
        engine = get_engine()
        if engine is None:
            return
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables initialized successfully")
    
    except Exception as e:
        print(f"⚠️  Failed to initialize database tables: {e}")
        print("   Continuing anyway - tables may already exist.")
