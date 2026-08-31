from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Iterable, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.models import Account, Currency, Plan
from app.accounts.service import ResourceNotFound, require_currency
from app.analytics.schemas import (
    ActivityHeatmapResponse,
    AnalyticsSummaryResponse,
    CashflowTrendPoint,
    CashflowTrendsResponse,
    CategoryAnalyticsItem,
    CategoryBreakdownResponse,
    CategoryGoalAnalyticsItem,
    CategoryGroupAnalyticsItem,
    DailyActivityCell,
    GoalsAnalyticsResponse,
    HeatmapCell,
    LocationAnalyticsPoint,
    MerchantRankingItem,
    MerchantRankingsResponse,
    TagAnalyticsItem,
    TagBreakdownResponse,
    UnconvertedAmountItem,
    UnconvertedCurrencySummary,
)
from app.ledger.models import (
    Category,
    CategoryGroup,
    MonthlyBudgetAssignment,
    PostedAccountMovement,
    Tag,
    Transaction,
    TransactionCorrection,
    TransactionTag,
    Transfer,
)
from app.ledger.service import (
    _category_budget_values,
    _get_plan,
    _month_bounds,
    _tag_state,
    fixed_amount,
)


DAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


def resolve_period(
    plan: Plan,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
) -> tuple[datetime, datetime]:
    if month is not None:
        return _month_bounds(plan, month)

    zone = ZoneInfo(plan.budget_timezone)
    now = datetime.now(zone)

    if start_date is None and end_date is None:
        current_month = now.strftime("%Y-%m")
        return _month_bounds(plan, current_month)

    start: datetime
    if isinstance(start_date, str):
        try:
            start = datetime.fromisoformat(start_date)
        except ValueError as exc:
            raise ValueError(f"Invalid start_date format: {start_date}") from exc
    elif isinstance(start_date, datetime):
        start = start_date
    else:
        start = now - timedelta(days=30)

    if start.tzinfo is None:
        start = start.replace(tzinfo=zone)

    end: datetime
    if isinstance(end_date, str):
        try:
            end = datetime.fromisoformat(end_date)
        except ValueError as exc:
            raise ValueError(f"Invalid end_date format: {end_date}") from exc
    elif isinstance(end_date, datetime):
        end = end_date
    else:
        end = now

    if end.tzinfo is None:
        end = end.replace(tzinfo=zone)

    if start >= end:
        raise ValueError("start_date must be earlier than end_date")

    return start, end


def _get_period_movements(
    session: Session,
    plan: Plan,
    start: datetime,
    end: datetime,
) -> list[PostedAccountMovement]:
    movements = list(
        session.scalars(
            select(PostedAccountMovement)
            .where(
                PostedAccountMovement.plan_id == plan.id,
                PostedAccountMovement.effective_at >= start,
                PostedAccountMovement.effective_at < end,
            )
            .order_by(PostedAccountMovement.effective_at, PostedAccountMovement.id)
        )
    )
    if not movements:
        return []

    tx_ids = [m.transaction_id for m in movements]
    replacement_sequences = {
        tx_id: seq
        for tx_id, seq in session.execute(
            select(
                PostedAccountMovement.transaction_id,
                func.max(PostedAccountMovement.correction_sequence),
            )
            .where(
                PostedAccountMovement.plan_id == plan.id,
                PostedAccountMovement.transaction_id.in_(tx_ids),
                PostedAccountMovement.movement_kind == "replacement",
            )
            .group_by(PostedAccountMovement.transaction_id)
        ).tuples()
    }

    active_movements = [
        m
        for m in movements
        if (
            m.movement_kind == "original"
            and m.transaction_id not in replacement_sequences
        )
        or (
            m.movement_kind == "replacement"
            and m.correction_sequence == replacement_sequences[m.transaction_id]
        )
    ]
    return active_movements


