from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, status
from neo4j import AsyncSession as GraphSession
from sqlalchemy.ext.asyncio import AsyncSession

from graphy.auth import (
    User,
    can_audit,
    can_detect,
    can_ingest,
    can_investigate,
    can_read,
    can_steward,
)
from graphy.db.neo4j import get_graph
from graphy.db.postgres import get_session

Pg = Annotated[AsyncSession, Depends(get_session)]
Graph = Annotated[GraphSession, Depends(get_graph)]

Reader = Annotated[User, Depends(can_read)]
Steward = Annotated[User, Depends(can_steward)]
Detector = Annotated[User, Depends(can_detect)]
Investigator = Annotated[User, Depends(can_investigate)]
Auditor = Annotated[User, Depends(can_audit)]
Admin = Annotated[User, Depends(can_ingest)]


def not_yet(requirement: str, phase: str) -> NoReturn:
    """Endpoints in the API contract whose implementation lands in a later delivery phase."""
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        f"{requirement} is scheduled for {phase} (BRD section 12)",
    )
