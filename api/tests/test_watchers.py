from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.accounts.service import ResourceNotFound
from app.db import session_factory_for
from app.gmail.models import GmailMessage, GmailSource
from app.main import create_app
from app.settings import Settings
from app.watchers.contracts import (
    HintField, MatchField, NoticeFacts, Predicate, Provider, Rule, SourceRef,
    Stage, STAGE_ORDER,
)
from app.watchers.engine import execute, ruleset_hash
from app.watchers.models import WatcherRun
from app.watchers.service import record_run


SOURCE = SourceRef(str(uuid4()), str(uuid4()), 1, "synthetic-source-message")


def facts(provider=Provider.BINANCE_CARD):
    if provider is Provider.GANADERO:
        return NoticeFacts(provider, "1234.50", "BOB", "Bs", "credit",
            masked_account_suffix="1234", notification_at="2026-01-01T10:01:00+00:00",
            header_message_id="<synthetic@example.invalid>", mime_charset="utf-8",
            authentication_metadata=("trusted_receiver_metadata_not_independent_verification",))
    if provider is Provider.BCP_QR:
        return NoticeFacts(provider, "12.50", "BOB", "BOB", "debit",
            raw_glosa="BM BM QR PAGO DE PRODUCTOS", transaction_id="synthetic-transaction",
            receipt_id="synthetic-receipt", event_at="2026-01-01T10:00:00-04:00",
            notification_at="2026-01-01T10:01:00-04:00", timezone_provenance="synthetic_explicit_offset",
            origin="synthetic-origin", destination="synthetic-destination",
            beneficiary="synthetic-beneficiary", bank="synthetic-bank", mime_charset="iso-8859-1")
    return NoticeFacts(provider, "12345678901234567890.90", "USD", "USD", "debit",
        merchant="SYNTHETIC MERCHANT", event_at="2026-01-01T10:00:00+00:00",
        notification_at="2026-01-01T10:01:00+00:00", timezone_provenance="subject_explicit_utc")


def rule(identifier="merchant-category", value="groceries", *, priority=10):
    return Rule(identifier, 1, priority, Predicate(MatchField.MERCHANT, "SYNTHETIC MERCHANT"), HintField.CATEGORY, value)


def test_stage_order_stable_rule_order_replayability_and_source_provenance():
    rules = (rule("z", priority=1), rule("a", priority=1), rule("unmatched", priority=0))
    unmatched = replace(rules[2], predicate=Predicate(MatchField.MERCHANT, "OTHER"))
    rules = (rules[0], rules[1], unmatched)
    first = execute(facts, rules, source=SOURCE)
    second = execute(facts, tuple(reversed(rules)), source=SOURCE)
    assert first == second
    assert ruleset_hash(rules, {}) == ruleset_hash(tuple(reversed(rules)), {})
    assert tuple(outcome.stage for outcome in first.stages) == STAGE_ORDER
    assert [evidence.rule_id for evidence in first.rules] == ["unmatched", "a", "z"]
    assert first.rules[0].outcome == "skipped_no_match"
    assert dict(first.hints) == {"category_hint": "groceries"}
    assert first.source == SOURCE
    assert first.parsed.reported_amount == "12345678901234567890.90"
    assert first.parsed.reported_currency == "USD"
    assert first.stages[4].status == "skipped" and first.stages[-1].status == "blocked"
    assert "settlement_unresolved" in first.review_reasons
    assert "settlement_amount" not in first.payload()["parsed"]


def test_conflicts_quarantine_and_keep_both_proposals_without_winner():
    result = execute(facts, (rule("one", "groceries"), rule("two", "travel")), source=SOURCE)
    assert result.status == "quarantined" and result.error_code == "rule_conflict"
    assert result.hints == ()
    assert [item.proposed_value for item in result.rules] == ["groceries", "travel"]
    assert result.parsed == facts()
    assert tuple(item.stage for item in result.stages) == STAGE_ORDER
    assert all(item.status == "skipped" for item in result.stages[4:])


def test_manual_hints_are_never_overwritten_even_by_conflicting_proposals():
    result = execute(facts, (rule("one", "groceries"), rule("two", "travel")),
        source=SOURCE, protected_hints={"category_hint": "manual-category"})
    assert result.status == "review_only"
    assert dict(result.hints) == {"category_hint": "manual-category"}
    assert all(item.outcome == "skipped_manual_protection" for item in result.rules)