def _calculate_unconverted_summaries(
    session: Session,
    foreign_movements: Iterable[PostedAccountMovement],
) -> list[UnconvertedCurrencySummary]:
    by_currency: dict[str, dict[str, Any]] = {}
    for m in foreign_movements:
        if m.transaction_type not in {"income", "expense"}:
            continue
        entry = by_currency.setdefault(
            m.currency_code,
            {
                "income": Decimal(0),
                "expenses": Decimal(0),
                "count": 0,
            },
        )
        signed = Decimal(m.signed_amount)
        if m.transaction_type == "income":
            entry["income"] += signed
        elif m.transaction_type == "expense":
            entry["expenses"] += abs(signed)
        entry["count"] += 1

    results: list[UnconvertedCurrencySummary] = []
    for code, data in sorted(by_currency.items()):
        curr = require_currency(session, code)
        inc = data["income"]
        exp = data["expenses"]
        net = inc - exp
        results.append(
            UnconvertedCurrencySummary(
                currency_code=code,
                total_income=fixed_amount(inc, curr),
                total_expenses=fixed_amount(exp, curr),
                net_amount=fixed_amount(net, curr),
                transaction_count=data["count"],
            )
        )
    return results


def get_analytics_summary(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
) -> AnalyticsSummaryResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)

    transfers_count = (
        session.scalar(
            select(func.count(Transfer.id)).where(
                Transfer.plan_id == plan.id,
                Transfer.event_at >= start,
                Transfer.event_at < end,
            )
        )
        or 0
    )

    income = Decimal(0)
    expenses = Decimal(0)
    tx_count = 0
    foreign_movements: list[PostedAccountMovement] = []

    for m in movements:
        if m.transaction_type not in {"income", "expense"}:
            continue
        if m.currency_code == plan.reporting_currency_code:
            signed = Decimal(m.signed_amount)
            if m.transaction_type == "income":
                income += signed
            elif m.transaction_type == "expense":
                expenses += abs(signed)
            tx_count += 1
        else:
            foreign_movements.append(m)

    net = income - expenses
    if income > 0:
        savings_rate_dec = ((net / income) * Decimal(100)).quantize(Decimal("0.01"))
        savings_rate_str = f"{savings_rate_dec:.2f}"
    else:
        savings_rate_str = "0.00"

    unconverted = _calculate_unconverted_summaries(session, foreign_movements)

    return AnalyticsSummaryResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        period_start=start,
        period_end=end,
        total_income=fixed_amount(income, currency),
        total_expenses=fixed_amount(expenses, currency),
        net_cashflow=fixed_amount(net, currency),
        savings_rate=savings_rate_str,
        transaction_count=tx_count,
        transfers_count=transfers_count,
        transfers_excluded_notice="Transfers are strictly excluded from income, expense, and net cashflow calculations.",
        unconverted_totals=unconverted,
    )


