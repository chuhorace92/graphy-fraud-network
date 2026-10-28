from fastapi import APIRouter
from pydantic import BaseModel

from graphy.api.deps import Reader

router = APIRouter(tags=["me"])


class Me(BaseModel):
    subject: str
    roles: list[str]


@router.get("/me", response_model=Me)
async def me(user: Reader) -> Me:
    """Who the API thinks you are; the UI uses the roles to hide actions you cannot take."""
    return Me(subject=user.subject, roles=sorted(user.roles))
