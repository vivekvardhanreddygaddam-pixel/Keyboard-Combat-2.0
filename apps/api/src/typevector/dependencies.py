"""TypeVector Arena — FastAPI Common Dependencies."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from typevector.database import get_db_session, get_db_session_optional

# Standard annotated database session dependency for route handlers
DbSession = Annotated[AsyncSession, Depends(get_db_session)]

# Optional database session dependency for standalone/offline-resilient route handlers
DbSessionOptional = Annotated[AsyncSession | None, Depends(get_db_session_optional)]
