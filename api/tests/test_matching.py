from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.accounts.models import Account, Plan
from app.accounts.schemas import AccountCreate, PlanCreate
from app.accounts.service import create_account, create_plan
from app.ledger.models import Category, PostedAccountMovement, Tag, Transaction
from app.ledger.schemas import CategoryCreate, TagCreate, TransactionCreate
from app.ledger.service import create_category, create_tag, create_transaction
from app.main import create_app
from app.matching.models import TransactionMatch
from app.matching.schemas import MatchEvaluationRequest
from app.matching.service import (
    accept_match,
    evaluate_plan_matches,
    get_match,
    list_matches,
    reject_match,
    unlink_match,
)
from app.settings import Settings
from app.statements.models import StatementImport, StatementRow
from app.watchers.models import WatcherCandidate, WatcherRawMessage, WatcherSource


def _create_test_plan_and_account(
    session: Session,
    plan_name: str = "Matching Test Plan",
    currency: str = "BOB",
) -> tuple[Plan, Account, Category]:
    plan_id = uuid4()
    plan = create_plan(
        session,
        plan_id=plan_id,
        payload=PlanCreate(
            name=plan_name,
            reporting_currency_code=currency,
            budget_timezone="America/La_Paz",
        ),
    ).resource

    account_id = uuid4()
    account = create_account(
        session,
        plan_id=plan_id,
        account_id=account_id,
        payload=AccountCreate(
            name="Test Checking",
            account_type="Bank",
            currency_code=currency,
        ),
    ).resource

    pending_cat = session.scalar(
        select(Category).where(
            Category.plan_id == plan_id,
            Category.is_pending.is_(True),
        )
    )
    assert pending_cat is not None
    return plan, account, pending_cat


def _create_watcher_source_and_msg(
    session: Session, plan_id: UUID, email: str = "notify@bank.com"
) -> tuple[WatcherSource, WatcherRawMessage]:
    source_id = uuid4()
    source = WatcherSource(
        id=source_id,
        plan_id=plan_id,
        source_type="gmail",
        email_address=email,
        encrypted_refresh_token="encrypted_secret",
        history_id="12345",
        status="active",
        creation_fingerprint=f"source:{email}:{uuid4().hex}",
    )
    session.add(source)
    session.flush()

    raw_msg_id = uuid4()
    raw_msg = WatcherRawMessage(
        id=raw_msg_id,
        plan_id=plan_id,
        source_id=source_id,
        external_message_id=f"msg-{raw_msg_id.hex[:8]}",
        internal_date=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        sender="notifications@bank.com",
        subject="Bank Notification",
        creation_fingerprint=f"raw:{raw_msg_id}",
    )
    session.add(raw_msg)
    session.flush()
    return source, raw_msg


