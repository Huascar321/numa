"""Create the append-only ledger and monthly budgeting baseline.

Revision ID: 003_ledger_core
Revises: 002_accounts
Create Date: 2026-08-13
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "003_ledger_core"
down_revision: str | None = "002_accounts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
MONEY = sa.Numeric(38, 18)


def upgrade() -> None:
    # The value is deliberately backfilled before the column becomes required.
    # Existing creation fingerprints are not rewritten: 002_accounts clients
    # can still replay their original Plan creation identity.
    op.add_column(
        "plans",
        sa.Column("budget_timezone", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE plans SET budget_timezone = 'America/La_Paz' "
            "WHERE budget_timezone IS NULL"
        )
    )
    op.alter_column("plans", "budget_timezone", nullable=False)
    op.create_check_constraint(
        "ck_plans_budget_timezone_nonempty",
        "plans",
        "btrim(budget_timezone) <> ''",
    )

    # Composite foreign keys are the database-level Plan-isolation boundary.
    op.create_unique_constraint(
        "uq_accounts_plan_id_id", "accounts", ["plan_id", "id"]
    )

    op.create_table(
        "category_groups",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_category_groups_name_nonempty"),
        sa.CheckConstraint(
            "status IN ('active', 'archived')",
            name="ck_category_groups_status",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_category_groups_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "id", name="uq_category_groups_plan_id_id"),
        sa.UniqueConstraint("plan_id", "name", name="uq_category_groups_plan_name"),
    )
    op.create_index("ix_category_groups_plan_id", "category_groups", ["plan_id"])

    op.create_table(
        "categories",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("group_id", UUID, nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "is_pending",
            sa.Boolean,
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_categories_name_nonempty"),
        sa.CheckConstraint(
            "status IN ('active', 'archived')", name="ck_categories_status"
        ),
        sa.CheckConstraint(
            "NOT is_pending OR (name = 'Pendientes' AND status = 'active')",
            name="ck_categories_pending_identity",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_categories_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "group_id"],
            ["category_groups.plan_id", "category_groups.id"],
            name="fk_categories_plan_group_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "id", name="uq_categories_plan_id_id"),
        sa.UniqueConstraint("plan_id", "name", name="uq_categories_plan_name"),
    )
    op.create_index(
        "uq_categories_one_pending_per_plan",
        "categories",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("is_pending"),
    )
    op.create_index("ix_categories_plan_status", "categories", ["plan_id", "status"])

    # Backfill exactly one protected category for every existing Plan. The
    # partial unique index makes a repeated execution fail rather than create a
    # second protected resource; Alembic itself executes this revision once.
    op.execute(
        sa.text(
            "INSERT INTO categories "
            "(id, plan_id, group_id, name, is_pending, status, creation_fingerprint) "
            "SELECT md5(('pending:' || id::text))::uuid, id, NULL, "
            "'Pendientes', true, 'active', md5(('pending:' || id::text)) "
            "FROM plans"
        )
    )

    op.create_table(
        "tags",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_tags_name_nonempty"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_tags_status"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_tags_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "id", name="uq_tags_plan_id_id"),
        sa.UniqueConstraint("plan_id", "name", name="uq_tags_plan_name"),
    )
    op.create_index("ix_tags_plan_status", "tags", ["plan_id", "status"])

    op.create_table(
        "transactions",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("photo_reference", sa.String(length=1024), nullable=True),
        sa.Column("location", JSONB, nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint("type IN ('income', 'expense')", name="ck_transactions_type"),
        sa.CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        sa.CheckConstraint("btrim(source) <> ''", name="ck_transactions_source_nonempty"),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_transactions_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_transactions_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_transactions_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_transactions_plan_category_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "id", name="uq_transactions_plan_id_id"),
    )
    op.create_index(
        "ix_transactions_plan_event_at", "transactions", ["plan_id", "event_at"]
    )
    op.create_index(
        "ix_transactions_plan_category_event",
        "transactions",
        ["plan_id", "category_id", "event_at"],
    )

    op.create_table(
        "transaction_corrections",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("transaction_id", UUID, nullable=False),
        sa.Column("correction_sequence", sa.BigInteger(), nullable=False),
        sa.Column("before_snapshot", JSONB, nullable=False),
        sa.Column("after_snapshot", JSONB, nullable=False),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_transaction_corrections_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_corrections_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "id", name="uq_transaction_corrections_plan_id_id"
        ),
        sa.UniqueConstraint(
            "plan_id",
            "transaction_id",
            "correction_sequence",
            name="uq_transaction_corrections_transaction_sequence",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "id",
            "correction_sequence",
            name="uq_transaction_corrections_id_sequence",
        ),
        sa.CheckConstraint(
            "correction_sequence > 0",
            name="ck_transaction_corrections_sequence_positive",
        ),
    )
    op.create_index(
        "ix_transaction_corrections_transaction",
        "transaction_corrections",
        ["plan_id", "transaction_id", "correction_sequence"],
    )

    op.create_table(
        "posted_account_movements",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("account_id", UUID, nullable=False),
        sa.Column("transaction_id", UUID, nullable=False),
        sa.Column("correction_id", UUID, nullable=True),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("signed_amount", MONEY, nullable=False),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("merchant", sa.String(length=255), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("photo_reference", sa.String(length=1024), nullable=True),
        sa.Column("location", JSONB, nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_metadata", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "movement_kind", sa.String(length=32), nullable=False
        ),
        sa.Column(
            "correction_sequence",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "signed_amount <> 0", name="ck_posted_movements_amount_nonzero"
        ),
        sa.CheckConstraint(
            "transaction_type IN ('income', 'expense')",
            name="ck_posted_movements_transaction_type",
        ),
        sa.CheckConstraint(
            "movement_kind IN ('original', 'compensation', 'replacement')",
            name="ck_posted_movements_kind",
        ),
        sa.CheckConstraint(
            "(movement_kind = 'original' AND correction_id IS NULL) OR "
            "(movement_kind <> 'original' AND correction_id IS NOT NULL)",
            name="ck_posted_movements_correction_link",
        ),
        sa.UniqueConstraint(
            "plan_id",
            "correction_id",
            "movement_kind",
            name="uq_posted_movements_correction_kind",
        ),
        sa.CheckConstraint(
            "(movement_kind = 'original' AND correction_sequence = 0) OR "
            "(movement_kind <> 'original' AND correction_sequence > 0)",
            name="ck_posted_movements_correction_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "account_id"],
            ["accounts.plan_id", "accounts.id"],
            name="fk_posted_movements_plan_account_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_posted_movements_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "correction_id"],
            ["transaction_corrections.plan_id", "transaction_corrections.id"],
            name="fk_posted_movements_plan_correction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_posted_movements_plan_category_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_posted_movements_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_posted_movements_account_effective",
        "posted_account_movements",
        ["plan_id", "account_id", "effective_at"],
    )
    op.create_index(
        "ix_posted_movements_budget",
        "posted_account_movements",
        ["plan_id", "effective_at", "category_id"],
    )

    op.create_table(
        "transaction_tags",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("transaction_id", UUID, nullable=False),
        sa.Column("tag_id", UUID, nullable=False),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("correction_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('attached', 'detached')", name="ck_transaction_tags_action"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "transaction_id"],
            ["transactions.plan_id", "transactions.id"],
            name="fk_transaction_tags_plan_transaction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "tag_id"],
            ["tags.plan_id", "tags.id"],
            name="fk_transaction_tags_plan_tag_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "correction_id"],
            ["transaction_corrections.plan_id", "transaction_corrections.id"],
            name="fk_transaction_tags_plan_correction_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_transaction_tags_current_lookup",
        "transaction_tags",
        ["plan_id", "transaction_id", "tag_id", "created_at"],
    )

    op.create_table(
        "monthly_budget_assignments",
        sa.Column("id", UUID, nullable=False),
        sa.Column("plan_id", UUID, nullable=False),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("month_key", sa.String(length=7), nullable=False),
        sa.Column("amount", MONEY, nullable=False),
        sa.Column("currency_code", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("provenance", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "month_key ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_monthly_assignments_month_key",
        ),
        sa.CheckConstraint(
            "btrim(source) <> ''", name="ck_monthly_assignments_source_nonempty"
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            name="fk_monthly_assignments_plan_id_plans",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id", "category_id"],
            ["categories.plan_id", "categories.id"],
            name="fk_monthly_assignments_plan_category_same_plan",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["currency_code"],
            ["currencies.code"],
            name="fk_monthly_assignments_currency_code_currencies",
            onupdate="RESTRICT",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id", "id", name="uq_monthly_assignments_plan_id_id"
        ),
    )
    op.create_index(
        "ix_monthly_assignments_plan_month",
        "monthly_budget_assignments",
        ["plan_id", "month_key"],
    )
    op.create_index(
        "ix_monthly_assignments_category_month",
        "monthly_budget_assignments",
        ["plan_id", "category_id", "month_key"],
    )

    # Database guards keep the append-only boundary intact even if a future
    # caller bypasses the service layer.
    op.execute(
        sa.text(
            """
            CREATE FUNCTION numa_reject_append_only_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'append-only ledger records cannot be modified';
            END;
            $$;

            CREATE FUNCTION numa_protect_budget_timezone()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NEW.budget_timezone IS DISTINCT FROM OLD.budget_timezone THEN
                RAISE EXCEPTION 'Plan budget_timezone is immutable';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_validate_plan_timezone()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_timezone_names WHERE name = NEW.budget_timezone
              ) THEN
                RAISE EXCEPTION 'budget_timezone must be a valid IANA timezone';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_protect_pending_category()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'DELETE' AND OLD.is_pending THEN
                RAISE EXCEPTION 'Pendientes is protected';
              END IF;
              IF TG_OP = 'UPDATE' AND OLD.is_pending AND (
                NEW.name IS DISTINCT FROM 'Pendientes' OR
                NEW.status IS DISTINCT FROM 'active' OR
                NEW.group_id IS NOT NULL OR
                NEW.is_pending IS DISTINCT FROM true OR
                NEW.plan_id IS DISTINCT FROM OLD.plan_id
              ) THEN
                RAISE EXCEPTION 'Pendientes is protected';
              END IF;
              IF TG_OP = 'UPDATE' AND NOT OLD.is_pending AND NEW.is_pending THEN
                RAISE EXCEPTION 'Pendientes is protected';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_guard_category_group_archive()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF TG_OP = 'UPDATE' AND OLD.status = 'active' AND NEW.status = 'archived'
                 AND EXISTS (
                   SELECT 1 FROM categories
                   WHERE plan_id = OLD.plan_id AND group_id = OLD.id AND status = 'active'
                 ) THEN
                RAISE EXCEPTION 'Category Group has active Categories';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_validate_transaction_currency()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE account_currency text; account_status text;
            BEGIN
              SELECT currency_code, status INTO account_currency, account_status FROM accounts
                WHERE plan_id = NEW.plan_id AND id = NEW.account_id;
              IF account_currency IS NULL OR NEW.currency_code <> account_currency THEN
                RAISE EXCEPTION 'Transaction currency must match Account currency';
              END IF;
              IF account_status <> 'active' THEN
                RAISE EXCEPTION 'archived Accounts reject new postings';
              END IF;
              IF NEW.source IS NULL OR btrim(NEW.source) = '' THEN
                RAISE EXCEPTION 'Transaction source is required';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_validate_movement_account()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE account_currency text; account_status text;
            BEGIN
              SELECT currency_code, status INTO account_currency, account_status FROM accounts
                WHERE plan_id = NEW.plan_id AND id = NEW.account_id;
              IF account_currency IS NULL OR NEW.currency_code <> account_currency THEN
                RAISE EXCEPTION 'Movement currency must match Account currency';
              END IF;
              IF NEW.movement_kind IN ('original', 'replacement')
                 AND account_status <> 'active' THEN
                RAISE EXCEPTION 'archived Accounts reject new postings';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE FUNCTION numa_validate_assignment_currency()
            RETURNS trigger LANGUAGE plpgsql AS $$
            DECLARE plan_currency text;
            BEGIN
              SELECT reporting_currency_code INTO plan_currency FROM plans
                WHERE id = NEW.plan_id;
              IF plan_currency IS NULL OR NEW.currency_code <> plan_currency THEN
                RAISE EXCEPTION 'Assignment currency must match Plan budget currency';
              END IF;
              RETURN NEW;
            END;
            $$;

            CREATE TRIGGER plans_budget_timezone_immutable
              BEFORE UPDATE ON plans FOR EACH ROW
              EXECUTE FUNCTION numa_protect_budget_timezone();
            CREATE TRIGGER plans_budget_timezone_valid
              BEFORE INSERT OR UPDATE ON plans FOR EACH ROW
              EXECUTE FUNCTION numa_validate_plan_timezone();
            CREATE TRIGGER categories_pending_protection
              BEFORE UPDATE OR DELETE ON categories FOR EACH ROW
              EXECUTE FUNCTION numa_protect_pending_category();
            CREATE TRIGGER category_groups_archive_guard
              BEFORE UPDATE ON category_groups FOR EACH ROW
              EXECUTE FUNCTION numa_guard_category_group_archive();
            CREATE TRIGGER transactions_currency_guard
              BEFORE INSERT OR UPDATE ON transactions FOR EACH ROW
              EXECUTE FUNCTION numa_validate_transaction_currency();
            CREATE TRIGGER posted_movements_account_guard
              BEFORE INSERT ON posted_account_movements FOR EACH ROW
              EXECUTE FUNCTION numa_validate_movement_account();
            CREATE TRIGGER assignments_currency_guard
              BEFORE INSERT OR UPDATE ON monthly_budget_assignments FOR EACH ROW
              EXECUTE FUNCTION numa_validate_assignment_currency();
            CREATE TRIGGER posted_movements_append_only
              BEFORE UPDATE OR DELETE ON posted_account_movements FOR EACH ROW
              EXECUTE FUNCTION numa_reject_append_only_mutation();
            CREATE TRIGGER corrections_append_only
              BEFORE UPDATE OR DELETE ON transaction_corrections FOR EACH ROW
              EXECUTE FUNCTION numa_reject_append_only_mutation();
            CREATE TRIGGER transaction_tags_append_only
              BEFORE UPDATE OR DELETE ON transaction_tags FOR EACH ROW
              EXECUTE FUNCTION numa_reject_append_only_mutation();
            CREATE TRIGGER assignments_append_only
              BEFORE UPDATE OR DELETE ON monthly_budget_assignments FOR EACH ROW
              EXECUTE FUNCTION numa_reject_append_only_mutation();
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DROP TRIGGER IF EXISTS assignments_append_only ON monthly_budget_assignments;
            DROP TRIGGER IF EXISTS transaction_tags_append_only ON transaction_tags;
            DROP TRIGGER IF EXISTS corrections_append_only ON transaction_corrections;
            DROP TRIGGER IF EXISTS posted_movements_append_only ON posted_account_movements;
            DROP TRIGGER IF EXISTS assignments_currency_guard ON monthly_budget_assignments;
            DROP TRIGGER IF EXISTS transactions_currency_guard ON transactions;
            DROP TRIGGER IF EXISTS posted_movements_account_guard ON posted_account_movements;
            DROP TRIGGER IF EXISTS category_groups_archive_guard ON category_groups;
            DROP TRIGGER IF EXISTS categories_pending_protection ON categories;
            DROP TRIGGER IF EXISTS plans_budget_timezone_immutable ON plans;
            DROP TRIGGER IF EXISTS plans_budget_timezone_valid ON plans;
            DROP FUNCTION IF EXISTS numa_validate_assignment_currency();
            DROP FUNCTION IF EXISTS numa_validate_transaction_currency();
            DROP FUNCTION IF EXISTS numa_validate_movement_account();
            DROP FUNCTION IF EXISTS numa_guard_category_group_archive();
            DROP FUNCTION IF EXISTS numa_protect_pending_category();
            DROP FUNCTION IF EXISTS numa_protect_budget_timezone();
            DROP FUNCTION IF EXISTS numa_validate_plan_timezone();
            DROP FUNCTION IF EXISTS numa_reject_append_only_mutation();
            """
        )
    )
    op.drop_index("ix_monthly_assignments_category_month", table_name="monthly_budget_assignments")
    op.drop_index("ix_monthly_assignments_plan_month", table_name="monthly_budget_assignments")
    op.drop_table("monthly_budget_assignments")
    op.drop_index("ix_transaction_tags_current_lookup", table_name="transaction_tags")
    op.drop_table("transaction_tags")
    op.drop_index("ix_posted_movements_budget", table_name="posted_account_movements")
    op.drop_index("ix_posted_movements_account_effective", table_name="posted_account_movements")
    op.drop_table("posted_account_movements")
    op.drop_index("ix_transaction_corrections_transaction", table_name="transaction_corrections")
    op.drop_table("transaction_corrections")
    op.drop_index("ix_transactions_plan_category_event", table_name="transactions")
    op.drop_index("ix_transactions_plan_event_at", table_name="transactions")
    op.drop_table("transactions")
    op.drop_index("ix_tags_plan_status", table_name="tags")
    op.drop_table("tags")
    op.drop_index("ix_categories_plan_status", table_name="categories")
    op.drop_index("uq_categories_one_pending_per_plan", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_category_groups_plan_id", table_name="category_groups")
    op.drop_table("category_groups")
    op.drop_constraint("uq_accounts_plan_id_id", "accounts", type_="unique")
    op.drop_constraint("ck_plans_budget_timezone_nonempty", "plans", type_="check")
    op.drop_column("plans", "budget_timezone")
