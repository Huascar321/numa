from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import io
import re
from typing import Any


LA_PAZ_TZ = timezone(timedelta(hours=-4))


@dataclass
class ParsedStatementRow:
    source_row_index: int
    event_at: datetime
    transaction_number: str
    channel: str | None
    description: str
    type: str  # "debit" | "credit"
    amount: Decimal
    signed_amount: Decimal
    running_balance: Decimal
    compound_identity: str
    card_suffix: str | None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedStatement:
    account_number: str | None
    client_name: str | None
    currency_code: str
    period_start: datetime | None
    period_end: datetime | None
    exported_at: datetime | None
    opening_balance: Decimal | None
    closing_balance: Decimal | None
    current_balance: Decimal | None
    footer_debit_count: int | None
    footer_credit_count: int | None
    debit_count: int
    credit_count: int
    debit_sum: Decimal
    credit_sum: Decimal
    warnings: list[str]
    metadata: dict[str, Any]
    rows: list[ParsedStatementRow]


def _clean_money(value: str) -> Decimal:
    cleaned = value.strip().replace("+", "").replace(",", "")
    if not cleaned:
        return Decimal("0.00")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal amount: '{value}'") from exc


def _parse_exported_at(date_str: str) -> datetime | None:
    date_str = date_str.strip()
    patterns = [
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ]
    for pattern in patterns:
        try:
            dt = datetime.strptime(date_str, pattern)
            return dt.replace(tzinfo=LA_PAZ_TZ)
        except ValueError:
            continue
    return None


