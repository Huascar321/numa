from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Plan
from app.accounts.service import ResourceNotFound
from app.fx.models import ExchangeRateQuote
from app.fx.providers import get_registered_providers
from app.fx.schemas import (
    ConvertRequest,
    ConvertResponse,
    LatestQuoteResponse,
    ProviderStatus,
    QuoteCreate,
    QuoteResponse,
)


class NoQuoteAvailable(ValueError):
    """Raised when an explicit FX quote is required for conversion but none is found."""
    pass


class InvalidFXConversion(ValueError):
    """Raised when an invalid or unsupported currency pair conversion is requested."""
    pass


def is_quote_stale(observed_at: datetime, max_age_hours: int = 24) -> bool:
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - observed_at) > timedelta(hours=max_age_hours)


def format_quote_response(
    quote: ExchangeRateQuote, max_age_hours: int = 24
) -> QuoteResponse:
    stale = is_quote_stale(quote.observed_at, max_age_hours=max_age_hours)
    return QuoteResponse(
        id=quote.id,
        plan_id=quote.plan_id,
        base_currency=quote.base_currency,
        quote_currency=quote.quote_currency,
        side=quote.side,
        bob_amount=quote.bob_amount,
        usdt_amount=quote.usdt_amount,
        rate=quote.rate,
        payment_method=quote.payment_method,
        fee_amount=quote.fee_amount,
        min_limit=quote.min_limit,
        max_limit=quote.max_limit,
        source=quote.source,
        offer_context=quote.offer_context,
        observed_at=quote.observed_at,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        is_stale=stale,
        freshness="stale" if stale else "fresh",
    )


def create_quote(
    session: Session,
    plan_id: UUID,
    payload: QuoteCreate,
) -> ExchangeRateQuote:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} not found.")

    quote_id = uuid4()
    observed_at = payload.observed_at or datetime.now(timezone.utc)

    # Compute rate using explicit formula:
    # BUY_USDT: rate = BOB paid / USDT received
    # SELL_USDT: rate = BOB received / USDT sold
    rate = payload.rate
    if rate is None:
        rate = (payload.bob_amount / payload.usdt_amount).quantize(
            Decimal("0.00000001")
        )

    fingerprint = payload.creation_fingerprint
    if not fingerprint:
        raw = f"{plan_id}:{payload.side}:{payload.bob_amount}:{payload.usdt_amount}:{observed_at.isoformat()}:{payload.source}"
        fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:64]

    quote = ExchangeRateQuote(
        id=quote_id,
        plan_id=plan_id,
        base_currency=payload.base_currency,
        quote_currency=payload.quote_currency,
        side=payload.side,
        bob_amount=payload.bob_amount,
        usdt_amount=payload.usdt_amount,
        rate=rate,
        payment_method=payload.payment_method,
        fee_amount=payload.fee_amount or Decimal("0"),
        min_limit=payload.min_limit,
        max_limit=payload.max_limit,
        source=payload.source,
        offer_context=payload.offer_context or {},
        observed_at=observed_at,
        creation_fingerprint=fingerprint,
    )
    session.add(quote)
    session.flush()
    return quote


def list_quotes(
    session: Session,
    plan_id: UUID,
    side: str | None = None,
    source: str | None = None,
    limit: int = 50,
) -> list[QuoteResponse]:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} not found.")

    stmt = select(ExchangeRateQuote).where(ExchangeRateQuote.plan_id == plan_id)
    if side:
        stmt = stmt.where(ExchangeRateQuote.side == side)
    if source:
        stmt = stmt.where(ExchangeRateQuote.source == source)

    stmt = stmt.order_by(
        ExchangeRateQuote.observed_at.desc(),
        ExchangeRateQuote.created_at.desc(),
    ).limit(limit)

    quotes = session.scalars(stmt).all()
    return [format_quote_response(q) for q in quotes]


