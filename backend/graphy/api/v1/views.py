import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from graphy.api.deps import Pg, Reader
from graphy.db.models import SavedView

router = APIRouter(tags=["views"])


class ViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    shared: bool = False
    state: dict[str, Any]  # canvas state: root entity, expanded groups, filters, positions


class ViewOut(ViewIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner: str
    created_at: datetime


@router.get("/views", response_model=list[ViewOut])
async def list_views(pg: Pg, user: Reader) -> list[SavedView]:
    q = select(SavedView).where(or_(SavedView.owner == user.subject, SavedView.shared))
    return list(await pg.scalars(q.order_by(SavedView.created_at.desc())))


@router.post("/views", response_model=ViewOut, status_code=201)
async def save_view(body: ViewIn, pg: Pg, user: Reader) -> SavedView:
    view = SavedView(**body.model_dump(), owner=user.subject)
    pg.add(view)
    await pg.commit()
    return view
