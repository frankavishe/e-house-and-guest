"""Booking events, lease installments, payments, refunds, the ledger and idempotency keys
(T074, R6, R8).

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


actor_kind = enum("actor_kind", "user", "system", "provider")
installment_status = enum("installment_status", "pending", "paid", "overdue", "waived")
payment_status = enum("payment_status", "pending", "succeeded", "failed", "expired")
refund_reason = enum(
    "refund_reason", "cancellation", "deposit_return", "owner_cancel", "admin", "late_payment"
)
refund_status = enum("refund_status", "pending", "sent", "failed")
ledger_entry_type = enum(
    "ledger_entry_type",
    "payment", "commission", "deposit_hold", "deposit_release", "refund", "payout", "adjustment",
)
NEW_ENUMS = (
    actor_kind, installment_status, payment_status, refund_reason, refund_status,
    ledger_entry_type,
)
# Created in 0005/0006.
booking_status = postgresql.ENUM(name="booking_status", create_type=False)
payment_network = postgresql.ENUM(name="payment_network", create_type=False)


def created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def timestamps() -> list[sa.Column]:
    return [
        created_at(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


# asyncpg runs one statement per call.
LEDGER_TRIGGERS = [
    """
    CREATE FUNCTION ledger_txn_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE total bigint;
    BEGIN
        SELECT COALESCE(SUM(amount_tzs), 0) INTO total
            FROM ledger_entries WHERE txn_id = NEW.txn_id;
        IF total <> 0 THEN
            RAISE EXCEPTION 'ledger txn % is unbalanced (sum %)', NEW.txn_id, total
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NULL;
    END $$
    """,
    """
    CREATE CONSTRAINT TRIGGER ledger_entries_balanced
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION ledger_txn_balanced()
    """,
    """
    CREATE FUNCTION ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'ledger_entries is append-only (% rejected)', TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END $$
    """,
    """
    CREATE TRIGGER ledger_entries_append_only
        BEFORE UPDATE OR DELETE ON ledger_entries
        FOR EACH ROW EXECUTE FUNCTION ledger_append_only()
    """,
]


def upgrade() -> None:
    bind = op.get_bind()
    for e in NEW_ENUMS:
        e.create(bind, checkfirst=True)

    op.create_table(
        "booking_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", booking_status),
        sa.Column("to_status", booking_status, nullable=False),
        sa.Column("actor_user_id", sa.Uuid()),
        sa.Column("actor_kind", actor_kind, nullable=False),
        sa.Column("note", sa.Text()),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_booking_events"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE",
                                name="fk_booking_events_booking_id_bookings"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"],
                                name="fk_booking_events_actor_user_id_users"),
    )
    op.create_index("ix_booking_events_booking_id", "booking_events", ["booking_id"])

    op.create_table(
        "lease_installments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("period", postgresql.TSTZRANGE(), nullable=False),
        sa.Column("rental_tzs", sa.BigInteger(), nullable=False),
        sa.Column("service_fee_tzs", sa.BigInteger(), nullable=False),
        sa.Column("commission_tzs", sa.BigInteger(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", installment_status, nullable=False),
        sa.Column("payment_id", sa.Uuid()),
        sa.Column("billed_at", sa.DateTime(timezone=True)),
        sa.Column("reminded_at", sa.DateTime(timezone=True)),
        sa.Column("overdue_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_lease_installments"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="CASCADE",
                                name="fk_lease_installments_booking_id_bookings"),
        sa.UniqueConstraint("booking_id", "seq", name="uq_lease_installments_booking_id_seq"),
        sa.CheckConstraint("seq >= 1", name="seq_positive"),
        sa.CheckConstraint("amount_tzs = rental_tzs + service_fee_tzs", name="amount_sum"),
    )
    op.create_index(
        "ix_lease_installments_status_due_at", "lease_installments", ["status", "due_at"]
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("lease_installment_id", sa.Uuid()),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("network", payment_network, nullable=False),
        sa.Column("msisdn", sa.Text(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("provider_txn_id", sa.Text()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_payments_booking_id_bookings"),
        sa.ForeignKeyConstraint(["lease_installment_id"], ["lease_installments.id"],
                                name="fk_payments_lease_installment_id_lease_installments"),
        sa.UniqueConstraint("provider", "provider_txn_id", name="uq_payments_provider_txn"),
        sa.CheckConstraint("amount_tzs > 0", name="amount_positive"),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
    op.create_index("ix_payments_status_created_at", "payments", ["status", "created_at"])
    op.create_index(
        "uq_payments_one_pending",
        "payments",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_foreign_key(
        "fk_lease_installments_payment_id_payments",
        "lease_installments",
        "payments",
        ["payment_id"],
        ["id"],
    )

    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("payment_id", sa.Uuid()),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_payment_events"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"],
                                name="fk_payment_events_payment_id_payments"),
        sa.UniqueConstraint("provider", "provider_event_id",
                            name="uq_payment_events_provider_event"),
    )

    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("reason", refund_reason, nullable=False),
        sa.Column("status", refund_status, nullable=False),
        sa.Column("provider_ref", sa.Text()),
        sa.Column("failure_reason", sa.Text()),
        sa.Column("created_by", sa.Uuid()),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_refunds_booking_id_bookings"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"],
                                name="fk_refunds_payment_id_payments"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_refunds_created_by_users"),
        sa.CheckConstraint("amount_tzs > 0", name="amount_positive"),
    )
    op.create_index("ix_refunds_booking_id", "refunds", ["booking_id"])
    op.create_index("ix_refunds_payment_id", "refunds", ["payment_id"])

    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("txn_id", sa.Uuid(), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("amount_tzs", sa.BigInteger(), nullable=False),
        sa.Column("entry_type", ledger_entry_type, nullable=False),
        sa.Column("booking_id", sa.Uuid()),
        sa.Column("payment_id", sa.Uuid()),
        sa.Column("refund_id", sa.Uuid()),
        sa.Column("payout_id", sa.Uuid()),
        created_at(),
        sa.PrimaryKeyConstraint("id", name="pk_ledger_entries"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"],
                                name="fk_ledger_entries_booking_id_bookings"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"],
                                name="fk_ledger_entries_payment_id_payments"),
        sa.ForeignKeyConstraint(["refund_id"], ["refunds.id"],
                                name="fk_ledger_entries_refund_id_refunds"),
        sa.CheckConstraint("amount_tzs <> 0", name="amount_non_zero"),
    )
    op.create_index("ix_ledger_entries_txn_id", "ledger_entries", ["txn_id"])
    op.create_index("ix_ledger_entries_booking_id", "ledger_entries", ["booking_id"])
    op.create_index("ix_ledger_entries_account", "ledger_entries", ["account"])
    for statement in LEDGER_TRIGGERS:
        op.execute(statement)

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", postgresql.JSONB(), nullable=False),
        created_at(),
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE",
                                name="fk_idempotency_keys_user_id_users"),
    )


def downgrade() -> None:
    op.drop_table("idempotency_keys")
    op.execute("DROP TABLE ledger_entries")
    op.execute("DROP FUNCTION ledger_append_only()")
    op.execute("DROP FUNCTION ledger_txn_balanced()")
    op.drop_table("refunds")
    op.drop_table("payment_events")
    op.drop_constraint(
        "fk_lease_installments_payment_id_payments", "lease_installments", type_="foreignkey"
    )
    op.drop_table("payments")
    op.drop_table("lease_installments")
    op.drop_table("booking_events")
    bind = op.get_bind()
    for e in reversed(NEW_ENUMS):
        e.drop(bind, checkfirst=True)