def get_latest_quotes(
    session: Session,
    plan_id: UUID,
    max_age_hours: int = 24,
) -> LatestQuoteResponse:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} not found.")

    buy_stmt = (
        select(ExchangeRateQuote)
        .where(
            ExchangeRateQuote.plan_id == plan_id,
            ExchangeRateQuote.side == "BUY_USDT",
        )
        .order_by(
            ExchangeRateQuote.observed_at.desc(),
            ExchangeRateQuote.created_at.desc(),
        )
        .limit(1)
    )
    latest_buy = session.scalars(buy_stmt).first()

    sell_stmt = (
        select(ExchangeRateQuote)
        .where(
            ExchangeRateQuote.plan_id == plan_id,
            ExchangeRateQuote.side == "SELL_USDT",
        )
        .order_by(
            ExchangeRateQuote.observed_at.desc(),
            ExchangeRateQuote.created_at.desc(),
        )
        .limit(1)
    )
    latest_sell = session.scalars(sell_stmt).first()

    buy_resp = (
        format_quote_response(latest_buy, max_age_hours=max_age_hours)
        if latest_buy
        else None
    )
    sell_resp = (
        format_quote_response(latest_sell, max_age_hours=max_age_hours)
        if latest_sell
        else None
    )

    has_quote = bool(buy_resp or sell_resp)
    has_fresh_quote = bool(
        (buy_resp and not buy_resp.is_stale)
        or (sell_resp and not sell_resp.is_stale)
    )
    is_stale = not has_fresh_quote

    return LatestQuoteResponse(
        buy_quote=buy_resp,
        sell_quote=sell_resp,
        has_fresh_quote=has_fresh_quote,
        has_quote=has_quote,
        is_stale=is_stale,
        staleness_threshold_hours=max_age_hours,
    )


