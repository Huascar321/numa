"""Add immutable reconciliation sessions and protected adjustments.

Revision ID: 006_reconciliation
Revises: 005_budget_engine
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "006_reconciliation"
down_revision: str | None = "005_budget_engine"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "reconciliation_sessions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("plan_id", uuid, nullable=False),
        sa.Column("account_id", uuid, nullable=False),
        sa.Column("currency_code", sa.String(16), nullable=False),
        sa.Column("statement_balance", sa.Numeric(), nullable=False),
        sa.Column("statement_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("derived_balance", sa.Numeric(), nullable=False),
        sa.Column("discrepancy", sa.Numeric(), nullable=False),
        sa.Column("policy", sa.String(16), nullable=False),
        sa.Column("tolerance", sa.Numeric(), nullable=False),
        sa.Column("warning_accepted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("policy IN ('block', 'warn')", name="ck_reconciliation_sessions_policy"),
        sa.CheckConstraint("tolerance >= 0", name="ck_reconciliation_sessions_tolerance_nonnegative"),
        sa.CheckConstraint(
            "statement_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND derived_balance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND discrepancy NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND tolerance NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)",
            name="ck_reconciliation_sessions_amounts_finite",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_reconciliation_sessions_plan", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id", "account_id"], ["accounts.plan_id", "accounts.id"], name="fk_reconciliation_sessions_plan_account_same_plan", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["currency_code"], ["currencies.code"], name="fk_reconciliation_sessions_currency", onupdate="RESTRICT", ondelete="RESTRICT"),
        sa.UniqueConstraint("plan_id", "id", name="uq_reconciliation_sessions_plan_id_id"),
    )
    op.create_index(
        "ix_reconciliation_sessions_account_confirmed",
        "reconciliation_sessions",
        ["plan_id", "account_id", "confirmed_at"],
    )

    op.add_column("transactions", sa.Column("reconciliation_session_id", uuid, nullable=True))
    op.add_column("posted_account_movements", sa.Column("reconciliation_session_id", uuid, nullable=True))
    op.create_foreign_key(
        "fk_transactions_reconciliation_session_same_plan",
        "transactions",
        "reconciliation_sessions",
        ["plan_id", "reconciliation_session_id"],
        ["plan_id", "id"],
        onupdate="RESTRICT",
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_posted_movements_reconciliation_session_same_plan",
        "posted_account_movements",
        "reconciliation_sessions",
        ["plan_id", "reconciliation_session_id"],
        ["plan_id", "id"],
        onupdate="RESTRICT",
        ondelete="RESTRICT",
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_unique_constraint(
        "uq_transactions_reconciliation_session",
        "transactions",
        ["plan_id", "reconciliation_session_id"],
    )
    op.create_unique_constraint(
        "uq_posted_movements_reconciliation_session",
        "posted_account_movements",
        ["plan_id", "reconciliation_session_id"],
    )

    op.drop_constraint("ck_transactions_type", "transactions", type_="check")
    op.drop_constraint("ck_transactions_category_by_type", "transactions", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_category_by_type", "posted_account_movements", type_="check")
    op.create_check_constraint(
        "ck_transactions_type",
        "transactions",
        "type IN ('income', 'expense', 'transfer', 'reconciliation_adjustment')",
    )
    op.create_check_constraint(
        "ck_transactions_category_by_type",
        "transactions",
        "(type IN ('transfer', 'reconciliation_adjustment') AND category_id IS NULL) OR "
        "(type IN ('income', 'expense') AND category_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_transactions_reconciliation_link",
        "transactions",
        "(type = 'reconciliation_adjustment') = (reconciliation_session_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_posted_movements_transaction_type",
        "posted_account_movements",
        "transaction_type IN ('income', 'expense', 'transfer', 'reconciliation_adjustment')",
    )
    op.create_check_constraint(
        "ck_posted_movements_category_by_type",
        "posted_account_movements",
        "(transaction_type IN ('transfer', 'reconciliation_adjustment') AND category_id IS NULL) OR "
        "(transaction_type IN ('income', 'expense') AND category_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_posted_movements_reconciliation_link",
        "posted_account_movements",
        "(transaction_type = 'reconciliation_adjustment') = (reconciliation_session_id IS NOT NULL)",
    )

    op.execute(sa.text("""
    CREATE OR REPLACE FUNCTION numa_reject_transfer_correction()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (SELECT type FROM transactions WHERE plan_id=NEW.plan_id AND id=NEW.transaction_id)
         IN ('transfer', 'reconciliation_adjustment') THEN
        RAISE EXCEPTION 'protected transactions cannot be corrected';
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION numa_reject_reconciliation_transaction_mutation()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.type = 'reconciliation_adjustment' THEN
        RAISE EXCEPTION 'reconciliation adjustments are append-only';
      END IF;
      RETURN NEW;
    END $$;

    CREATE TRIGGER transactions_reconciliation_append_only
      BEFORE UPDATE OR DELETE ON transactions FOR EACH ROW
      EXECUTE FUNCTION numa_reject_reconciliation_transaction_mutation();
    CREATE TRIGGER reconciliation_sessions_append_only
      BEFORE UPDATE OR DELETE ON reconciliation_sessions FOR EACH ROW
      EXECUTE FUNCTION numa_reject_append_only_mutation();

    CREATE FUNCTION numa_reconciliation_integrity()
    RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE
      root reconciliation_sessions%ROWTYPE;
      account_currency text;
      account_status text;
      places integer;
      as_of_balance numeric;
      transaction_count integer;
      movement_count integer;
      adjustment transactions%ROWTYPE;
      movement posted_account_movements%ROWTYPE;
      target_id uuid;
    BEGIN
      IF TG_TABLE_NAME = 'reconciliation_sessions' THEN
        target_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END;
      ELSIF TG_TABLE_NAME = 'transactions' THEN
        target_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.reconciliation_session_id ELSE NEW.reconciliation_session_id END;
      ELSE
        target_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.reconciliation_session_id ELSE NEW.reconciliation_session_id END;
      END IF;
      IF target_id IS NULL THEN
        RETURN NULL;
      END IF;
      FOR root IN SELECT * FROM reconciliation_sessions WHERE id = target_id LOOP
        SELECT a.currency_code, a.status, c.decimal_places
          INTO account_currency, account_status, places
          FROM accounts a JOIN currencies c ON c.code = a.currency_code
          WHERE a.plan_id = root.plan_id AND a.id = root.account_id;
        IF account_currency IS NULL OR root.currency_code <> account_currency THEN
          RAISE EXCEPTION 'reconciliation currency must match Account currency';
        END IF;
        IF root.statement_balance <> trunc(root.statement_balance, places)
           OR root.derived_balance <> trunc(root.derived_balance, places)
           OR root.discrepancy <> trunc(root.discrepancy, places)
           OR root.tolerance <> trunc(root.tolerance, places) THEN
          RAISE EXCEPTION 'reconciliation amounts exceed Account currency scale';
        END IF;
        SELECT coalesce(sum(signed_amount), 0) INTO as_of_balance
          FROM posted_account_movements
          WHERE plan_id = root.plan_id
            AND account_id = root.account_id
            AND currency_code = root.currency_code
            AND effective_at <= root.statement_at
            AND reconciliation_session_id IS DISTINCT FROM root.id;
        IF root.derived_balance <> as_of_balance
           OR root.discrepancy <> root.statement_balance - root.derived_balance THEN
          RAISE EXCEPTION 'reconciliation comparison is inconsistent';
        END IF;
        IF abs(root.discrepancy) > root.tolerance AND root.policy = 'block' THEN
          RAISE EXCEPTION 'blocked reconciliation exceeds tolerance';
        END IF;
        IF abs(root.discrepancy) > root.tolerance AND root.policy = 'warn'
           AND NOT root.warning_accepted THEN
          RAISE EXCEPTION 'warning acceptance is required';
        END IF;

        SELECT count(*) INTO transaction_count FROM transactions
          WHERE plan_id = root.plan_id AND reconciliation_session_id = root.id;
        SELECT count(*) INTO movement_count FROM posted_account_movements
          WHERE plan_id = root.plan_id AND reconciliation_session_id = root.id;
        IF root.discrepancy = 0 THEN
          IF transaction_count <> 0 OR movement_count <> 0 THEN
            RAISE EXCEPTION 'zero reconciliation cannot have an adjustment';
          END IF;
        ELSE
          IF account_status <> 'active' THEN
            RAISE EXCEPTION 'archived Accounts cannot receive reconciliation adjustments';
          END IF;
          IF transaction_count <> 1 OR movement_count <> 1 THEN
            RAISE EXCEPTION 'non-zero reconciliation requires exactly one adjustment';
          END IF;
          SELECT * INTO adjustment FROM transactions
            WHERE plan_id = root.plan_id AND reconciliation_session_id = root.id;
          SELECT * INTO movement FROM posted_account_movements
            WHERE plan_id = root.plan_id AND reconciliation_session_id = root.id;
          IF adjustment.type <> 'reconciliation_adjustment'
             OR adjustment.account_id <> root.account_id
             OR adjustment.currency_code <> root.currency_code
             OR adjustment.amount <> abs(root.discrepancy)
             OR adjustment.event_at <> root.statement_at
             OR adjustment.category_id IS NOT NULL
             OR adjustment.source <> 'reconciliation'
             OR movement.transaction_id <> adjustment.id
             OR movement.account_id <> root.account_id
             OR movement.currency_code <> root.currency_code
             OR movement.signed_amount <> root.discrepancy
             OR movement.transaction_type <> 'reconciliation_adjustment'
             OR movement.effective_at <> root.statement_at
             OR movement.category_id IS NOT NULL
             OR movement.source <> 'reconciliation'
             OR movement.movement_kind <> 'original'
             OR movement.correction_id IS NOT NULL
             OR movement.correction_sequence <> 0 THEN
            RAISE EXCEPTION 'reconciliation adjustment facts are inconsistent';
          END IF;
        END IF;
      END LOOP;
      IF EXISTS (
        SELECT 1 FROM transactions t
        WHERE t.type = 'reconciliation_adjustment'
          AND NOT EXISTS (
            SELECT 1 FROM reconciliation_sessions r
            WHERE r.plan_id = t.plan_id AND r.id = t.reconciliation_session_id
          )
      ) OR EXISTS (
        SELECT 1 FROM posted_account_movements m
        WHERE m.transaction_type = 'reconciliation_adjustment'
          AND NOT EXISTS (
            SELECT 1 FROM reconciliation_sessions r
            WHERE r.plan_id = m.plan_id AND r.id = m.reconciliation_session_id
          )
      ) THEN
        RAISE EXCEPTION 'orphan reconciliation adjustment';
      END IF;
      RETURN NULL;
    END $$;

    CREATE CONSTRAINT TRIGGER reconciliation_integrity_session
      AFTER INSERT OR UPDATE OR DELETE ON reconciliation_sessions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      EXECUTE FUNCTION numa_reconciliation_integrity();
    CREATE CONSTRAINT TRIGGER reconciliation_integrity_transaction
      AFTER INSERT OR UPDATE OR DELETE ON transactions
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      EXECUTE FUNCTION numa_reconciliation_integrity();
    CREATE CONSTRAINT TRIGGER reconciliation_integrity_movement
      AFTER INSERT OR UPDATE OR DELETE ON posted_account_movements
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
      EXECUTE FUNCTION numa_reconciliation_integrity();
    """))


def downgrade() -> None:
    op.execute(sa.text("""
    DROP TRIGGER IF EXISTS reconciliation_integrity_movement ON posted_account_movements;
    DROP TRIGGER IF EXISTS reconciliation_integrity_transaction ON transactions;
    DROP TRIGGER IF EXISTS reconciliation_integrity_session ON reconciliation_sessions;
    DROP TRIGGER IF EXISTS reconciliation_sessions_append_only ON reconciliation_sessions;
    DROP TRIGGER IF EXISTS transactions_reconciliation_append_only ON transactions;
    DROP FUNCTION IF EXISTS numa_reconciliation_integrity();
    DROP FUNCTION IF EXISTS numa_reject_reconciliation_transaction_mutation();
    DROP TRIGGER IF EXISTS posted_movements_append_only ON posted_account_movements;
    DELETE FROM posted_account_movements WHERE transaction_type = 'reconciliation_adjustment';
    DELETE FROM transactions WHERE type = 'reconciliation_adjustment';
    DELETE FROM reconciliation_sessions;
    CREATE TRIGGER posted_movements_append_only
      BEFORE UPDATE OR DELETE ON posted_account_movements FOR EACH ROW
      EXECUTE FUNCTION numa_reject_append_only_mutation();
    CREATE OR REPLACE FUNCTION numa_reject_transfer_correction()
    RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (SELECT type FROM transactions WHERE plan_id=NEW.plan_id AND id=NEW.transaction_id)='transfer' THEN
        RAISE EXCEPTION 'transfer corrections are forbidden';
      END IF;
      RETURN NEW;
    END $$;
    """))
    op.drop_constraint("ck_posted_movements_reconciliation_link", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_category_by_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_transactions_reconciliation_link", "transactions", type_="check")
    op.drop_constraint("ck_transactions_category_by_type", "transactions", type_="check")
    op.drop_constraint("ck_transactions_type", "transactions", type_="check")
    op.create_check_constraint("ck_transactions_type", "transactions", "type IN ('income', 'expense', 'transfer')")
    op.create_check_constraint("ck_transactions_category_by_type", "transactions", "(type = 'transfer' AND category_id IS NULL) OR (type IN ('income', 'expense') AND category_id IS NOT NULL)")
    op.create_check_constraint("ck_posted_movements_transaction_type", "posted_account_movements", "transaction_type IN ('income', 'expense', 'transfer')")
    op.create_check_constraint("ck_posted_movements_category_by_type", "posted_account_movements", "(transaction_type = 'transfer' AND category_id IS NULL) OR (transaction_type IN ('income', 'expense') AND category_id IS NOT NULL)")
    op.drop_constraint("uq_posted_movements_reconciliation_session", "posted_account_movements", type_="unique")
    op.drop_constraint("uq_transactions_reconciliation_session", "transactions", type_="unique")
    op.drop_constraint("fk_posted_movements_reconciliation_session_same_plan", "posted_account_movements", type_="foreignkey")
    op.drop_constraint("fk_transactions_reconciliation_session_same_plan", "transactions", type_="foreignkey")
    op.drop_column("posted_account_movements", "reconciliation_session_id")
    op.drop_column("transactions", "reconciliation_session_id")
    op.drop_index("ix_reconciliation_sessions_account_confirmed", table_name="reconciliation_sessions")
    op.drop_table("reconciliation_sessions")
