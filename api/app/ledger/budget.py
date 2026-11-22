"""Plan-local budget projections. Money is derived; no ledger rows are changed."""
from collections import defaultdict
from decimal import Decimal, localcontext
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.accounts.models import Account, Plan
from app.accounts.service import CreationConflict
from app.ledger.models import BudgetAction, Category, MonthlyBudgetAssignment, PostedAccountMovement, Transfer

ZERO = Decimal(0)


def project(session: Session, plan_id: UUID, month: str) -> dict:
    with localcontext() as context:
        context.prec = 80
        return _project(session, plan_id, month)


def _project(session: Session, plan_id: UUID, month: str) -> dict:
    # Import here: ledger service delegates its public projection functions here.
    from app.ledger.service import (_get_plan, _month_bounds, _next_month,
        _goal_response, _unconverted_summary, fixed_amount, require_currency)
    plan = _get_plan(session, plan_id)
    _month_bounds(plan, month)  # Validate public month before querying/replaying.
    currency = require_currency(session, plan.reporting_currency_code)
    zone = ZoneInfo(plan.budget_timezone)
    categories = list(session.scalars(select(Category).where(Category.plan_id == plan_id)
        .order_by(Category.is_pending.desc(), Category.created_at, Category.id)))
    accounts = {a.id: a for a in session.scalars(select(Account).where(Account.plan_id == plan_id))}
    assignments = list(session.scalars(select(MonthlyBudgetAssignment)
        .where(MonthlyBudgetAssignment.plan_id == plan_id)))
    movements = list(session.scalars(select(PostedAccountMovement)
        .where(PostedAccountMovement.plan_id == plan_id)))
    transfers = {t.id: t for t in session.scalars(select(Transfer).where(Transfer.plan_id == plan_id))}
    latest = {}
    for item in movements:
        if item.movement_kind != "compensation":
            previous = latest.get(item.transaction_id)
            if previous is None or item.correction_sequence > previous.correction_sequence:
                latest[item.transaction_id] = item
    active = list(latest.values())
    credit_spending = {}
    credit_cash_inflow = defaultdict(lambda: ZERO)
    card_positions = defaultdict(lambda: ZERO)
    for item in sorted(active, key=lambda m: (m.effective_at, m.transaction_id)):
        account = accounts[item.account_id]
        if account.account_type != "Credit Card" or account.currency_code != currency.code:
            continue
        before = card_positions[account.id]
        after = before + Decimal(item.signed_amount)
        card_positions[account.id] = after
        key = item.effective_at.astimezone(zone).strftime("%Y-%m")
        if item.transaction_type == "expense":
            credit_spending[item.transaction_id] = max(-after, ZERO) - max(-before, ZERO)
        elif item.transaction_type in {"income", "transfer"}:
            credit_cash_inflow[key] += max(after, ZERO) - max(before, ZERO)
    for transfer in transfers.values():
        original = transfers.get(transfer.reverses_transfer_id) if transfer.reverses_transfer_id else transfer
        if original is None:
            continue
        source = accounts[original.source_account_id]
        destination = accounts[original.destination_account_id]
        if (source.account_type == "Credit Card" and destination.account_type != "Credit Card"
                and source.currency_code == destination.currency_code == currency.code):
            key = transfer.event_at.astimezone(zone).strftime("%Y-%m")
            credit_cash_inflow[key] += Decimal(original.inbound_amount) * (-1 if transfer.reverses_transfer_id else 1)
    by_month = defaultdict(list)
    for item in active:
        by_month[item.effective_at.astimezone(zone).strftime("%Y-%m")].append(item)
    assigned = defaultdict(lambda: ZERO)
    for a in assignments:
        assigned[a.month_key, a.category_id] += Decimal(a.amount)
    future_assigned = sum((Decimal(a.amount) for a in assignments if a.month_key > month), ZERO)
    payment_categories = {c.payment_account_id: c for c in categories if c.payment_account_id}
    first = min([month, *[a.month_key for a in assignments if a.month_key <= month],
                 *[m for m in by_month if m <= month]])
    prior = {c.id: ZERO for c in categories}
    ready = ZERO
    prior_cash_excess = ZERO
    current = first
    # PostgreSQL NUMERIC(38,18) inputs require more than Decimal's default 28 digits.
    with localcontext() as context:
        context.prec = 80
        while current <= month:
            items = by_month[current]
            budget_items = [m for m in items if m.currency_code == currency.code]
            income = sum((Decimal(m.signed_amount) for m in budget_items if m.transaction_type == "income"
                          and accounts[m.account_id].account_type != "Credit Card"), ZERO)
            month_assigned = sum((assigned[current, c.id] for c in categories), ZERO)
            ready += income + credit_cash_inflow[current] - month_assigned - prior_cash_excess
            values = {}
            funded_cards = defaultdict(lambda: ZERO)
            cash_excess_total = ZERO
            for category in categories:
                if category.payment_account_id:
                    continue
                rollover = max(prior[category.id], ZERO)
                allocation = assigned[current, category.id]
                funds = rollover + allocation
                expenses = [m for m in budget_items if m.transaction_type == "expense" and m.category_id == category.id]
                cash = sum((-Decimal(m.signed_amount) - credit_spending.get(m.transaction_id, ZERO)
                            for m in expenses), ZERO)
                card_items = sorted((m for m in expenses if accounts[m.account_id].account_type == "Credit Card"),
                    key=lambda m: (m.effective_at, m.transaction_id))
                credit = sum((credit_spending[m.transaction_id] for m in card_items), ZERO)
                cash_excess = max(cash - funds, ZERO)
                remaining = max(funds - cash, ZERO)
                for item in card_items:
                    financed = min(remaining, credit_spending[item.transaction_id])
                    funded_cards[item.account_id] += financed
                    remaining -= financed
                card_excess = max(credit - max(funds - cash, ZERO), ZERO)
                available = funds - cash - credit
                values[category.id] = dict(rollover=rollover, assigned=allocation,
                    activity=-cash-credit, available=available, cash_overspending=cash_excess,
                    credit_card_overspending=card_excess)
                cash_excess_total += cash_excess
            # Payment transfers preserve ledger expense totals; reversals undo reserves.
            payments = defaultdict(lambda: ZERO)
            for transfer in transfers.values():
                if transfer.event_at.astimezone(zone).strftime("%Y-%m") != current:
                    continue
                original = transfers.get(transfer.reverses_transfer_id) if transfer.reverses_transfer_id else transfer
                if original is None:
                    continue
                source = accounts[original.source_account_id]
                destination = accounts[original.destination_account_id]
                if source.account_type != "Credit Card" and destination.id in payment_categories:
                    payments[destination.id] += Decimal(original.inbound_amount) * (-1 if transfer.reverses_transfer_id else 1)
            for account_id, category in payment_categories.items():
                rollover = max(prior[category.id], ZERO)
                allocation = assigned[current, category.id]
                activity = funded_cards[account_id] - payments[account_id]
                available = rollover + allocation + activity
                values[category.id] = dict(rollover=rollover, assigned=allocation, activity=activity,
                    available=available, cash_overspending=max(-available, ZERO), credit_card_overspending=ZERO)
                cash_excess_total += max(-available, ZERO)
            prior = {key: value["available"] for key, value in values.items()}
            prior_cash_excess = cash_excess_total
            if current == month:
                break
            current = _next_month(current)
        fmt = lambda value: fixed_amount(value, currency)
        envelopes = []
        balances = defaultdict(lambda: ZERO)
        for item in movements:
            if item.effective_at.astimezone(zone).strftime("%Y-%m") <= month:
                balances[item.account_id] += Decimal(item.signed_amount)
        for category in categories:
            value = values[category.id]
            goal = _goal_response(category, value, currency, month)
            debt = max(-balances[category.payment_account_id], ZERO) if category.payment_account_id else ZERO
            envelopes.append(dict(plan_id=plan_id, category_id=category.id, month=month, currency=currency.code,
                **{key: fmt(v) for key, v in value.items()},
                assigned_money=dict(amount=fmt(value["assigned"]), currency=currency.code),
                activity_money=dict(amount=fmt(value["activity"]), currency=currency.code),
                available_money=dict(amount=fmt(value["available"]), currency=currency.code), goal=goal,
                payment_account_id=category.payment_account_id,
                payment_debt=fmt(debt), payment_shortfall=fmt(max(debt-value["available"], ZERO)),
                unconverted_by_currency=_unconverted_summary(session, plan, items, category_id=category.id)))
        activity_total = sum((Decimal(m.signed_amount) for m in budget_items if m.transaction_type == "expense"), ZERO)
        adjustments = sum((Decimal(m.signed_amount) for m in budget_items if m.transaction_type == "reconciliation_adjustment"), ZERO)
        ready -= max(future_assigned, ZERO)
        return dict(plan_id=plan_id, month=month, currency=currency.code,
            ready_to_assign=fmt(ready), ready_to_assign_money=dict(amount=fmt(ready), currency=currency.code),
            assigned_total=fmt(month_assigned), activity_total=fmt(activity_total),
            available_total=fmt(sum((v["available"] for v in values.values()), ZERO)),
            assigned_in_future=fmt(max(future_assigned, ZERO)), cash_overspending=fmt(cash_excess_total),
            credit_cash_inflow=fmt(credit_cash_inflow[current]),
            reconciliation_adjustments=fmt(adjustments),
            unconverted_by_currency=_unconverted_summary(session, plan, items), categories=envelopes)