def parse_banco_ganadero_csv(csv_content: str) -> ParsedStatement:
    """Parse Banco Ganadero CSV statement according to the verified 4-month sample structure."""
    if csv_content.startswith("\ufeff"):
        csv_content = csv_content[1:]

    lines = csv_content.splitlines()
    preamble_lines: list[str] = []
    header_index: int | None = None

    for idx, line in enumerate(lines):
        clean_line = line.strip().upper()
        # Look for the exact 8-field header
        if "FECHA" in clean_line and "HORA" in clean_line and "SALDO" in clean_line and ";" in line:
            header_index = idx
            break
        preamble_lines.append(line)

    if header_index is None:
        raise ValueError("Banco Ganadero CSV header not found")

    # Parse Preamble
    account_number: str | None = None
    client_name: str | None = None
    currency_code = "BOB"
    period_start: datetime | None = None
    period_end: datetime | None = None
    exported_at: datetime | None = None
    opening_balance: Decimal | None = None

    for pl in preamble_lines:
        text_line = pl.strip()
        if not text_line:
            continue
        acc_m = re.search(r"NRO\.?\s*DE\s*CUENTA:\s*(\w+)", text_line, re.IGNORECASE)
        if acc_m:
            account_number = acc_m.group(1).strip()
            continue

        cli_m = re.search(r"CLIENTE:\s*(.+)", text_line, re.IGNORECASE)
        if cli_m:
            client_name = cli_m.group(1).strip()
            continue

        if re.search(r"BOLIVIANOS", text_line, re.IGNORECASE):
            currency_code = "BOB"
        elif re.search(r"DOLARES|DÓLARES|USD", text_line, re.IGNORECASE):
            currency_code = "USD"

        period_m = re.search(
            r"PERIODO\s+DEL\s+(\d{1,2}/\d{1,2}/\d{4})\s+AL\s+(\d{1,2}/\d{1,2}/\d{4})",
            text_line,
            re.IGNORECASE,
        )
        if period_m:
            try:
                period_start = datetime.strptime(
                    period_m.group(1), "%d/%m/%Y"
                ).replace(tzinfo=LA_PAZ_TZ)
                period_end = datetime.strptime(
                    period_m.group(2), "%d/%m/%Y"
                ).replace(hour=23, minute=59, second=59, tzinfo=LA_PAZ_TZ)
            except ValueError:
                pass
            continue

        export_m = re.search(r"Fecha\s+y\s+Hora:\s*(.+)", text_line, re.IGNORECASE)
        if export_m:
            exported_at = _parse_exported_at(export_m.group(1))
            continue

        saldo_ant_m = re.search(
            r"SALDO\s+ANTERIOR:\s*([0-9.,+-]+)", text_line, re.IGNORECASE
        )
        if saldo_ant_m:
            opening_balance = _clean_money(saldo_ant_m.group(1))
            continue

    # Parse rows using csv.reader with semicolon delimiter
    data_lines = lines[header_index + 1 :]
    reader = csv.reader(io.StringIO("\n".join(data_lines)), delimiter=";")

    rows: list[ParsedStatementRow] = []
    footer_lines: list[str] = []
    in_footer = False

    current_balance: Decimal | None = None
    footer_debit_count: int | None = None
    footer_credit_count: int | None = None

    row_index = 0
    for row in reader:
        if not row or all(not field.strip() for field in row):
            continue

        first_field = row[0].strip().upper()
        if (
            first_field.startswith("SALDO ACTUAL:")
            or first_field.startswith("CANTIDAD DÉBITOS:")
            or first_field.startswith("CANTIDAD DEBITOS:")
            or first_field.startswith("CANTIDAD CRÉDITOS:")
            or first_field.startswith("CANTIDAD CREDITOS:")
        ):
            in_footer = True

        if in_footer:
            footer_lines.append(";".join(row))
            continue

        if len(row) < 8:
            # Maybe a footer row or malformed row
            joined = ";".join(row).strip().upper()
            if "SALDO ACTUAL" in joined or "CANTIDAD" in joined:
                in_footer = True
                footer_lines.append(";".join(row))
                continue
            raise ValueError(
                f"Row {row_index + 1} has insufficient columns (expected 8, found {len(row)})"
            )

        fecha_str = row[0].strip()
        hora_str = row[1].strip()
        canal = row[2].strip() or None
        transaccion = row[3].strip()
        descripcion = row[4].strip()
        debito_str = row[5].strip()
        credito_str = row[6].strip()
        saldo_str = row[7].strip()

        try:
            dt = datetime.strptime(f"{fecha_str} {hora_str}", "%d/%m/%Y %H:%M:%S")
            event_at = dt.replace(tzinfo=LA_PAZ_TZ)
        except ValueError as exc:
            raise ValueError(f"Invalid timestamp at row {row_index + 1}: {fecha_str} {hora_str}") from exc

        debito_val = abs(_clean_money(debito_str))
        credito_val = abs(_clean_money(credito_str))
        saldo_val = _clean_money(saldo_str)

        if debito_val > 0 and credito_val == 0:
            row_type = "debit"
            amount = debito_val
            signed_amount = -debito_val
        elif credito_val > 0 and debito_val == 0:
            row_type = "credit"
            amount = credito_val
            signed_amount = credito_val
        elif debito_val == 0 and credito_val == 0:
            # Zero-amount row (treat as debit 0.00 or handle)
            row_type = "debit"
            amount = Decimal("0.00")
            signed_amount = Decimal("0.00")
        else:
            raise ValueError(
                f"Row {row_index + 1} has both debit ({debito_val}) and credit ({credito_val})"
            )

        # Compound source identity (preserves source order even for shared transaction ID)
        compound_identity = f"bg:{row_index}:{transaccion}:{fecha_str}:{row_type}:{amount}"

        # Card suffix parsing (e.g. Tarj: 1810 FR or POS SUPERMERCADO TIA VEN Tarj: 1810 BO)
        card_suffix: str | None = None
        card_country: str | None = None
        card_m = re.search(r"(?:Tarj:|XXXXXX-)\s*(\d{4})(?:\s+([A-Z]{2}))?", descripcion)
        if card_m:
            card_suffix = card_m.group(1)
            card_country = card_m.group(2)

        row_meta: dict[str, Any] = {
            "source_format": "banco_ganadero_csv",
            "raw_fecha": fecha_str,
            "raw_hora": hora_str,
            "raw_transaccion": transaccion,
            "raw_canal": canal,
            "raw_descripcion": descripcion,
        }
        if card_country:
            row_meta["card_country"] = card_country

        parsed_row = ParsedStatementRow(
            source_row_index=row_index,
            event_at=event_at,
            transaction_number=transaccion,
            channel=canal,
            description=descripcion,
            type=row_type,
            amount=amount,
            signed_amount=signed_amount,
            running_balance=saldo_val,
            compound_identity=compound_identity,
            card_suffix=card_suffix,
            metadata=row_meta,
        )
        rows.append(parsed_row)
        row_index += 1

    # Parse Footer Lines
    for fl in footer_lines:
        saldo_act_m = re.search(r"SALDO\s+ACTUAL:\s*([0-9.,+-]+)", fl, re.IGNORECASE)
        if saldo_act_m:
            current_balance = _clean_money(saldo_act_m.group(1))

        deb_cnt_m = re.search(
            r"CANTIDAD\s+D[EÉ]BITOS:\s*(\d+)", fl, re.IGNORECASE
        )
        if deb_cnt_m:
            footer_debit_count = int(deb_cnt_m.group(1))

        cred_cnt_m = re.search(
            r"CANTIDAD\s+CR[EÉ]DITOS:\s*(\d+)", fl, re.IGNORECASE
        )
        if cred_cnt_m:
            footer_credit_count = int(cred_cnt_m.group(1))

    # Calculate Aggregates
    debit_count = sum(1 for r in rows if r.type == "debit" and r.amount > 0)
    credit_count = sum(1 for r in rows if r.type == "credit" and r.amount > 0)
    debit_sum = sum((r.amount for r in rows if r.type == "debit"), start=Decimal("0.00"))
    credit_sum = sum((r.amount for r in rows if r.type == "credit"), start=Decimal("0.00"))
    closing_balance = rows[-1].running_balance if rows else opening_balance

    warnings: list[str] = []

    # Footer Validation
    if footer_debit_count is not None and debit_count != footer_debit_count:
        warnings.append(
            f"Debit count mismatch: footer declared {footer_debit_count}, parsed {debit_count}"
        )
    if footer_credit_count is not None and credit_count != footer_credit_count:
        warnings.append(
            f"Credit count mismatch: footer declared {footer_credit_count}, parsed {credit_count}"
        )

    # Running Balance Arithmetic Validation
    # Invariant: running balance must be checked in source row order
    if opening_balance is not None:
        expected_balance = opening_balance
        for idx, r in enumerate(rows):
            if r.type == "debit":
                expected_balance = expected_balance - r.amount
            else:
                expected_balance = expected_balance + r.amount

            if r.running_balance != expected_balance:
                warnings.append(
                    f"Arithmetic mismatch at row {idx + 1}: "
                    f"expected running balance {expected_balance}, found {r.running_balance}"
                )
                expected_balance = r.running_balance

    metadata: dict[str, Any] = {
        "account_number": account_number,
        "client_name": client_name,
        "raw_opening_balance": str(opening_balance) if opening_balance is not None else None,
        "raw_current_balance": str(current_balance) if current_balance is not None else None,
    }

    return ParsedStatement(
        account_number=account_number,
        client_name=client_name,
        currency_code=currency_code,
        period_start=period_start,
        period_end=period_end,
        exported_at=exported_at,
        opening_balance=opening_balance,
        closing_balance=closing_balance,
        current_balance=current_balance,
        footer_debit_count=footer_debit_count,
        footer_credit_count=footer_credit_count,
        debit_count=debit_count,
        credit_count=credit_count,
        debit_sum=debit_sum,
        credit_sum=credit_sum,
        warnings=warnings,
        metadata=metadata,
        rows=rows,
    )
