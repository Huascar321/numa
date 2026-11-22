from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, load_only, sessionmaker

from app.binance_card.models import BinanceCardReview
from app.binance_card.parser import PARSER_VERSION, NoticeResult, parse_notice
from app.gmail.models import GmailMessage


def record_message(session: Session, message: GmailMessage) -> None:
    """Insert once, retaining source evidence; never import a financial service."""
    try:
        result = parse_notice(message.decoded)
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        result = NoticeResult("needs_review", "unreadable_evidence")
    values = asdict(result)
    values["header_message_id"] = values.pop("message_id")
    session.execute(
        insert(BinanceCardReview)
        .values(message_id=message.id, parser_version=PARSER_VERSION, **values)
        .on_conflict_do_nothing(index_elements=["message_id"])
    )


def process_pending(sessions: sessionmaker[Session], *, limit: int = 100) -> int:
    """Bounded local backlog, including disconnected sources; no provider calls."""
    if not 1 <= limit <= 500:
        raise ValueError("Batch size must be between 1 and 500.")
    with sessions.begin() as session:
        messages = session.scalars(
            select(GmailMessage)
            .options(load_only(GmailMessage.id, GmailMessage.decoded))
            .outerjoin(BinanceCardReview, BinanceCardReview.message_id == GmailMessage.id)
            .where(BinanceCardReview.message_id.is_(None))
            .order_by(GmailMessage.id)
            .limit(limit)
            .with_for_update(of=GmailMessage, skip_locked=True)
        ).all()
        for message in messages:
            record_message(session, message)
        return len(messages)