def test_four_way_classification_exact_high_possible_new(
    postgres_sessions: sessionmaker[Session],
) -> None:
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # 1. Transaction A (Manual)
        tx_a_id = uuid4()
        tx_a = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=tx_a_id,
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="150.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
                merchant="Farmacia Chavez",
                memo="Medicine purchase",
                source_metadata={"bcp_transaction_id": "TX-998877"},
                provenance={"source": "manual"},
            ),
        ).resource

        # Candidate 1: EXACT MATCH (matching bcp_transaction_id + amount + currency)
        cand_exact = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="bcp_qr",
            status="pending",
            reported_amount=Decimal("150.00"),
            reported_currency="BOB",
            merchant="Farmacia Chavez",
            subject="Pago QR Farmacia Chavez",
            sender="notificaciones@bcp.com.bo",
            event_at=datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
            raw_payload={"transaction_id": "TX-998877", "receipt_id": "RCPT-1122"},
            creation_fingerprint=f"exact_cand_{uuid4().hex}",
        )
        session.add(cand_exact)

        # Candidate 2: HIGH CONFIDENCE MATCH (matching receipt_id + exact amount + same day)
        tx_b_id = uuid4()
        tx_b = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=tx_b_id,
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="85.50",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc),
                merchant="Hipermaxi",
                source_metadata={"receipt_id": "RCPT-5544"},
                provenance={"source": "manual"},
            ),
        ).resource

        raw_msg_2_id = uuid4()
        raw_msg_2 = WatcherRawMessage(
            id=raw_msg_2_id,
            plan_id=plan.id,
            source_id=source.id,
            external_message_id=f"msg-2-{raw_msg_2_id.hex[:8]}",
            internal_date=datetime(2026, 8, 20, 14, 5, tzinfo=timezone.utc),
            sender="notificaciones@bcp.com.bo",
            subject="Pago QR Hipermaxi",
            creation_fingerprint=f"raw2:{raw_msg_2_id}",
        )
        session.add(raw_msg_2)
        session.flush()

        cand_high = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg_2.id,
            source_id=source.id,
            candidate_type="bcp_qr",
            status="pending",
            reported_amount=Decimal("85.50"),
            reported_currency="BOB",
            merchant="Hipermaxi Los Pozos",
            subject="Pago QR Hipermaxi",
            sender="notificaciones@bcp.com.bo",
            event_at=datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc),
            raw_payload={"receipt_id": "RCPT-5544"},  # No transaction_id, but receipt_id matches
            creation_fingerprint=f"high_cand_{uuid4().hex}",
        )
        session.add(cand_high)

        # Candidate 3: POSSIBLE MATCH (Inconclusive - same amount within 3 days, no shared ID, different description)
        raw_msg_3_id = uuid4()
        raw_msg_3 = WatcherRawMessage(
            id=raw_msg_3_id,
            plan_id=plan.id,
            source_id=source.id,
            external_message_id=f"msg-3-{raw_msg_3_id.hex[:8]}",
            internal_date=datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
            sender="notificaciones@bg.com.bo",
            subject="Debito Cuenta",
            creation_fingerprint=f"raw3:{raw_msg_3_id}",
        )
        session.add(raw_msg_3)
        session.flush()

        cand_possible = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg_3.id,
            source_id=source.id,
            candidate_type="banco_ganadero",
            status="pending",
            reported_amount=Decimal("85.50"),
            reported_currency="BOB",
            subject="Debito Cuenta",
            sender="notificaciones@bg.com.bo",
            event_at=None,
            notification_at=datetime(2026, 8, 22, 9, 0, tzinfo=timezone.utc),
            account_suffix="2488",
            creation_fingerprint=f"possible_cand_{uuid4().hex}",
        )
        session.add(cand_possible)

        # Candidate 4: NEW TRANSACTION (unique amount, no existing match)
        raw_msg_4_id = uuid4()
        raw_msg_4 = WatcherRawMessage(
            id=raw_msg_4_id,
            plan_id=plan.id,
            source_id=source.id,
            external_message_id=f"msg-4-{raw_msg_4_id.hex[:8]}",
            internal_date=datetime(2026, 8, 23, 11, 0, tzinfo=timezone.utc),
            sender="do-not-reply@ses.binance.com",
            subject="Binance Card Purchase",
            creation_fingerprint=f"raw4:{raw_msg_4_id}",
        )
        session.add(raw_msg_4)
        session.flush()

        cand_new = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg_4.id,
            source_id=source.id,
            candidate_type="binance_card",
            status="pending",
            reported_amount=Decimal("9999.99"),
            reported_currency="BOB",
            merchant="Unknown Merchant",
            subject="Binance Card Payment",
            sender="do-not-reply@ses.binance.com",
            event_at=datetime(2026, 8, 23, 11, 0, tzinfo=timezone.utc),
            creation_fingerprint=f"new_cand_{uuid4().hex}",
        )
        session.add(cand_new)
        session.flush()

        # Evaluate matches
        eval_res = evaluate_plan_matches(session, plan.id)
        assert eval_res.evaluated_candidates_count == 4

        matches = {m.candidate_id: m for m in eval_res.evaluations if m.candidate_id}

        # Verify 4 classifications
        assert matches[cand_exact.id].classification == "EXACT_MATCH"
        assert matches[cand_exact.id].transaction_id == tx_a.id

        assert matches[cand_high.id].classification == "HIGH_CONFIDENCE_MATCH"
        assert matches[cand_high.id].transaction_id == tx_b.id

        assert matches[cand_possible.id].classification == "POSSIBLE_MATCH"
        assert matches[cand_possible.id].status == "suggested"

        assert matches[cand_new.id].classification == "NEW_TRANSACTION"


