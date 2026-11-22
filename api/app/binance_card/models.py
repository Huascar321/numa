from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

DISPOSITION_CHECK = "disposition IN ('candidate', 'needs_review', 'ignored')"
FACTS_CHECK = r"""
 (disposition = 'candidate' AND reported_amount IS NOT NULL
  AND reported_amount ~ '^[0-9]{1,38}\.[0-9]{1,2}$'
  AND reported_amount::numeric > 0 AND reported_currency IS NOT NULL AND reported_currency = 'USD'
  AND merchant IS NOT NULL AND length(merchant) BETWEEN 1 AND 512
  AND event_at IS NOT NULL AND notification_at IS NOT NULL AND notification_at >= event_at)
 OR (disposition != 'candidate' AND reported_amount IS NULL
  AND reported_currency IS NULL AND merchant IS NULL
  AND event_at IS NULL AND notification_at IS NULL)
"""


class BinanceCardReview(Base):
    __tablename__ = "binance_card_reviews"
    __table_args__ = (
        CheckConstraint(DISPOSITION_CHECK, name="ck_binance_review_disposition"),
        CheckConstraint(FACTS_CHECK, name="ck_binance_review_facts"),
    )

    message_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gmail_messages.id", ondelete="RESTRICT"), primary_key=True
    )
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    disposition: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    reported_amount: Mapped[str | None] = mapped_column(Text)
    reported_currency: Mapped[str | None] = mapped_column(String(3))
    merchant: Mapped[str | None] = mapped_column(Text)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notification_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    header_message_id: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP")
    )
