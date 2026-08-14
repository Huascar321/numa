"""Add immutable, paired transfer roots.

Revision ID: 004_transfers
Revises: 003_ledger_core
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004_transfers"
down_revision: str | None = "003_ledger_core"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # Ledger-core's category foreign keys already permit NULL, but its columns
    # did not.  A transfer has no category on either its leg or movement.
    op.alter_column("transactions", "category_id", nullable=True)
    op.alter_column("posted_account_movements", "category_id", nullable=True)
    op.drop_constraint("ck_transactions_type", "transactions", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.create_check_constraint("ck_transactions_type", "transactions", "type IN ('income', 'expense', 'transfer')")
    op.create_check_constraint("ck_transactions_amount_finite", "transactions", "amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)")
    op.create_check_constraint("ck_transactions_category_by_type", "transactions", "(type = 'transfer' AND category_id IS NULL) OR (type IN ('income', 'expense') AND category_id IS NOT NULL)")
    op.create_check_constraint("ck_posted_movements_transaction_type", "posted_account_movements", "transaction_type IN ('income', 'expense', 'transfer')")
    op.create_check_constraint("ck_posted_movements_amount_finite", "posted_account_movements", "signed_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)")
    op.create_check_constraint("ck_posted_movements_category_by_type", "posted_account_movements", "(transaction_type = 'transfer' AND category_id IS NULL) OR (transaction_type IN ('income', 'expense') AND category_id IS NOT NULL)")

    op.create_table(
        "transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbound_amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("outbound_currency_code", sa.String(16), nullable=False),
        sa.Column("inbound_amount", sa.Numeric(38, 18), nullable=False),
        sa.Column("inbound_currency_code", sa.String(16), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rate", sa.Numeric(76, 38), nullable=False),
        sa.Column("rate_source", sa.Text(), nullable=True),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("reversal_reason", sa.Text(), nullable=True),
        sa.Column("provenance", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("creation_fingerprint", sa.String(64), nullable=False),
        sa.Column("reverses_transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("source_account_id <> destination_account_id", name="ck_transfers_distinct_accounts"),
        sa.CheckConstraint("id <> reverses_transfer_id OR reverses_transfer_id IS NULL", name="ck_transfers_no_self_reversal"),
        sa.CheckConstraint("outbound_amount > 0 AND inbound_amount > 0", name="ck_transfers_amounts_positive"),
        sa.CheckConstraint("outbound_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND inbound_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND rate NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric)", name="ck_transfers_amounts_finite"),
        sa.CheckConstraint("rate > 0", name="ck_transfers_rate_positive"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], name="fk_transfers_plan", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id", "source_account_id"], ["accounts.plan_id", "accounts.id"], name="fk_transfers_source_account_same_plan", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id", "destination_account_id"], ["accounts.plan_id", "accounts.id"], name="fk_transfers_destination_account_same_plan", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["outbound_currency_code"], ["currencies.code"], name="fk_transfers_outbound_currency"),
        sa.ForeignKeyConstraint(["inbound_currency_code"], ["currencies.code"], name="fk_transfers_inbound_currency"),
        sa.ForeignKeyConstraint(["plan_id", "reverses_transfer_id"], ["transfers.plan_id", "transfers.id"], name="fk_transfers_reversal_same_plan", deferrable=True, initially="DEFERRED"),
        sa.UniqueConstraint("plan_id", "id", name="uq_transfers_plan_id_id"),
        sa.UniqueConstraint("plan_id", "reverses_transfer_id", name="uq_transfers_direct_reversal"),
    )
    op.create_index("ix_transfers_plan_event", "transfers", ["plan_id", "event_at"])
    op.create_index("ix_transfers_plan_reversal", "transfers", ["plan_id", "reverses_transfer_id"])
    op.create_table(
        "transfer_legs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role IN ('outbound', 'inbound')", name="ck_transfer_legs_role"),
        sa.ForeignKeyConstraint(["plan_id", "transfer_id"], ["transfers.plan_id", "transfers.id"], name="fk_transfer_legs_transfer_same_plan", deferrable=True, initially="DEFERRED", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["plan_id", "transaction_id"], ["transactions.plan_id", "transactions.id"], name="fk_transfer_legs_transaction_same_plan", deferrable=True, initially="DEFERRED", ondelete="RESTRICT"),
        sa.UniqueConstraint("plan_id", "transfer_id", "role", name="uq_transfer_legs_transfer_role"),
        sa.UniqueConstraint("plan_id", "transaction_id", name="uq_transfer_legs_transaction"),
    )
    op.create_index("ix_transfer_legs_plan_transfer", "transfer_legs", ["plan_id", "transfer_id"])

    op.execute(sa.text("""
    DO $$ BEGIN
      IF current_setting('server_encoding') <> 'UTF8' THEN RAISE EXCEPTION '004_transfers requires UTF8'; END IF;
    END $$;
    CREATE FUNCTION numa_unicode_codepoint(value text) RETURNS integer
    LANGUAGE plpgsql IMMUTABLE STRICT AS $$
    DECLARE bytes bytea; first integer;
    BEGIN
      bytes := convert_to(value, 'UTF8'); first := get_byte(bytes, 0);
      IF first < 128 THEN RETURN first; END IF;
      IF first < 224 THEN RETURN ((first & 31) << 6) + (get_byte(bytes, 1) & 63); END IF;
      IF first < 240 THEN RETURN ((first & 15) << 12) + ((get_byte(bytes, 1) & 63) << 6) + (get_byte(bytes, 2) & 63); END IF;
      RETURN ((first & 7) << 18) + ((get_byte(bytes, 1) & 63) << 12) + ((get_byte(bytes, 2) & 63) << 6) + (get_byte(bytes, 3) & 63);
    END $$;
    CREATE FUNCTION canonical_transfer_text(value text) RETURNS text
    LANGUAGE plpgsql IMMUTABLE AS $$
    DECLARE result text; i integer; cp integer;
    BEGIN
      IF value IS NULL THEN RETURN NULL; END IF;
      result := btrim(normalize(value, NFC), U&'\\0020');
      FOR i IN 1..char_length(result) LOOP
        cp := numa_unicode_codepoint(substring(result FROM i FOR 1));
        IF cp BETWEEN 0 AND 31 OR cp = 127 OR cp BETWEEN 128 AND 159 THEN
          RAISE EXCEPTION 'transfer text contains a forbidden control character';
        END IF;
      END LOOP;
      RETURN result;
    END $$;
    CREATE FUNCTION numa_transfer_text_before_insert() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      NEW.memo := canonical_transfer_text(NEW.memo);
      NEW.reversal_reason := canonical_transfer_text(NEW.reversal_reason);
      NEW.rate_source := canonical_transfer_text(NEW.rate_source);
      IF NEW.memo = '' THEN NEW.memo := NULL; END IF;
      IF NEW.memo IS NOT NULL AND char_length(NEW.memo) > 2000 THEN RAISE EXCEPTION 'memo is too long'; END IF;
      IF (NEW.reverses_transfer_id IS NULL) <> (NEW.reversal_reason IS NULL)
         OR (NEW.reversal_reason IS NOT NULL AND (NEW.reversal_reason = '' OR char_length(NEW.reversal_reason) > 500)) THEN RAISE EXCEPTION 'invalid reversal_reason'; END IF;
      IF NEW.outbound_currency_code = NEW.inbound_currency_code THEN
        IF NEW.rate_source IS NOT NULL THEN RAISE EXCEPTION 'same-currency transfer has no rate source'; END IF;
      ELSIF NEW.rate_source IS NULL OR NEW.rate_source = '' OR char_length(NEW.rate_source) > 128 THEN RAISE EXCEPTION 'cross-currency transfer requires rate source'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER transfers_text_before_insert BEFORE INSERT ON transfers FOR EACH ROW EXECUTE FUNCTION numa_transfer_text_before_insert();
    ALTER TABLE transfers ADD CONSTRAINT ck_transfers_canonical_text CHECK (
      (memo IS NULL OR (memo = canonical_transfer_text(memo) AND char_length(memo) BETWEEN 1 AND 2000)) AND
       ((reverses_transfer_id IS NULL AND reversal_reason IS NULL) OR (reverses_transfer_id IS NOT NULL AND reversal_reason IS NOT NULL AND reversal_reason = canonical_transfer_text(reversal_reason) AND char_length(reversal_reason) BETWEEN 1 AND 500)) AND
       ((outbound_currency_code = inbound_currency_code AND rate_source IS NULL) OR (outbound_currency_code <> inbound_currency_code AND rate_source IS NOT NULL AND rate_source = canonical_transfer_text(rate_source) AND char_length(rate_source) BETWEEN 1 AND 128))
    );
    CREATE FUNCTION numa_transfer_rate(outbound numeric, inbound numeric) RETURNS numeric LANGUAGE plpgsql IMMUTABLE AS $$
     DECLARE a numeric; b numeric; p numeric; q numeric; r numeric;
     BEGIN
       a := outbound * 1000000000000000000; b := inbound * 1000000000000000000;
       p := a * 100000000000000000000000000000000000000;
       -- div/mod operate on the integer amount units directly.  Do not divide
       -- to a rounded numeric decimal before applying the half-even decision.
       q := div(p, b);
       r := mod(p, b);
      IF 2*r > b OR (2*r = b AND mod(q, 2) = 1) THEN q := q + 1; END IF;
       RETURN (q * '0.00000000000000000000000000000000000001'::numeric(76,38))::numeric(76,38);
    END $$;
    CREATE FUNCTION numa_transfer_integrity() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE root record; leg_count integer; movement_count integer; ttype text; mov record; parent record;
    BEGIN
      -- Validate all affected durable transfer facts at commit.  This deliberately
      -- scans the small transfer relation so INSERT ordering is unconstrained.
      FOR root IN SELECT * FROM transfers LOOP
        IF root.outbound_amount <> trunc(root.outbound_amount, (SELECT c.decimal_places FROM accounts a JOIN currencies c ON c.code=a.currency_code WHERE a.plan_id=root.plan_id AND a.id=root.source_account_id))
           OR root.inbound_amount <> trunc(root.inbound_amount, (SELECT c.decimal_places FROM accounts a JOIN currencies c ON c.code=a.currency_code WHERE a.plan_id=root.plan_id AND a.id=root.destination_account_id)) THEN RAISE EXCEPTION 'transfer originals exceed Account currency scale'; END IF;
        SELECT count(*) INTO leg_count FROM transfer_legs WHERE plan_id=root.plan_id AND transfer_id=root.id;
        IF leg_count <> 2 OR NOT EXISTS(SELECT 1 FROM transfer_legs WHERE plan_id=root.plan_id AND transfer_id=root.id AND role='outbound') OR NOT EXISTS(SELECT 1 FROM transfer_legs WHERE plan_id=root.plan_id AND transfer_id=root.id AND role='inbound') THEN RAISE EXCEPTION 'transfer must have exactly outbound and inbound legs'; END IF;
        IF root.outbound_currency_code = root.inbound_currency_code AND root.outbound_amount <> root.inbound_amount THEN RAISE EXCEPTION 'same-currency transfer originals must match'; END IF;
        IF root.rate <> (CASE WHEN root.outbound_currency_code=root.inbound_currency_code THEN 1::numeric ELSE numa_transfer_rate(root.outbound_amount, root.inbound_amount) END) THEN RAISE EXCEPTION 'transfer rate is inconsistent'; END IF;
        FOR mov IN SELECT l.role, t.*, m.id movement_id, m.account_id movement_account, m.currency_code movement_currency, m.signed_amount, m.transaction_type, m.effective_at, m.category_id movement_category, m.movement_kind, m.correction_id, m.correction_sequence FROM transfer_legs l JOIN transactions t ON (t.plan_id=l.plan_id AND t.id=l.transaction_id) LEFT JOIN posted_account_movements m ON (m.plan_id=t.plan_id AND m.transaction_id=t.id) WHERE l.plan_id=root.plan_id AND l.transfer_id=root.id LOOP
          SELECT count(*) INTO movement_count FROM posted_account_movements WHERE plan_id=mov.plan_id AND transaction_id=mov.id;
          IF movement_count <> 1 THEN RAISE EXCEPTION 'transfer leg must own exactly one movement'; END IF;
          IF mov.type <> 'transfer' OR mov.category_id IS NOT NULL OR mov.movement_id IS NULL OR mov.transaction_type <> 'transfer' OR mov.movement_category IS NOT NULL OR mov.movement_kind <> 'original' OR mov.correction_id IS NOT NULL OR mov.correction_sequence <> 0 OR mov.event_at <> root.event_at OR mov.effective_at <> root.event_at THEN RAISE EXCEPTION 'invalid transfer leg'; END IF;
          IF mov.role='outbound' AND (mov.account_id<>root.source_account_id OR mov.currency_code<>root.outbound_currency_code OR mov.amount<>root.outbound_amount OR mov.movement_account<>root.source_account_id OR mov.movement_currency<>root.outbound_currency_code OR mov.signed_amount<>-root.outbound_amount) THEN RAISE EXCEPTION 'invalid outbound leg'; END IF;
          IF mov.role='inbound' AND (mov.account_id<>root.destination_account_id OR mov.currency_code<>root.inbound_currency_code OR mov.amount<>root.inbound_amount OR mov.movement_account<>root.destination_account_id OR mov.movement_currency<>root.inbound_currency_code OR mov.signed_amount<>root.inbound_amount) THEN RAISE EXCEPTION 'invalid inbound leg'; END IF;
        END LOOP;
        IF root.reverses_transfer_id IS NOT NULL THEN
          SELECT * INTO parent FROM transfers WHERE plan_id=root.plan_id AND id=root.reverses_transfer_id;
          IF NOT FOUND OR root.source_account_id<>parent.destination_account_id OR root.destination_account_id<>parent.source_account_id OR root.outbound_amount<>parent.inbound_amount OR root.inbound_amount<>parent.outbound_amount OR root.outbound_currency_code<>parent.inbound_currency_code OR root.inbound_currency_code<>parent.outbound_currency_code OR (root.outbound_currency_code<>root.inbound_currency_code AND root.rate_source<>'reversal') THEN RAISE EXCEPTION 'reversal must exactly compensate its parent'; END IF;
        END IF;
      END LOOP;
      IF EXISTS (SELECT 1 FROM transactions t WHERE t.type='transfer' AND NOT EXISTS (SELECT 1 FROM transfer_legs l WHERE l.plan_id=t.plan_id AND l.transaction_id=t.id)) THEN RAISE EXCEPTION 'orphan transfer transaction'; END IF;
      IF EXISTS (SELECT 1 FROM posted_account_movements m JOIN transactions t ON(t.plan_id=m.plan_id AND t.id=m.transaction_id) WHERE m.transaction_type<>t.type OR (m.transaction_type='transfer' AND NOT EXISTS(SELECT 1 FROM transfer_legs l WHERE l.plan_id=m.plan_id AND l.transaction_id=m.transaction_id))) THEN RAISE EXCEPTION 'movement classifier or transfer ownership mismatch'; END IF;
      IF EXISTS (SELECT 1 FROM transaction_corrections c JOIN transactions t ON(t.plan_id=c.plan_id AND t.id=c.transaction_id) WHERE t.type='transfer') THEN RAISE EXCEPTION 'transfer corrections are forbidden'; END IF;
      RETURN NULL;
    END $$;
    CREATE CONSTRAINT TRIGGER transfers_integrity_root AFTER INSERT OR UPDATE OR DELETE ON transfers DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION numa_transfer_integrity();
    CREATE CONSTRAINT TRIGGER transfers_integrity_leg AFTER INSERT OR UPDATE OR DELETE ON transfer_legs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION numa_transfer_integrity();
    CREATE CONSTRAINT TRIGGER transfers_integrity_transaction AFTER INSERT OR UPDATE OR DELETE ON transactions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION numa_transfer_integrity();
    CREATE CONSTRAINT TRIGGER transfers_integrity_movement AFTER INSERT OR UPDATE OR DELETE ON posted_account_movements DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION numa_transfer_integrity();
    CREATE FUNCTION numa_reject_transfer_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF TG_TABLE_NAME IN ('transfers','transfer_legs') OR OLD.type='transfer' THEN RAISE EXCEPTION 'transfer records are append-only'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER transfers_append_only BEFORE UPDATE OR DELETE ON transfers FOR EACH ROW EXECUTE FUNCTION numa_reject_transfer_mutation();
    CREATE TRIGGER transfer_legs_append_only BEFORE UPDATE OR DELETE ON transfer_legs FOR EACH ROW EXECUTE FUNCTION numa_reject_transfer_mutation();
    CREATE TRIGGER transactions_transfer_append_only BEFORE UPDATE OR DELETE ON transactions FOR EACH ROW EXECUTE FUNCTION numa_reject_transfer_mutation();
    CREATE FUNCTION numa_reject_transfer_correction() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF (SELECT type FROM transactions WHERE plan_id=NEW.plan_id AND id=NEW.transaction_id)='transfer' THEN RAISE EXCEPTION 'transfer corrections are forbidden'; END IF; RETURN NEW; END $$;
    CREATE TRIGGER transaction_corrections_transfer_guard BEFORE INSERT ON transaction_corrections FOR EACH ROW EXECUTE FUNCTION numa_reject_transfer_correction();
    """))


def downgrade() -> None:
    op.execute(sa.text("""
    DROP TRIGGER IF EXISTS transaction_corrections_transfer_guard ON transaction_corrections;
    DROP TRIGGER IF EXISTS transactions_transfer_append_only ON transactions;
    DROP TRIGGER IF EXISTS transfer_legs_append_only ON transfer_legs;
    DROP TRIGGER IF EXISTS transfers_append_only ON transfers;
    DROP TRIGGER IF EXISTS transfers_integrity_movement ON posted_account_movements;
    DROP TRIGGER IF EXISTS transfers_integrity_transaction ON transactions;
    DROP TRIGGER IF EXISTS transfers_integrity_leg ON transfer_legs;
    DROP TRIGGER IF EXISTS transfers_integrity_root ON transfers;
    DROP TRIGGER IF EXISTS transfers_text_before_insert ON transfers;
    DROP FUNCTION IF EXISTS numa_reject_transfer_correction(); DROP FUNCTION IF EXISTS numa_reject_transfer_mutation();
    DROP FUNCTION IF EXISTS numa_transfer_integrity(); DROP FUNCTION IF EXISTS numa_transfer_rate(numeric,numeric);
    DROP FUNCTION IF EXISTS numa_transfer_text_before_insert(); DROP FUNCTION IF EXISTS canonical_transfer_text(text); DROP FUNCTION IF EXISTS numa_unicode_codepoint(text);
    """))
    op.drop_table("transfer_legs"); op.drop_table("transfers")
    op.drop_constraint("ck_posted_movements_category_by_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_amount_finite", "posted_account_movements", type_="check")
    op.drop_constraint("ck_posted_movements_transaction_type", "posted_account_movements", type_="check")
    op.drop_constraint("ck_transactions_category_by_type", "transactions", type_="check")
    op.drop_constraint("ck_transactions_amount_finite", "transactions", type_="check")
    op.drop_constraint("ck_transactions_type", "transactions", type_="check")
    op.create_check_constraint("ck_transactions_type", "transactions", "type IN ('income', 'expense')")
    op.create_check_constraint("ck_posted_movements_transaction_type", "posted_account_movements", "transaction_type IN ('income', 'expense')")
    op.alter_column("transactions", "category_id", nullable=False)
    op.alter_column("posted_account_movements", "category_id", nullable=False)