def test_bcp_qr_identifier_precedence(
    postgres_sessions: sessionmaker[Session],
) -> None:
    """Test that BCP QR deduplication prioritizes transaction_id > receipt_id > message_id."""
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # Existing Transaction with transaction_id = TX-1, receipt_id = RCPT-1
        tx_1 = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="200.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                merchant="Merchant One",
                source_metadata={"bcp_transaction_id": "TX-1", "bcp_receipt_id": "RCPT-1"},
                provenance={"source": "manual"},
            ),
        ).resource

        # Candidate with matching transaction_id
        cand_tx = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="bcp_qr",
            status="pending",
            reported_amount=Decimal("200.00"),
            reported_currency="BOB",
            merchant="Merchant One",
            subject="Pago QR",
            sender="notificaciones@bcp.com.bo",
            event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            raw_payload={"transaction_id": "TX-1", "receipt_id": "RCPT-DIFF"},
            creation_fingerprint=f"bcp_tx_cand_{uuid4().hex}",
        )
        session.add(cand_tx)
        session.flush()

        eval_res = evaluate_plan_matches(
            session, plan.id, MatchEvaluationRequest(candidate_id=cand_tx.id)
        )
        match_1 = eval_res.evaluations[0]
        assert match_1.classification == "EXACT_MATCH"
        assert match_1.signals["identifier"]["matched_identifier"] == "transaction_id"


def test_banco_ganadero_statement_enrichment_and_inconclusive_notice(
    postgres_sessions: sessionmaker[Session],
) -> None:
    """Banco Ganadero notice candidate enriched by statement match fills event_at;
    inconclusive notice leaves event_at as None without inferring from notification date.
    """
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # 1. Inconclusive Ganadero notice
        notice_cand = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="banco_ganadero",
            status="pending",
            reported_amount=Decimal("50.00"),
            reported_currency="BOB",
            subject="Aviso de Debito",
            sender="notificaciones@bg.com.bo",
            event_at=None,
            notification_at=datetime(2026, 8, 21, 15, 30, tzinfo=timezone.utc),
            account_suffix="2488",
            creation_fingerprint=f"ganadero_notice_{uuid4().hex}",
        )
        session.add(notice_cand)
        session.flush()

        # Before statement match: evaluation is inconclusive (no matching statement/txn yet)
        eval_1 = evaluate_plan_matches(
            session, plan.id, MatchEvaluationRequest(candidate_id=notice_cand.id)
        )
        assert eval_1.evaluations[0].classification == "NEW_TRANSACTION"
        # Candidate remains with event_at as None!
        session.refresh(notice_cand)
        assert notice_cand.event_at is None
        assert notice_cand.status == "pending"

        # 2. Now a Statement arrives with authoritative transaction fact
        stmt_import = StatementImport(
            id=uuid4(),
            plan_id=plan.id,
            account_id=account.id,
            source_format="banco_ganadero_csv",
            status="committed",
            currency_code="BOB",
            creation_fingerprint=f"stmt_import_{uuid4().hex}",
        )
        session.add(stmt_import)

        stmt_event_time = datetime(2026, 8, 21, 14, 0, tzinfo=timezone.utc)
        stmt_row = StatementRow(
            id=uuid4(),
            plan_id=plan.id,
            import_id=stmt_import.id,
            account_id=account.id,
            source_row_index=0,
            event_at=stmt_event_time,
            transaction_number="TXN-BG-12345",
            description="PAGO SERVICIOS AGUA Tarj: 2488",
            type="debit",
            amount=Decimal("50.00"),
            signed_amount=Decimal("-50.00"),
            running_balance=Decimal("1000.00"),
            compound_identity=f"{account.id}:TXN-BG-12345:0",
            match_status="unmatched",
            card_suffix="2488",
        )
        session.add(stmt_row)

        # Corresponding Transaction posted from statement
        stmt_tx = Transaction(
            id=uuid4(),
            plan_id=plan.id,
            account_id=account.id,
            type="expense",
            amount=Decimal("50.00"),
            currency_code="BOB",
            event_at=stmt_event_time,
            category_id=pending_cat.id,
            memo="PAGO SERVICIOS AGUA Tarj: 2488",
            source="statement",
            source_metadata={
                "transaction_number": "TXN-BG-12345",
                "compound_identity": stmt_row.compound_identity,
                "card_suffix": "2488",
            },
            provenance={"import_id": str(stmt_import.id)},
            creation_fingerprint=f"stmt_tx_{uuid4().hex}",
        )
        session.add(stmt_tx)
        stmt_row.transaction_id = stmt_tx.id
        session.flush()

        # Evaluate again: Ganadero notice matches the statement transaction!
        eval_2 = evaluate_plan_matches(
            session, plan.id, MatchEvaluationRequest(candidate_id=notice_cand.id)
        )
        match_rec = next(
            m for m in eval_2.evaluations if m.candidate_id == notice_cand.id and m.transaction_id == stmt_tx.id
        )
        assert match_rec.classification in ("EXACT_MATCH", "HIGH_CONFIDENCE_MATCH")

        # Accept the match
        accepted = accept_match(session, plan.id, match_rec.id)
        assert accepted.status == "accepted"

        # Verify non-destructive enrichment
        session.refresh(notice_cand)
        session.refresh(stmt_tx)

        assert notice_cand.status == "resolved"
        assert notice_cand.transaction_id == stmt_tx.id
        # Notice retains raw notification_at, but provenance records enriched event time from statement
        assert notice_cand.notification_at == datetime(2026, 8, 21, 15, 30, tzinfo=timezone.utc)
        assert notice_cand.provenance.get("enriched_event_at") == stmt_event_time.isoformat()