def act(session: Session, plan_id: UUID, action_id: UUID, payload) -> tuple[dict, bool]:
    with localcontext() as context:
        context.prec = 80
        return _act(session, plan_id, action_id, payload)


def _act(session: Session, plan_id: UUID, action_id: UUID, payload) -> tuple[dict, bool]:
    from app.ledger.service import (_get_plan, _require_active_category, amount_for_currency,
        fingerprint, fixed_amount, require_currency, LedgerValidationError)
    plan = session.scalar(select(Plan).where(Plan.id == plan_id).with_for_update())
    if plan is None:
        _get_plan(session, plan_id)
    session.execute(select(func.pg_advisory_xact_lock(action_id.int & ((1 << 63) - 1))))
    currency = require_currency(session, plan.reporting_currency_code)
    canonical = payload.model_dump()
    if payload.amount is not None:
        canonical["amount"] = fixed_amount(amount_for_currency(session, payload.amount,
            currency.code, positive=payload.kind == "move"), currency)
    identity = fingerprint(dict(plan_id=plan_id, **canonical))
    existing = session.get(BudgetAction, action_id)
    if existing:
        if existing.plan_id != plan_id or existing.creation_fingerprint != identity:
            raise CreationConflict("Budget action UUID has a different payload")
        return existing.result, False
    snapshot = project(session, plan_id, payload.month)
    envelopes = {str(e["category_id"]): e for e in snapshot["categories"]}
    changes = []
    if payload.kind == "set_assigned":
        category = _require_active_category(session, plan_id, payload.category_id)
        amount = amount_for_currency(session, payload.amount, currency.code, positive=False)
        delta = amount - Decimal(envelopes[str(category.id)]["assigned"])
        changes.append((category.id, delta))
    elif payload.kind == "fund_target":
        category = _require_active_category(session, plan_id, payload.category_id)
        envelope = envelopes[str(category.id)]
        if not envelope["goal"]:
            raise LedgerValidationError("Category has no target")
        amount = Decimal(envelope["goal"]["required_contribution"])
        if amount > max(Decimal(snapshot["ready_to_assign"]), ZERO):
            raise LedgerValidationError("Not enough Ready to Assign to fund this target")
        changes.append((category.id, amount))
    else:
        amount = amount_for_currency(session, payload.amount, currency.code, positive=True)
        if payload.source_category_id == payload.category_id:
            raise LedgerValidationError("Choose different source and destination")
        if payload.source_category_id:
            source = _require_active_category(session, plan_id, payload.source_category_id)
            available = Decimal(envelopes[str(source.id)]["available"])
            changes.append((source.id, -amount))
        else:
            available = Decimal(snapshot["ready_to_assign"])
        if amount > max(available, ZERO):
            raise LedgerValidationError("Not enough money available in the source")
        if payload.category_id:
            destination = _require_active_category(session, plan_id, payload.category_id)
            changes.append((destination.id, amount))
    for index, (category_id, delta) in enumerate(changes):
        session.add(MonthlyBudgetAssignment(id=uuid5(action_id, str(index)), plan_id=plan_id,
            category_id=category_id, month_key=payload.month, amount=delta, currency_code=currency.code,
            source="budget_action", provenance={"action_id": str(action_id), "kind": payload.kind},
            creation_fingerprint=identity))
    result = dict(id=str(action_id), plan_id=str(plan_id), month=payload.month, kind=payload.kind,
        changes=[dict(category_id=str(c), amount=fixed_amount(d, currency)) for c, d in changes])
    session.add(BudgetAction(id=action_id, plan_id=plan_id, creation_fingerprint=identity, result=result))
    session.flush()
    return result, True