def get_category_breakdown(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    type_: Literal["expense", "income", "all"] = "expense",
) -> CategoryBreakdownResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)

    categories_map = {
        c.id: c
        for c in session.scalars(
            select(Category).where(Category.plan_id == plan.id)
        )
    }
    groups_map = {
        g.id: g
        for g in session.scalars(
            select(CategoryGroup).where(CategoryGroup.plan_id == plan.id)
        )
    }

    target_types = (
        {"income", "expense"}
        if type_ == "all"
        else {type_}
    )

    cat_totals: dict[UUID | None, Decimal] = {}
    cat_counts: dict[UUID | None, int] = {}
    cat_unconverted: dict[UUID | None, dict[str, tuple[Decimal, int]]] = {}
    foreign_movements: list[PostedAccountMovement] = []
    total_reporting = Decimal(0)

    for m in movements:
        if m.transaction_type not in target_types:
            continue
        amt = abs(Decimal(m.signed_amount))
        cat_id = m.category_id

        if m.currency_code == plan.reporting_currency_code:
            cat_totals[cat_id] = cat_totals.get(cat_id, Decimal(0)) + amt
            cat_counts[cat_id] = cat_counts.get(cat_id, 0) + 1
            total_reporting += amt
        else:
            foreign_movements.append(m)
            u_map = cat_unconverted.setdefault(cat_id, {})
            prev_amt, prev_count = u_map.get(m.currency_code, (Decimal(0), 0))
            u_map[m.currency_code] = (prev_amt + amt, prev_count + 1)

    all_cat_ids = set(cat_totals.keys()) | set(cat_unconverted.keys())
    category_items: list[CategoryAnalyticsItem] = []

    for cat_id in all_cat_ids:
        amt = cat_totals.get(cat_id, Decimal(0))
        count = cat_counts.get(cat_id, 0)
        percentage = (
            ((amt / total_reporting) * Decimal(100)).quantize(Decimal("0.01"))
            if total_reporting > 0
            else Decimal("0.00")
        )

        unconv_list: list[UnconvertedAmountItem] = []
        for code, (u_amt, u_cnt) in sorted(cat_unconverted.get(cat_id, {}).items()):
            curr = require_currency(session, code)
            unconv_list.append(
                UnconvertedAmountItem(
                    currency_code=code,
                    amount=fixed_amount(u_amt, curr),
                    transaction_count=u_cnt,
                )
            )

        cat_obj = categories_map.get(cat_id) if cat_id else None
        cat_name = cat_obj.name if cat_obj else "Uncategorized"
        group_id = cat_obj.group_id if cat_obj else None
        group_obj = groups_map.get(group_id) if group_id else None
        group_name = group_obj.name if group_obj else None

        category_items.append(
            CategoryAnalyticsItem(
                category_id=cat_id,
                category_name=cat_name,
                group_id=group_id,
                group_name=group_name,
                amount=fixed_amount(amt, currency),
                percentage=f"{percentage:.2f}",
                transaction_count=count,
                unconverted_by_currency=unconv_list,
            )
        )

    category_items.sort(
        key=lambda x: Decimal(x.amount), reverse=True
    )

    # Rollup by group
    groups_dict: dict[UUID | None, list[CategoryAnalyticsItem]] = {}
    for item in category_items:
        groups_dict.setdefault(item.group_id, []).append(item)

    group_items: list[CategoryGroupAnalyticsItem] = []
    for g_id, c_items in groups_dict.items():
        g_amt = sum((Decimal(item.amount) for item in c_items), Decimal(0))
        g_count = sum(item.transaction_count for item in c_items)
        g_percentage = (
            ((g_amt / total_reporting) * Decimal(100)).quantize(Decimal("0.01"))
            if total_reporting > 0
            else Decimal("0.00")
        )
        g_name = groups_map[g_id].name if g_id and g_id in groups_map else "Ungrouped"

        group_items.append(
            CategoryGroupAnalyticsItem(
                group_id=g_id,
                group_name=g_name,
                amount=fixed_amount(g_amt, currency),
                percentage=f"{g_percentage:.2f}",
                transaction_count=g_count,
                categories=c_items,
            )
        )

    group_items.sort(
        key=lambda x: Decimal(x.amount), reverse=True
    )

    unconverted_totals = _calculate_unconverted_summaries(session, foreign_movements)

    return CategoryBreakdownResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        period_start=start,
        period_end=end,
        type=type_,
        total_amount=fixed_amount(total_reporting, currency),
        categories=category_items,
        groups=group_items,
        unconverted_totals=unconverted_totals,
    )


def get_merchant_rankings(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    limit: int = 10,
) -> MerchantRankingsResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)

    merchant_totals: dict[str, Decimal] = {}
    merchant_counts: dict[str, int] = {}
    merchant_unconverted: dict[str, dict[str, tuple[Decimal, int]]] = {}
    foreign_movements: list[PostedAccountMovement] = []
    total_expense = Decimal(0)

    for m in movements:
        if m.transaction_type != "expense":
            continue
        merchant_name = m.merchant.strip() if m.merchant and m.merchant.strip() else "Unspecified"
        amt = abs(Decimal(m.signed_amount))

        if m.currency_code == plan.reporting_currency_code:
            merchant_totals[merchant_name] = (
                merchant_totals.get(merchant_name, Decimal(0)) + amt
            )
            merchant_counts[merchant_name] = (
                merchant_counts.get(merchant_name, 0) + 1
            )
            total_expense += amt
        else:
            foreign_movements.append(m)
            u_map = merchant_unconverted.setdefault(merchant_name, {})
            prev_amt, prev_count = u_map.get(m.currency_code, (Decimal(0), 0))
            u_map[m.currency_code] = (prev_amt + amt, prev_count + 1)

    all_merchants = set(merchant_totals.keys()) | set(merchant_unconverted.keys())
    ranking_items: list[MerchantRankingItem] = []

    for name in all_merchants:
        amt = merchant_totals.get(name, Decimal(0))
        count = merchant_counts.get(name, 0)
        percentage = (
            ((amt / total_expense) * Decimal(100)).quantize(Decimal("0.01"))
            if total_expense > 0
            else Decimal("0.00")
        )
        avg = amt / count if count > 0 else Decimal(0)

        unconv_list: list[UnconvertedAmountItem] = []
        for code, (u_amt, u_cnt) in sorted(merchant_unconverted.get(name, {}).items()):
            curr = require_currency(session, code)
            unconv_list.append(
                UnconvertedAmountItem(
                    currency_code=code,
                    amount=fixed_amount(u_amt, curr),
                    transaction_count=u_cnt,
                )
            )

        ranking_items.append(
            MerchantRankingItem(
                merchant=name,
                total_amount=fixed_amount(amt, currency),
                percentage=f"{percentage:.2f}",
                transaction_count=count,
                average_amount=fixed_amount(avg, currency),
                unconverted_by_currency=unconv_list,
            )
        )

    ranking_items.sort(key=lambda x: Decimal(x.total_amount), reverse=True)
    if limit > 0:
        ranking_items = ranking_items[:limit]

    unconverted_totals = _calculate_unconverted_summaries(session, foreign_movements)

    return MerchantRankingsResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        period_start=start,
        period_end=end,
        total_expense_amount=fixed_amount(total_expense, currency),
        merchants=ranking_items,
        unconverted_totals=unconverted_totals,
    )