def test_non_destructive_enrichment_preserves_manual_fields(
    postgres_sessions: sessionmaker[Session],
) -> None:
    """Non-destructive enrichment MUST NEVER overwrite manual category, custom memo, tags, or merchant."""
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # Create a custom category and tag
        custom_cat = create_category(
            session,
            plan_id=plan.id,
            category_id=uuid4(),
            payload=CategoryCreate(name=f"Health & Care {uuid4().hex[:6]}"),
        ).resource

        custom_tag = create_tag(
            session,
            plan_id=plan.id,
            tag_id=uuid4(),
            payload=TagCreate(name=f"Urgent {uuid4().hex[:6]}"),
        ).resource

        manual_event_time = datetime(2026, 8, 19, 11, 0, tzinfo=timezone.utc)
        manual_tx = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="300.00",
                currency_code="BOB",
                event_at=manual_event_time,
                category_id=custom_cat.id,
                merchant="Dr. Carlos Suarez (Personal Doctor)",
                memo="Annual checkup - User custom memo",
                tags=[custom_tag.id],
                source_metadata={"user_note": "keep this"},
                provenance={"user_created": True},
            ),
        ).resource

        cand = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="binance_card",
            status="pending",
            reported_amount=Decimal("300.00"),
            reported_currency="BOB",
            merchant="BINANCE MERCHANT CLN",
            subject="Card transaction notification",
            sender="do-not-reply@ses.binance.com",
            event_at=manual_event_time,
            message_id_header="<msg-binance-123@ses.binance.com>",
            creation_fingerprint=f"binance_cand_{uuid4().hex}",
        )
        session.add(cand)
        session.flush()

        eval_res = evaluate_plan_matches(
            session, plan.id, MatchEvaluationRequest(candidate_id=cand.id)
        )
        match_rec = eval_res.evaluations[0]

        # Accept match
        accept_match(session, plan.id, match_rec.id)

        session.refresh(manual_tx)

        # Check that manual user fields are preserved intact
        assert manual_tx.category_id == custom_cat.id
        assert manual_tx.merchant == "Dr. Carlos Suarez (Personal Doctor)"
        assert manual_tx.memo == "Annual checkup - User custom memo"
        assert manual_tx.amount == Decimal("300.00")
        assert manual_tx.event_at == manual_event_time

        # Check that external provider IDs were enriched non-destructively
        assert manual_tx.source_metadata.get("message_id") == "<msg-binance-123@ses.binance.com>"
        assert manual_tx.source_metadata.get("user_note") == "keep this"


def test_possible_matches_never_auto_merged(
    postgres_sessions: sessionmaker[Session],
) -> None:
    """auto_link_exact=True must link EXACT_MATCH but NEVER auto-merge or link POSSIBLE_MATCH."""
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # 1. Transaction
        tx = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="500.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                merchant="Restaurant La Estancia",
                provenance={"source": "manual"},
            ),
        ).resource

        # Candidate with similar amount but different date and inconclusive description -> POSSIBLE_MATCH
        cand_possible = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="banco_ganadero",
            status="pending",
            reported_amount=Decimal("500.00"),
            reported_currency="BOB",
            subject="Aviso Debito",
            sender="notificaciones@bg.com.bo",
            event_at=None,
            notification_at=datetime(2026, 8, 24, 18, 0, tzinfo=timezone.utc),
            creation_fingerprint=f"possible_cand_auto_{uuid4().hex}",
        )
        session.add(cand_possible)
        session.flush()

        # Evaluate with auto_link_exact = True
        eval_res = evaluate_plan_matches(
            session,
            plan.id,
            MatchEvaluationRequest(auto_link_exact=True),
        )

        match_rec = eval_res.evaluations[0]
        assert match_rec.classification == "POSSIBLE_MATCH"
        assert match_rec.status == "suggested"  # NOT accepted!

        session.refresh(cand_possible)
        assert cand_possible.status == "pending"
        assert cand_possible.transaction_id is None


