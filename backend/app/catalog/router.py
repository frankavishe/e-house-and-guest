"""Public catalogue endpoints: `/categories`, `/categories/{slug}`, `/locations`."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Response

from app.catalog import service
from app.catalog.models import LocationLevel
from app.catalog.schemas import CategoryDetail, CategoryNode, LocationOut
from app.core.deps import Session

router = APIRouter(tags=["catalog"])

CACHE_5_MIN = "public, max-age=300"


@router.get("/categories", response_model=list[CategoryNode])
async def list_categories(session: Session, response: Response) -> list[CategoryNode]:
    response.headers["Cache-Control"] = CACHE_5_MIN
    return await service.category_tree(session)


@router.get(
    "/categories/{slug}",
    response_model=CategoryDetail,
    responses={404: {"description": "Unknown or inactive category"}},
)
async def get_category(
    slug: Annotated[str, Path(max_length=80)], session: Session, response: Response
) -> CategoryDetail:
    response.headers["Cache-Control"] = CACHE_5_MIN
    return await service.category_detail(session, slug)


@router.get("/locations", response_model=list[LocationOut])
async def list_locations(
    session: Session,
    response: Response,
    parent_id: Annotated[int | None, Query(ge=1, le=2_147_483_647)] = None,
    level: LocationLevel | None = None,
) -> list[LocationOut]:
    """Regions by default; children of `parent_id`; or every location of `level`."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    return await service.list_locations(session, parent_id, level)
