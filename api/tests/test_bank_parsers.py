from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.watchers.bcp_qr import parse_bcp_qr_message
from app.watchers.ganadero import decode_rfc2047, parse_banco_ganadero_message
from app.watchers.models import WatcherRawMessage


def make_raw_message(
    sender: str,
    subject: str,
    body_plain: str | None = None,
    body_html: str | None = None,
    date_header: str = "Mon, 24 Aug 2026 14:31:00 -0400",
    message_id_header: str = "<test-notice@example.com>",
) -> WatcherRawMessage:
    return WatcherRawMessage(
        id=uuid4(),
        plan_id=uuid4(),
        source_id=uuid4(),
        external_message_id="ext-msg-1",
        external_thread_id="thread-1",
        internal_date=datetime(2026, 8, 24, 18, 31, 0, tzinfo=timezone.utc),
        history_id="100",
        sender=sender,
        recipient="user@example.com",
        subject=subject,
        snippet="Notice snippet",
        raw_headers={
            "from": sender,
            "subject": subject,
            "date": date_header,
            "message-id": message_id_header,
        },
        body_plain=body_plain,
        body_html=body_html,
        mime_metadata={},
        provenance={"message_id": message_id_header},
        status="pending",
        creation_fingerprint=f"test:{uuid4()}",
    )


class TestBancoGanaderoParser:
    def test_credit_notice_extracts_amount_direction_suffix_and_null_event_at(self):
        raw_msg = make_raw_message(
            sender="Banco Ganadero <notificaciones@bg.com.bo>",
            subject="Recibiste Bs 150.00 en tu cuenta *1234",
            body_plain="Estimado cliente, Recibiste Bs 150.00 en tu cuenta *1234.",
            date_header="Mon, 24 Aug 2026 10:15:00 -0400",
            message_id_header="<ganadero-credit-001@bg.com.bo>",
        )

        res = parse_banco_ganadero_message(raw_msg)
        assert res.is_banco_ganadero is True
        assert res.reported_amount == Decimal("150.00")
        assert res.reported_currency == "BOB"
        assert res.raw_currency_token == "Bs"
        assert res.direction == "credit"
        assert res.account_suffix == "*1234"
        assert res.event_at is None  # CRITICAL INVARIANT: Null event time pending statement enrichment
        assert res.notification_at is not None
        assert res.message_id_header == "<ganadero-credit-001@bg.com.bo>"

    def test_debit_notice_extracts_amount_direction_suffix(self):
        raw_msg = make_raw_message(
            sender="Banco Ganadero <notificaciones@bg.com.bo>",
            subject="Enviaste Bs 45.20 de tu cuenta *5678",
            body_plain="Estimado cliente, Enviaste Bs 45.20 de tu cuenta *5678.",
            date_header="Mon, 24 Aug 2026 11:20:00 -0400",
        )

        res = parse_banco_ganadero_message(raw_msg)
        assert res.is_banco_ganadero is True
        assert res.reported_amount == Decimal("45.20")
        assert res.reported_currency == "BOB"
        assert res.direction == "debit"
        assert res.account_suffix == "*5678"
        assert res.event_at is None

    def test_rfc2047_subject_decoding(self):
        # "Recibiste Bs 200.00 en tu cuenta *9999" base64 encoded
        rfc2047_subject = "=?UTF-8?B?UmVjaWJpc3RlIEJzIDIwMC4wMCBlbiB0dSBjdWVudGEgKjk5OTk=?="
        decoded = decode_rfc2047(rfc2047_subject)
        assert "Recibiste Bs 200.00" in decoded

        raw_msg = make_raw_message(
            sender="Banco Ganadero <notificaciones@bg.com.bo>",
            subject=rfc2047_subject,
            body_plain="Recibiste Bs 200.00 en tu cuenta *9999",
        )
        res = parse_banco_ganadero_message(raw_msg)
        assert res.is_banco_ganadero is True
        assert res.reported_amount == Decimal("200.00")
        assert res.account_suffix == "*9999"
        assert res.direction == "credit"

    def test_rejects_non_matching_sender(self):
        raw_msg = make_raw_message(
            sender="Spam <other@external.com>",
            subject="Recibiste Bs 100.00 en tu cuenta *1234",
        )
        res = parse_banco_ganadero_message(raw_msg)
        assert res.is_banco_ganadero is False