def get_tag_breakdown(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    type_: Literal["expense", "income", "all"] = "expense",
) -> TagBreakdownResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)
    tags_map = {
        t.id: t
        for t in session.scalars(select(Tag).where(Tag.plan_id == plan.id))
    }

    target_types = (
        {"income", "expense"}
        if type_ == "all"
        else {type_}
    )

    tag_totals: dict[UUID, Decimal] = {}
    tag_counts: dict[UUID, int] = {}
    tag_unconverted: dict[UUID, dict[str, tuple[Decimal, int]]] = {}
    foreign_movements: list[PostedAccountMovement] = []

    untagged_amount = Decimal(0)
    untagged_count = 0
    total_tagged = Decimal(0)

    for m in movements:
        if m.transaction_type not in target_types:
            continue
        amt = abs(Decimal(m.signed_amount))
        active_tags = _tag_state(session, plan.id, m.transaction_id)

        if m.currency_code == plan.reporting_currency_code:
            if active_tags:
                for tag_id in active_tags:
                    tag_totals[tag_id] = tag_totals.get(tag_id, Decimal(0)) + amt
                    tag_counts[tag_id] = tag_counts.get(tag_id, 0) + 1
                    total_tagged += amt
            else:
                untagged_amount += amt
                untagged_count += 1
        else:
            foreign_movements.append(m)
            if active_tags:
                for tag_id in active_tags:
                    u_map = tag_unconverted.setdefault(tag_id, {})
                    prev_amt, prev_count = u_map.get(m.currency_code, (Decimal(0), 0))
                    u_map[m.currency_code] = (prev_amt + amt, prev_count + 1)

    all_tag_ids = set(tag_totals.keys()) | set(tag_unconverted.keys())
    tag_items: list[TagAnalyticsItem] = []

    for tag_id in all_tag_ids:
        tag_obj = tags_map.get(tag_id)
        if not tag_obj:
            continue
        amt = tag_totals.get(tag_id, Decimal(0))
        count = tag_counts.get(tag_id, 0)
        percentage = (
            ((amt / total_tagged) * Decimal(100)).quantize(Decimal("0.01"))
            if total_tagged > 0
            else Decimal("0.00")
        )

        unconv_list: list[UnconvertedAmountItem] = []
        for code, (u_amt, u_cnt) in sorted(tag_unconverted.get(tag_id, {}).items()):
            curr = require_currency(session, code)
            unconv_list.append(
                UnconvertedAmountItem(
                    currency_code=code,
                    amount=fixed_amount(u_amt, curr),
                    transaction_count=u_cnt,
                )
            )

        tag_items.append(
            TagAnalyticsItem(
                tag_id=tag_id,
                tag_name=tag_obj.name,
                amount=fixed_amount(amt, currency),
                percentage=f"{percentage:.2f}",
                transaction_count=count,
                unconverted_by_currency=unconv_list,
            )
        )

    tag_items.sort(key=lambda x: Decimal(x.amount), reverse=True)
    unconverted_totals = _calculate_unconverted_summaries(session, foreign_movements)

    return TagBreakdownResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        period_start=start,
        period_end=end,
        type=type_,
        total_tagged_amount=fixed_amount(total_tagged, currency),
        tags=tag_items,
        untagged_amount=fixed_amount(untagged_amount, currency),
        untagged_transaction_count=untagged_count,
        unconverted_totals=unconverted_totals,
    )


