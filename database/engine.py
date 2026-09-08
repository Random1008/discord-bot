from shared.db.engine import create_engine_and_session

from config.settings import settings

engine, AsyncSessionLocal = create_engine_and_session(settings.database_url, echo=settings.sql_echo)
