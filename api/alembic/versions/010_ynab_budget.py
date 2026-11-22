"""Protected card payment categories and immutable budget action receipts."""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "010_ynab_budget"
down_revision: str | None = "009_watcher_runs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("categories", sa.Column("payment_account_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_categories_payment_account", "categories", "accounts",
                          ["plan_id", "payment_account_id"], ["plan_id", "id"])
    op.create_unique_constraint("uq_categories_payment_account", "categories", ["payment_account_id"])
    op.create_check_constraint("ck_categories_payment_identity", "categories",
        "payment_account_id IS NULL OR (NOT is_pending AND status = 'active' AND group_id IS NULL AND goal_type IS NULL)")
    op.execute("""
      INSERT INTO categories (id, plan_id, name, is_pending, status, creation_fingerprint, payment_account_id)
      SELECT md5('card-payment:' || a.id::text)::uuid, a.plan_id,
             'Card payment · ' || a.id::text, false, 'active',
             md5('card-payment:' || a.id::text), a.id
      FROM accounts a JOIN plans p ON p.id = a.plan_id
      WHERE a.account_type = 'Credit Card' AND a.currency_code = p.reporting_currency_code;
      CREATE FUNCTION numa_protect_payment_category() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF TG_OP = 'DELETE' THEN
          IF OLD.payment_account_id IS NOT NULL THEN RAISE EXCEPTION 'payment category is protected'; END IF;
          RETURN OLD;
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.payment_account_id IS DISTINCT FROM NEW.payment_account_id THEN
          RAISE EXCEPTION 'payment category identity is immutable';
        END IF;
        IF TG_OP = 'UPDATE' AND OLD.payment_account_id IS NOT NULL AND (
          NEW.id IS DISTINCT FROM OLD.id OR NEW.plan_id IS DISTINCT FROM OLD.plan_id OR
          NEW.name IS DISTINCT FROM OLD.name OR NEW.is_pending IS DISTINCT FROM OLD.is_pending
        ) THEN RAISE EXCEPTION 'payment category is protected'; END IF;
        IF NEW.payment_account_id IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM accounts a JOIN plans p ON p.id = a.plan_id
          WHERE a.id = NEW.payment_account_id AND a.plan_id = NEW.plan_id
            AND a.account_type = 'Credit Card' AND a.currency_code = p.reporting_currency_code
        ) THEN RAISE EXCEPTION 'payment category requires a budget currency credit card'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER categories_payment_guard BEFORE INSERT OR UPDATE OR DELETE ON categories
        FOR EACH ROW EXECUTE FUNCTION numa_protect_payment_category();
      CREATE FUNCTION numa_reject_payment_categorization() RETURNS trigger LANGUAGE plpgsql AS $$
      BEGIN
        IF EXISTS (SELECT 1 FROM categories WHERE id = NEW.category_id AND payment_account_id IS NOT NULL)
          THEN RAISE EXCEPTION 'payment categories cannot categorize transactions'; END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER transactions_payment_category_guard BEFORE INSERT OR UPDATE ON transactions
        FOR EACH ROW EXECUTE FUNCTION numa_reject_payment_categorization();
    """)
    op.create_table("budget_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(64), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.execute("""CREATE TRIGGER budget_actions_append_only BEFORE UPDATE OR DELETE ON budget_actions
      FOR EACH ROW EXECUTE FUNCTION numa_reject_append_only_mutation();""")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM budget_actions) OR EXISTS ("
        "SELECT 1 FROM monthly_budget_assignments a JOIN categories c ON c.id=a.category_id "
        "WHERE c.payment_account_id IS NOT NULL)")):
        raise RuntimeError("Cannot discard budget action or payment funding history; restore a compatible version instead.")
    op.drop_table("budget_actions")
    op.execute("DROP TRIGGER transactions_payment_category_guard ON transactions; DROP FUNCTION numa_reject_payment_categorization(); DROP TRIGGER categories_payment_guard ON categories; DROP FUNCTION numa_protect_payment_category();")
    op.execute("DELETE FROM categories WHERE payment_account_id IS NOT NULL")
    op.drop_constraint("ck_categories_payment_identity", "categories")
    op.drop_constraint("uq_categories_payment_account", "categories")
    op.drop_constraint("fk_categories_payment_account", "categories")
    op.drop_column("categories", "payment_account_id")