def get_cashflow_trends(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    interval: Literal["day", "week", "month"] = "day",
) -> CashflowTrendsResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    zone = ZoneInfo(plan.budget_timezone)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)

    # Build bucket keys and date boundaries
    buckets: dict[str, dict[str, Any]] = {}

    start_local = start.astimezone(zone)
    end_local = end.astimezone(zone)

    if interval == "day":
        cur = start_local.date()
        end_date_bound = end_local.date()
        while cur <= end_date_bound:
            k = cur.strftime("%Y-%m-%d")
            b_start = datetime(cur.year, cur.month, cur.day, tzinfo=zone)
            b_end = b_start + timedelta(days=1)
            buckets[k] = {
                "bucket_key": k,
                "bucket_start": b_start,
                "bucket_end": b_end,
                "income": Decimal(0),
                "expense": Decimal(0),
                "count": 0,
                "foreign": [],
            }
            cur += timedelta(days=1)

    elif interval == "week":
        # Align to Monday of start week
        cur = start_local.date() - timedelta(days=start_local.weekday())
        end_date_bound = end_local.date()
        while cur <= end_date_bound:
            iso_year, iso_week, _ = cur.isocalendar()
            k = f"{iso_year}-W{iso_week:02d}"
            b_start = datetime(cur.year, cur.month, cur.day, tzinfo=zone)
            b_end = b_start + timedelta(days=7)
            if k not in buckets:
                buckets[k] = {
                    "bucket_key": k,
                    "bucket_start": b_start,
                    "bucket_end": b_end,
                    "income": Decimal(0),
                    "expense": Decimal(0),
                    "count": 0,
                    "foreign": [],
                }
            cur += timedelta(days=7)

    elif interval == "month":
        cur_year, cur_month = start_local.year, start_local.month
        end_year, end_month = end_local.year, end_local.month
        while (cur_year, cur_month) <= (end_year, end_month):
            k = f"{cur_year:04d}-{cur_month:02d}"
            b_start = datetime(cur_year, cur_month, 1, tzinfo=zone)
            if cur_month == 12:
                b_end = datetime(cur_year + 1, 1, 1, tzinfo=zone)
                cur_year += 1
                cur_month = 1
            else:
                b_end = datetime(cur_year, cur_month + 1, 1, tzinfo=zone)
                cur_month += 1
            buckets[k] = {
                "bucket_key": k,
                "bucket_start": b_start,
                "bucket_end": b_end,
                "income": Decimal(0),
                "expense": Decimal(0),
                "count": 0,
                "foreign": [],
            }

    # Assign movements to buckets
    for m in movements:
        if m.transaction_type not in {"income", "expense"}:
            continue
        m_local = m.effective_at.astimezone(zone)
        if interval == "day":
            k = m_local.strftime("%Y-%m-%d")
        elif interval == "week":
            iso_year, iso_week, _ = m_local.isocalendar()
            k = f"{iso_year}-W{iso_week:02d}"
        else:
            k = m_local.strftime("%Y-%m")

        if k not in buckets:
            b_start = m.effective_at
            b_end = m.effective_at + timedelta(days=1)
            buckets[k] = {
                "bucket_key": k,
                "bucket_start": b_start,
                "bucket_end": b_end,
                "income": Decimal(0),
                "expense": Decimal(0),
                "count": 0,
                "foreign": [],
            }

        b = buckets[k]
        if m.currency_code == plan.reporting_currency_code:
            amt = abs(Decimal(m.signed_amount))
            if m.transaction_type == "income":
                b["income"] += amt
            elif m.transaction_type == "expense":
                b["expense"] += amt
            b["count"] += 1
        else:
            b["foreign"].append(m)

    # Sort bucket keys chronologically
    sorted_keys = sorted(buckets.keys())
    points: list[CashflowTrendPoint] = []
    cumulative_net = Decimal(0)

    for k in sorted_keys:
        b = buckets[k]
        inc = b["income"]
        exp = b["expense"]
        net = inc - exp
        cumulative_net += net

        foreign_summary = _calculate_unconverted_summaries(session, b["foreign"])

        points.append(
            CashflowTrendPoint(
                bucket_key=k,
                bucket_start=b["bucket_start"],
                bucket_end=b["bucket_end"],
                income=fixed_amount(inc, currency),
                expense=fixed_amount(exp, currency),
                net=fixed_amount(net, currency),
                cumulative_net=fixed_amount(cumulative_net, currency),
                transaction_count=b["count"],
                unconverted_by_currency=foreign_summary,
            )
        )

    return CashflowTrendsResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        interval=interval,
        period_start=start,
        period_end=end,
        points=points,
    )