def convert_currency(
    session: Session,
    plan_id: UUID,
    payload: ConvertRequest,
) -> ConvertResponse:
    plan = session.get(Plan, plan_id)
    if plan is None:
        raise ResourceNotFound(f"Plan {plan_id} not found.")

    from_curr = payload.from_currency.upper()
    to_curr = payload.to_currency.upper()

    if from_curr == to_curr:
        return ConvertResponse(
            from_currency=from_curr,
            to_currency=to_curr,
            from_amount=payload.amount,
            to_amount=payload.amount,
            rate_used=Decimal("1.0"),
            rate_source="identity",
            quote_id=None,
            rate_observed_at=None,
            is_stale=False,
            formula=f"{to_curr} = {from_curr}",
            provenance={
                "conversion_type": "identity",
                "from_currency": from_curr,
                "to_currency": to_curr,
                "amount": str(payload.amount),
            },
        )

    # Conversion BOB -> USDT (BUY_USDT direction)
    if from_curr == "BOB" and to_curr == "USDT":
        rate: Decimal
        rate_source: str
        quote_id: UUID | None = None
        rate_observed_at: datetime | None = None
        is_stale: bool = False
        quote_source: str = "manual"

        if payload.custom_rate is not None:
            rate = payload.custom_rate
            rate_source = "custom_rate"
            quote_source = "custom"
        elif payload.quote_id is not None:
            quote = session.get(ExchangeRateQuote, payload.quote_id)
            if quote is None or quote.plan_id != plan_id:
                raise ResourceNotFound(
                    f"Exchange rate quote {payload.quote_id} not found."
                )
            rate = quote.rate
            rate_source = f"quote_{quote.id}"
            quote_id = quote.id
            rate_observed_at = quote.observed_at
            is_stale = is_quote_stale(quote.observed_at)
            quote_source = quote.source
        else:
            latest = session.scalars(
                select(ExchangeRateQuote)
                .where(
                    ExchangeRateQuote.plan_id == plan_id,
                    ExchangeRateQuote.side == "BUY_USDT",
                )
                .order_by(
                    ExchangeRateQuote.observed_at.desc(),
                    ExchangeRateQuote.created_at.desc(),
                )
                .limit(1)
            ).first()
            if latest is None:
                raise NoQuoteAvailable(
                    "No exchange rate quote available for BOB -> USDT conversion. "
                    "Manual quote is required; official 6.96 rate is never assumed."
                )
            rate = latest.rate
            rate_source = "latest_buy_quote"
            quote_id = latest.id
            rate_observed_at = latest.observed_at
            is_stale = is_quote_stale(latest.observed_at)
            quote_source = latest.source

        # USDT amount = BOB paid / rate (rate = BOB / USDT)
        to_amount = (payload.amount / rate).quantize(
            Decimal("0.000001"), rounding=ROUND_HALF_UP
        )
        formula = "USDT = BOB / rate (rate = BOB paid / USDT received)"

        provenance = {
            "from_currency": from_curr,
            "to_currency": to_curr,
            "from_amount": str(payload.amount),
            "to_amount": str(to_amount),
            "rate_used": str(rate),
            "rate_source": rate_source,
            "quote_id": str(quote_id) if quote_id else None,
            "side": "BUY_USDT",
            "observed_at": rate_observed_at.isoformat() if rate_observed_at else None,
            "is_stale": is_stale,
            "source": quote_source,
            "formula": formula,
        }

        return ConvertResponse(
            from_currency=from_curr,
            to_currency=to_curr,
            from_amount=payload.amount,
            to_amount=to_amount,
            rate_used=rate,
            rate_source=rate_source,
            quote_id=quote_id,
            rate_observed_at=rate_observed_at,
            is_stale=is_stale,
            formula=formula,
            provenance=provenance,
        )

    # Conversion USDT -> BOB (SELL_USDT direction)
    if from_curr == "USDT" and to_curr == "BOB":
        rate: Decimal
        rate_source: str
        quote_id: UUID | None = None
        rate_observed_at: datetime | None = None
        is_stale: bool = False
        quote_source: str = "manual"

        if payload.custom_rate is not None:
            rate = payload.custom_rate
            rate_source = "custom_rate"
            quote_source = "custom"
        elif payload.quote_id is not None:
            quote = session.get(ExchangeRateQuote, payload.quote_id)
            if quote is None or quote.plan_id != plan_id:
                raise ResourceNotFound(
                    f"Exchange rate quote {payload.quote_id} not found."
                )
            rate = quote.rate
            rate_source = f"quote_{quote.id}"
            quote_id = quote.id
            rate_observed_at = quote.observed_at
            is_stale = is_quote_stale(quote.observed_at)
            quote_source = quote.source
        else:
            latest = session.scalars(
                select(ExchangeRateQuote)
                .where(
                    ExchangeRateQuote.plan_id == plan_id,
                    ExchangeRateQuote.side == "SELL_USDT",
                )
                .order_by(
                    ExchangeRateQuote.observed_at.desc(),
                    ExchangeRateQuote.created_at.desc(),
                )
                .limit(1)
            ).first()
            if latest is None:
                raise NoQuoteAvailable(
                    "No exchange rate quote available for USDT -> BOB conversion. "
                    "Manual quote is required; official 6.96 rate is never assumed."
                )
            rate = latest.rate
            rate_source = "latest_sell_quote"
            quote_id = latest.id
            rate_observed_at = latest.observed_at
            is_stale = is_quote_stale(latest.observed_at)
            quote_source = latest.source

        # BOB amount = USDT sold * rate (rate = BOB received / USDT sold)
        to_amount = (payload.amount * rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        formula = "BOB = USDT * rate (rate = BOB received / USDT sold)"

        provenance = {
            "from_currency": from_curr,
            "to_currency": to_curr,
            "from_amount": str(payload.amount),
            "to_amount": str(to_amount),
            "rate_used": str(rate),
            "rate_source": rate_source,
            "quote_id": str(quote_id) if quote_id else None,
            "side": "SELL_USDT",
            "observed_at": rate_observed_at.isoformat() if rate_observed_at else None,
            "is_stale": is_stale,
            "source": quote_source,
            "formula": formula,
        }

        return ConvertResponse(
            from_currency=from_curr,
            to_currency=to_curr,
            from_amount=payload.amount,
            to_amount=to_amount,
            rate_used=rate,
            rate_source=rate_source,
            quote_id=quote_id,
            rate_observed_at=rate_observed_at,
            is_stale=is_stale,
            formula=formula,
            provenance=provenance,
        )

    raise InvalidFXConversion(
        f"Unsupported currency conversion: {from_curr} to {to_curr}. "
        "Only BOB and USDT pairs are supported."
    )


def list_providers() -> list[ProviderStatus]:
    return [p.get_status() for p in get_registered_providers()]