def test_parser_failures_are_scrubbed_and_preserve_raw_safe_reference():
    def failure():
        raise RuntimeError("private raw body and private-credential-marker")
    result = execute(failure, source=SOURCE)
    assert result.status == "quarantined" and result.error_code == "parser_failed"
    assert result.source == SOURCE
    assert "private" not in str(result.payload())
    assert tuple(item.stage for item in result.stages) == STAGE_ORDER
    assert all(item.status == "skipped" for item in result.stages[3:])


def test_duplicate_rule_id_is_a_quarantined_configuration_not_a_silent_priority_winner():
    result = execute(facts, (rule("same", "groceries"), rule("same", "travel")), source=SOURCE)
    assert result.error_code == "rule_failed"
    assert result.parsed == facts()
    assert result.hints == ()


@pytest.mark.parametrize("provider", tuple(Provider))
def test_provider_facts_are_retained_without_transaction_or_invented_fields(provider):
    parsed = facts(provider)
    result = execute(lambda: parsed, source=SOURCE)
    assert result.status == "review_only" and result.parsed == parsed
    assert result.stages[-1].code == "posting_not_enabled"
    if provider is Provider.GANADERO:
        assert parsed.event_at is parsed.merchant is parsed.raw_glosa is parsed.transaction_id is None
        assert parsed.notification_at is not None
        assert parsed.masked_account_suffix == "1234" and parsed.raw_currency_token == "Bs"
        assert "missing_event_time" in result.review_reasons
        assert "statement_enrichment_required" in result.review_reasons
        assert result.parsed.authentication_metadata == parsed.authentication_metadata
    elif provider is Provider.BCP_QR:
        assert result.parsed.receipt_id == "synthetic-receipt"
        assert result.parsed.transaction_id == "synthetic-transaction"
        assert result.parsed.raw_glosa == "BM BM QR PAGO DE PRODUCTOS"
        assert result.parsed.mime_charset == "iso-8859-1"
        assert result.parsed.timezone_provenance == "synthetic_explicit_offset"


@pytest.mark.parametrize("glosa", [None, "", "unrecognized raw glosa"])
def test_missing_or_unrecognized_glosa_never_gets_default_subtype(glosa):
    parsed = replace(facts(Provider.BCP_QR), raw_glosa=glosa)
    unsafe_rule = Rule("default-subtype", 1, 0, Predicate(MatchField.PROVIDER, "bcp_qr"), HintField.SUBTYPE, "interbank")
    result = execute(lambda: parsed, (unsafe_rule,), source=SOURCE)
    assert result.parsed.raw_glosa == glosa
    assert result.hints == ()
    assert result.rules[0].outcome == "skipped_unsafe_qr_subtype"


@pytest.mark.parametrize("kwargs", [
    {"reported_amount": "1e2"}, {"reported_amount": "NaN"}, {"reported_amount": 1.25},
    {"reported_amount": "0"}, {"merchant": 1.25}, {"event_at": "2026-01-01T10:00:00"},
    {"timezone_provenance": None}, {"direction": "unknown"}, {"reported_currency": ""},
])
def test_untyped_or_ambiguous_facts_are_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        replace(facts(), **kwargs)


@pytest.mark.parametrize("field,value", [("event_at", "2026-01-01T10:00:00+00:00"),
    ("merchant", "INVENTED"), ("raw_glosa", "INVENTED"), ("transaction_id", "INVENTED")])
def test_ganadero_contract_cannot_invent_missing_event_facts(field, value):
    with pytest.raises(ValueError):
        replace(facts(Provider.GANADERO), **{field: value})


def test_rules_cannot_target_amount_currency_account_event_or_raw_glosa():
    for field in ("reported_amount", "reported_currency", "account_id", "event_at", "raw_glosa", "settlement_amount"):
        with pytest.raises(ValueError):
            Rule("unsafe", 1, 0, Predicate(MatchField.PROVIDER, "binance_card"), field, "invented")


