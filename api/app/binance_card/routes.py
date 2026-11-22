from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Load, Session

from app.accounts.service import ResourceNotFound, get_plan
from app.binance_card.models import BinanceCardReview
from app.gmail.models import GmailMessage, GmailSource
from app.gmail.routes import get_session

router = APIRouter(tags=["binance-card-review"])


@router.get("/plans/{plan_id}/gmail/binance-card-reviews")
def get_reviews(
    plan_id: UUID,
    response: Response,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> dict:
    try:
        get_plan(session, plan_id)
    except ResourceNotFound:
        raise HTTPException(404, "Plan not found.") from None
    response.headers["Cache-Control"] = "no-store"
    base = (
        select(BinanceCardReview, GmailMessage, GmailSource)
        .options(
            Load(GmailMessage).load_only(GmailMessage.id, GmailMessage.gmail_id, GmailMessage.ingested_at),
            Load(GmailSource).load_only(GmailSource.id, GmailSource.email),
        )
        .join(GmailMessage, GmailMessage.id == BinanceCardReview.message_id)
        .join(GmailSource, GmailSource.id == GmailMessage.source_id)
        .where(GmailSource.plan_id == plan_id, BinanceCardReview.disposition != "ignored")
    )
    counts = dict(session.execute(
        select(BinanceCardReview.disposition, func.count())
        .join(GmailMessage, GmailMessage.id == BinanceCardReview.message_id)
        .join(GmailSource, GmailSource.id == GmailMessage.source_id)
        .where(GmailSource.plan_id == plan_id, BinanceCardReview.disposition != "ignored")
        .group_by(BinanceCardReview.disposition)
    ).all())
    rows = session.execute(
        base.where(BinanceCardReview.message_id > after)
        .order_by(BinanceCardReview.message_id).limit(limit + 1)
    ).all()
    return {
        "candidate_count": counts.get("candidate", 0),
        "needs_review_count": counts.get("needs_review", 0),
        "items": [{
            "id": review.message_id,
            "disposition": review.disposition,
            "reason": review.reason,
            "reported_amount": review.reported_amount,
            "reported_currency": review.reported_currency,
            "merchant": review.merchant,
            "event_at": review.event_at,
            "notification_at": review.notification_at,
            "settlement_amount": None,
            "settlement_currency": None,
            "account_id": None,
            "provenance": {
                "source_id": source.id,
                "source_email": source.email,
                "gmail_message_id": message.gmail_id,
                "header_message_id": review.header_message_id,
                "parser_version": review.parser_version,
                "ingested_at": message.ingested_at,
                "processed_at": review.processed_at,
                "sender_authentication": "not_verified_by_parser",
            },
        } for review, message, source in rows[:limit]],
        "next_after": rows[limit - 1][0].message_id if len(rows) > limit else None,
    }