def get_activity_heatmap(
    session: Session,
    plan_id: UUID,
    *,
    month: str | None = None,
    start_date: datetime | str | None = None,
    end_date: datetime | str | None = None,
    include_locations: bool = False,
) -> ActivityHeatmapResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)
    zone = ZoneInfo(plan.budget_timezone)
    start, end = resolve_period(
        plan, month=month, start_date=start_date, end_date=end_date
    )

    movements = _get_period_movements(session, plan, start, end)

    # 1. Day of week x Hour of day matrix (7 x 24)
    matrix_counts: dict[tuple[int, int], int] = {}
    matrix_amounts: dict[tuple[int, int], Decimal] = {}

    for d in range(7):
        for h in range(24):
            matrix_counts[(d, h)] = 0
            matrix_amounts[(d, h)] = Decimal(0)

    # 2. Daily activity list
    daily_data: dict[str, dict[str, Any]] = {}
    cur = start.astimezone(zone).date()
    end_bound = end.astimezone(zone).date()
    while cur <= end_bound:
        k = cur.strftime("%Y-%m-%d")
        daily_data[k] = {
            "date": k,
            "count": 0,
            "income": Decimal(0),
            "expense": Decimal(0),
            "total": Decimal(0),
        }
        cur += timedelta(days=1)

    location_points: list[LocationAnalyticsPoint] = []

    for m in movements:
        if m.transaction_type not in {"income", "expense"}:
            continue

        local_dt = m.effective_at.astimezone(zone)
        dow = local_dt.weekday()  # 0=Monday, 6=Sunday
        hr = local_dt.hour
        date_str = local_dt.strftime("%Y-%m-%d")
        amt = abs(Decimal(m.signed_amount))

        matrix_counts[(dow, hr)] += 1
        if m.currency_code == plan.reporting_currency_code:
            matrix_amounts[(dow, hr)] += amt

        if date_str not in daily_data:
            daily_data[date_str] = {
                "date": date_str,
                "count": 0,
                "income": Decimal(0),
                "expense": Decimal(0),
                "total": Decimal(0),
            }

        dd = daily_data[date_str]
        dd["count"] += 1
        if m.currency_code == plan.reporting_currency_code:
            if m.transaction_type == "income":
                dd["income"] += amt
            elif m.transaction_type == "expense":
                dd["expense"] += amt
            dd["total"] += amt

        # Location consent-aware processing
        if include_locations and m.location and isinstance(m.location, dict):
            lat = m.location.get("latitude") or m.location.get("lat")
            lng = m.location.get("longitude") or m.location.get("lng") or m.location.get("lon")
            lbl = m.location.get("label") or m.location.get("name") or m.location.get("city")
            try:
                lat_f = float(lat) if lat is not None else None
                lng_f = float(lng) if lng is not None else None
            except (ValueError, TypeError):
                lat_f, lng_f = None, None

            curr = require_currency(session, m.currency_code)
            location_points.append(
                LocationAnalyticsPoint(
                    latitude=lat_f,
                    longitude=lng_f,
                    label=str(lbl) if lbl else None,
                    merchant=m.merchant,
                    amount=fixed_amount(amt, curr),
                    currency_code=m.currency_code,
                    transaction_count=1,
                )
            )

    day_hour_cells: list[HeatmapCell] = []
    for d in range(7):
        for h in range(24):
            day_hour_cells.append(
                HeatmapCell(
                    day_of_week=d,
                    day_name=DAY_NAMES[d],
                    hour_of_day=h,
                    transaction_count=matrix_counts[(d, h)],
                    total_amount=fixed_amount(matrix_amounts[(d, h)], currency),
                )
            )

    daily_cells: list[DailyActivityCell] = []
    for k in sorted(daily_data.keys()):
        dd = daily_data[k]
        daily_cells.append(
            DailyActivityCell(
                date=k,
                transaction_count=dd["count"],
                income=fixed_amount(dd["income"], currency),
                expense=fixed_amount(dd["expense"], currency),
                total_amount=fixed_amount(dd["total"], currency),
            )
        )

    return ActivityHeatmapResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        period_start=start,
        period_end=end,
        day_hour_matrix=day_hour_cells,
        daily_activity=daily_cells,
        location_clusters=location_points if include_locations else None,
    )


