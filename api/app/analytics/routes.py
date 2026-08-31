from __future__ import annotations

from collections.abc import Iterator
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.analytics.schemas import (
    ActivityHeatmapResponse,
    AnalyticsSummaryResponse,
    CashflowTrendsResponse,
    CategoryBreakdownResponse,
    GoalsAnalyticsResponse,
    MerchantRankingsResponse,
    TagBreakdownResponse,
)
from app.analytics.service import (
    get_activity_heatmap,
    get_analytics_summary,
    get_cashflow_trends,
    get_category_breakdown,
    get_goals_analytics,
    get_merchant_rankings,
    get_tag_breakdown,
)
from app.db import session_scope


router = APIRouter(tags=["analytics"])


def get_database_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.settings) as session:
        yield session


def _not_found(exc: ResourceNotFound) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail
    )


@router.get(
    "/plans/{plan_id}/analytics/summary",
    response_model=AnalyticsSummaryResponse,
)
def analytics_summary(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    session: Session = Depends(get_database_session),
) -> AnalyticsSummaryResponse:
    try:
        return get_analytics_summary(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/categories",
    response_model=CategoryBreakdownResponse,
)
def analytics_categories(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    type: Literal["expense", "income", "all"] = Query("expense"),
    session: Session = Depends(get_database_session),
) -> CategoryBreakdownResponse:
    try:
        return get_category_breakdown(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            type_=type,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/merchants",
    response_model=MerchantRankingsResponse,
)
def analytics_merchants(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_database_session),
) -> MerchantRankingsResponse:
    try:
        return get_merchant_rankings(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/tags",
    response_model=TagBreakdownResponse,
)
def analytics_tags(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    type: Literal["expense", "income", "all"] = Query("expense"),
    session: Session = Depends(get_database_session),
) -> TagBreakdownResponse:
    try:
        return get_tag_breakdown(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            type_=type,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/trends",
    response_model=CashflowTrendsResponse,
)
def analytics_trends(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    interval: Literal["day", "week", "month"] = Query("day"),
    session: Session = Depends(get_database_session),
) -> CashflowTrendsResponse:
    try:
        return get_cashflow_trends(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/heatmap",
    response_model=ActivityHeatmapResponse,
)
def analytics_heatmap(
    plan_id: UUID,
    month: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    include_locations: bool = Query(False),
    session: Session = Depends(get_database_session),
) -> ActivityHeatmapResponse:
    try:
        return get_activity_heatmap(
            session,
            plan_id,
            month=month,
            start_date=start_date,
            end_date=end_date,
            include_locations=include_locations,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))


@router.get(
    "/plans/{plan_id}/analytics/goals",
    response_model=GoalsAnalyticsResponse,
)
def analytics_goals(
    plan_id: UUID,
    as_of_month: str | None = Query(None),
    session: Session = Depends(get_database_session),
) -> GoalsAnalyticsResponse:
    try:
        return get_goals_analytics(
            session,
            plan_id,
            as_of_month=as_of_month,
        )
    except ResourceNotFound as exc:
        raise _not_found(exc)
    except ValueError as exc:
        raise _unprocessable(str(exc))