class TestBcpQrParser:
    def test_bcp_qr_notice_with_exact_product_payment_glosa(self):
        body_html = """
        <html><body>
        <p>Comprobante de Transferencia QR</p>
        <p>Operación: 12345678</p>
        <p>Comprobante: 987654</p>
        <p>Fecha y hora: 24/08/2026 14:30:00</p>
        <p>Monto: Bs 75.50</p>
        <p>Beneficiario: Supermercado Fidalga</p>
        <p>Banco Destino: Banco BCP</p>
        <p>Glosa: BM BM QR PAGO DE PRODUCTOS</p>
        </body></html>
        """
        raw_msg = make_raw_message(
            sender="BCP <notificaciones@bcp.com.bo>",
            subject="Comprobante de Transferencia QR",
            body_plain="Comprobante de Transferencia QR Operación: 12345678 Comprobante: 987654 Fecha: 24/08/2026 14:30:00 Monto: Bs 75.50 Beneficiario: Supermercado Fidalga Glosa: BM BM QR PAGO DE PRODUCTOS",
            body_html=body_html,
            message_id_header="<bcp-qr-001@bcp.com.bo>",
        )

        res = parse_bcp_qr_message(raw_msg)
        assert res.is_bcp_qr is True
        assert res.reported_amount == Decimal("75.50")
        assert res.reported_currency == "BOB"
        assert res.transaction_id == "12345678"
        assert res.receipt_id == "987654"
        assert res.event_at == datetime(2026, 8, 24, 14, 30, 0, tzinfo=timezone(timedelta(hours=-4)))
        assert res.beneficiary == "Supermercado Fidalga"
        assert res.raw_glosa == "BM BM QR PAGO DE PRODUCTOS"
        assert res.glosa == "BM BM QR PAGO DE PRODUCTOS"

    def test_bcp_qr_notice_with_interbancaria_glosa(self):
        raw_msg = make_raw_message(
            sender="notificacionesbcp@bcp.com.bo",
            subject="Transferencia QR Exitosa",
            body_plain="Nro. Operación: 87654321 Nro. Comprobante: 112233 Fecha: 2026-08-24 16:00:00 Monto: 250.00 BOB Glosa: BM BM QR INTERBANCARIA Beneficiario: Juan Perez",
        )

        res = parse_bcp_qr_message(raw_msg)
        assert res.is_bcp_qr is True
        assert res.reported_amount == Decimal("250.00")
        assert res.transaction_id == "87654321"
        assert res.receipt_id == "112233"
        assert res.raw_glosa == "BM BM QR INTERBANCARIA"
        assert res.glosa == "BM BM QR INTERBANCARIA"

    def test_bcp_qr_notice_preserves_null_glosa_when_absent(self):
        # CRITICAL INVARIANT: If glosa is absent, glosa MUST remain None and NEVER synthesized
        raw_msg = make_raw_message(
            sender="BCP <notificaciones@bcp.com.bo>",
            subject="Comprobante Transferencia QR",
            body_plain="Operación: 55443322 Comprobante: 998877 Fecha: 24/08/2026 12:00:00 Monto: Bs 10.00 Beneficiario: Cafeteria",
            body_html="<html><body><p>Operación: 55443322</p><p>Comprobante: 998877</p><p>Monto: Bs 10.00</p><p>Beneficiario: Cafeteria</p></body></html>",
        )

        res = parse_bcp_qr_message(raw_msg)
        assert res.is_bcp_qr is True
        assert res.reported_amount == Decimal("10.00")
        assert res.raw_glosa is None
        assert res.glosa is None