def get_goals_analytics(
    session: Session,
    plan_id: UUID,
    *,
    as_of_month: str | None = None,
) -> GoalsAnalyticsResponse:
    plan = _get_plan(session, plan_id)
    currency = require_currency(session, plan.reporting_currency_code)

    if as_of_month is None:
        zone = ZoneInfo(plan.budget_timezone)
        as_of_month = datetime.now(zone).strftime("%Y-%m")

    categories = list(
        session.scalars(
            select(Category).where(
                Category.plan_id == plan.id,
                Category.goal_type.isnot(None),
                Category.status == "active",
            )
        )
    )

    groups_map = {
        g.id: g
        for g in session.scalars(
            select(CategoryGroup).where(CategoryGroup.plan_id == plan.id)
        )
    }

    goal_items: list[CategoryGoalAnalyticsItem] = []

    for cat in categories:
        target = Decimal(cat.goal_target or 0)
        values = _category_budget_values(session, plan, cat, as_of_month)
        assigned, available = values["assigned"], values["available"]
        group_name = groups_map[cat.group_id].name if cat.group_id and cat.group_id in groups_map else None

        current_progress: Decimal
        remaining: Decimal
        status: str

        if cat.goal_type == "target_balance":
            current_progress = available
            remaining = max(target - available, Decimal(0))
            status = "completed" if available >= target else "underfunded"

        elif cat.goal_type == "monthly_funding":
            current_progress = assigned
            remaining = max(target - assigned, Decimal(0))
            status = "funded" if assigned >= target else "underfunded"

        elif cat.goal_type == "due_date":
            current_progress = available
            shortfall = max(target - available, Decimal(0))
            remaining = shortfall
            assert cat.goal_due_month is not None

            if cat.goal_due_month <= as_of_month:
                required = shortfall
            else:
                year, month_num = int(as_of_month[:4]), int(as_of_month[5:])
                due_year, due_month_num = int(cat.goal_due_month[:4]), int(cat.goal_due_month[5:])
                months_remaining = (due_year - year) * 12 + due_month_num - month_num + 1
                required = shortfall / Decimal(max(months_remaining, 1))

            required = required.quantize(Decimal(1).scaleb(-currency.decimal_places))
            status = (
                "completed"
                if shortfall == 0
                else ("on_track" if assigned >= required else "underfunded")
            )
        else:
            continue

        pct = (
            ((current_progress / target) * Decimal(100)).quantize(Decimal("0.01"))
            if target > 0
            else Decimal("0.00")
        )

        goal_items.append(
            CategoryGoalAnalyticsItem(
                category_id=cat.id,
                category_name=cat.name,
                group_name=group_name,
                goal_type=cat.goal_type,
                goal_target=fixed_amount(target, currency),
                goal_due_month=cat.goal_due_month,
                current_progress_amount=fixed_amount(current_progress, currency),
                target_amount=fixed_amount(target, currency),
                progress_percentage=f"{pct:.2f}",
                remaining_amount=fixed_amount(remaining, currency),
                status=status,
            )
        )

    goal_items.sort(key=lambda x: x.category_name.lower())

    return GoalsAnalyticsResponse(
        plan_id=plan.id,
        reporting_currency_code=plan.reporting_currency_code,
        as_of_month=as_of_month,
        goals=goal_items,
    )