@pytest.fixture
def watcher_db(migrated_postgres_url):
    sessions = session_factory_for(migrated_postgres_url)
    with sessions.begin() as session:
        session.execute(text("TRUNCATE plans, jobs CASCADE"))
    api = TestClient(create_app(Settings(_env_file=None, database_url=migrated_postgres_url)))
    plan, source = uuid4(), uuid4()
    assert api.put(f"/plans/{plan}", json={"name": "Watcher foundations", "reporting_currency_code": "BOB", "budget_timezone": "America/La_Paz"}).status_code == 201
    with sessions.begin() as session:
        session.add(GmailSource(id=source, plan_id=plan, status="disconnected", email="synthetic@example.invalid", allowed_senders=[]))
        session.flush()
        message = GmailMessage(source_id=source, gmail_id="synthetic-only", raw_mime=b"synthetic raw evidence", decoded={"headers": [], "parts": [], "issues": []}, provider_metadata={}, status="decoded")
        session.add(message); session.flush(); mid = message.id
    return sessions, plan, mid


def run(sessions, plan, mid, **kwargs):
    with sessions.begin() as session:
        return record_run(session, plan_id=plan, message_id=mid, parser=facts, parser_version="synthetic-parser-v1", **kwargs)


def test_durable_retry_idempotency_explicit_replay_lineage_and_no_financial_changes(watcher_db):
    sessions, plan, mid = watcher_db
    first = run(sessions, plan, mid, rules=(rule(),))
    repeat = run(sessions, plan, mid, rules=(rule(),))
    assert first.revision == repeat.revision == 1
    replay = run(sessions, plan, mid, rules=(rule(),), replay_of=1)
    assert replay.revision == 2 and replay.replayed_from == 1
    assert replay.result == first.result
    changed_contract = run(sessions, plan, mid, rules=(rule(value="different-hint"),))
    assert changed_contract.revision == 3 and changed_contract.replayed_from is None
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(WatcherRun)) == 3
        assert session.get(WatcherRun, (mid, 1)).result == first.result
        assert session.get(GmailMessage, mid).raw_mime == b"synthetic raw evidence"
        assert session.execute(text("SELECT (SELECT count(*) FROM transactions), (SELECT count(*) FROM posted_account_movements)")).one() == (0, 0)


def test_concurrent_retries_create_one_run_and_explicit_replays_have_ordered_revisions(watcher_db):
    sessions, plan, mid = watcher_db
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(sessions, plan, mid), range(2)))
    assert [result.revision for result in results] == [1, 1]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run(sessions, plan, mid, replay_of=1), range(2)))
    assert sorted(result.revision for result in results) == [2, 3]


def test_plan_isolation_bad_replay_parent_rollback_and_immutable_runs(watcher_db):
    sessions, plan, mid = watcher_db
    with pytest.raises(ResourceNotFound):
        run(sessions, uuid4(), mid)
    with pytest.raises(ResourceNotFound):
        run(sessions, plan, mid, replay_of=99)
    with pytest.raises(RuntimeError), sessions.begin() as session:
        record_run(session, plan_id=plan, message_id=mid, parser=facts, parser_version="synthetic-v1")
        raise RuntimeError("Synthetic transaction rollback")
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(WatcherRun)) == 0
    run(sessions, plan, mid)
    with pytest.raises(DBAPIError), sessions.begin() as session:
        session.execute(text("UPDATE watcher_runs SET status='quarantined' WHERE message_id=:mid"), {"mid": mid})


def test_conflict_and_invalid_ruleset_are_durable_and_keep_config_evidence(watcher_db):
    sessions, plan, mid = watcher_db
    conflict = run(sessions, plan, mid, rules=(rule("one", "a"), rule("two", "b")))
    assert conflict.status == "quarantined"
    assert conflict.result["error_code"] == "rule_conflict"
    assert len(conflict.result["rules"]) == 2
    invalid = run(sessions, plan, mid, rules=(rule("same", "a"), rule("same", "b")))
    assert invalid.status == "quarantined" and invalid.result["error_code"] == "rule_failed"
    assert len(invalid.config_snapshot["rules"]) == 2


def test_durable_parser_failure_keeps_source_without_leaking_exception_details(watcher_db):
    sessions, plan, mid = watcher_db
    def failure():
        raise ValueError("private-credential-and-email-body-marker")
    with sessions.begin() as session:
        result = record_run(session, plan_id=plan, message_id=mid, parser=failure, parser_version="synthetic-failure-v1")
        assert result.status == "quarantined"
        assert result.result["source"]["message_id"] == mid
        assert result.result["error_code"] == "parser_failed"
        assert "private-credential" not in str(result.result)
    with sessions() as session:
        assert session.get(WatcherRun, (mid, 1)).result == result.result
        assert session.get(GmailMessage, mid).raw_mime == b"synthetic raw evidence"