def test_accept_reject_unlink_workflow(
    postgres_sessions: sessionmaker[Session],
) -> None:
    """Matches can be accepted, rejected, or unlinked cleanly and reversibly."""
    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        tx = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="120.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                merchant="Supermarket",
                source_metadata={"bcp_transaction_id": "TX-120"},
            ),
        ).resource

        cand = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="bcp_qr",
            status="pending",
            reported_amount=Decimal("120.00"),
            reported_currency="BOB",
            merchant="Supermarket",
            subject="Pago QR Supermarket",
            sender="notificaciones@bcp.com.bo",
            event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            raw_payload={"transaction_id": "TX-120"},
            creation_fingerprint=f"cand_reversibility_{uuid4().hex}",
        )
        session.add(cand)
        session.flush()

        eval_res = evaluate_plan_matches(session, plan.id)
        match_id = eval_res.evaluations[0].id

        # 1. Accept match
        accepted = accept_match(session, plan.id, match_id)
        assert accepted.status == "accepted"
        session.refresh(cand)
        assert cand.status == "resolved"
        assert cand.transaction_id == tx.id

        # 2. Unlink match
        unlinked = unlink_match(session, plan.id, match_id, reason="Incorrect match")
        assert unlinked.status == "unlinked"
        session.refresh(cand)
        assert cand.status == "pending"
        assert cand.transaction_id is None

        # 3. Reject match
        rejected = reject_match(session, plan.id, match_id, reason="User rejected")
        assert rejected.status == "rejected"
        session.refresh(cand)
        assert cand.status == "pending"
        assert cand.transaction_id is None


def test_matching_api_endpoints(
    migrated_postgres_url: str,
    postgres_sessions: sessionmaker[Session],
) -> None:
    settings = Settings(database_url=migrated_postgres_url)
    client = TestClient(create_app(settings))

    with postgres_sessions() as session:
        plan, account, pending_cat = _create_test_plan_and_account(session)
        source, raw_msg = _create_watcher_source_and_msg(session, plan.id)

        # Post Transaction
        tx = create_transaction(
            session,
            plan_id=plan.id,
            transaction_id=uuid4(),
            payload=TransactionCreate(
                account_id=account.id,
                type="expense",
                amount="75.00",
                currency_code="BOB",
                event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
                merchant="Gas Station",
                source_metadata={"transaction_number": "TX-75"},
            ),
        ).resource

        cand = WatcherCandidate(
            id=uuid4(),
            plan_id=plan.id,
            raw_message_id=raw_msg.id,
            source_id=source.id,
            candidate_type="bcp_qr",
            status="pending",
            reported_amount=Decimal("75.00"),
            reported_currency="BOB",
            merchant="Gas Station",
            subject="Pago QR Gas Station",
            sender="notificaciones@bcp.com.bo",
            event_at=datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc),
            raw_payload={"transaction_id": "TX-75"},
            creation_fingerprint=f"cand_api_test_{uuid4().hex}",
        )
        session.add(cand)
        session.commit()

        # 1. POST /evaluate
        eval_resp = client.post(
            f"/plans/{plan.id}/matching/evaluate",
            json={"candidate_id": str(cand.id)},
        )
        assert eval_resp.status_code == 200
        eval_data = eval_resp.json()
        assert eval_data["evaluated_candidates_count"] == 1
        assert len(eval_data["evaluations"]) == 1
        match_id = eval_data["evaluations"][0]["id"]
        assert eval_data["evaluations"][0]["classification"] == "EXACT_MATCH"

        # 2. GET /matches
        matches_resp = client.get(f"/plans/{plan.id}/matching/matches")
        assert matches_resp.status_code == 200
        assert len(matches_resp.json()) >= 1

        # 3. GET /matches/{match_id}
        detail_resp = client.get(f"/plans/{plan.id}/matching/matches/{match_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == match_id

        # 4. POST /matches/{match_id}/accept
        accept_resp = client.post(f"/plans/{plan.id}/matching/matches/{match_id}/accept")
        assert accept_resp.status_code == 200
        assert accept_resp.json()["status"] == "accepted"

        # 5. POST /matches/{match_id}/unlink
        unlink_resp = client.post(
            f"/plans/{plan.id}/matching/matches/{match_id}/unlink",
            json={"reason": "Testing unlink via API"},
        )
        assert unlink_resp.status_code == 200
        assert unlink_resp.json()["status"] == "unlinked"

        # 6. POST /matches/{match_id}/reject
        reject_resp = client.post(
            f"/plans/{plan.id}/matching/matches/{match_id}/reject",
            json={"reason": "Testing reject via API"},
        )
        assert reject_resp.status_code == 200
        assert reject_resp.json()["status"] == "rejected"
