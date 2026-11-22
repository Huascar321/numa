from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
import re
from uuid import UUID


class Provider(str, Enum):
    BINANCE_CARD = "binance_card"
    GANADERO = "ganadero"
    BCP_QR = "bcp_qr"


class Stage(str, Enum):
    EMAIL = "email"
    WATCHER = "watcher"
    PARSER = "parser"
    RULES = "rules"
    AI = "ai"
    NORMALIZE = "normalize"
    DEDUPLICATE = "deduplicate"
    TRANSACTION = "transaction"


STAGE_ORDER = tuple(Stage)


@dataclass(frozen=True)
class SourceRef:
    plan_id: str
    source_id: str
    message_id: int
    gmail_id: str

    def __post_init__(self):
        for identifier in (self.plan_id, self.source_id):
            if not isinstance(identifier, str):
                raise ValueError("Source identifiers must be strings.")
            UUID(identifier)
        if type(self.message_id) is not int or self.message_id < 1 or not isinstance(self.gmail_id, str) or not self.gmail_id:
            raise ValueError("Stored source-message identity is required.")


class MatchField(str, Enum):
    PROVIDER = "provider"
    MERCHANT = "merchant"
    RAW_GLOSA = "raw_glosa"
    REPORTED_CURRENCY = "reported_currency"
    DIRECTION = "direction"


class HintField(str, Enum):
    CATEGORY = "category_hint"
    SUBTYPE = "subtype_hint"


@dataclass(frozen=True)
class NoticeFacts:
    provider: Provider
    reported_amount: str
    reported_currency: str
    raw_currency_token: str
    direction: str
    merchant: str | None = None
    masked_account_suffix: str | None = None
    raw_glosa: str | None = None
    transaction_id: str | None = None
    receipt_id: str | None = None
    event_at: str | None = None
    notification_at: str | None = None
    timezone_provenance: str | None = None
    origin: str | None = None
    destination: str | None = None
    beneficiary: str | None = None
    bank: str | None = None
    header_message_id: str | None = None
    mime_charset: str | None = None
    authentication_metadata: tuple[str, ...] = ()

    def __post_init__(self):
        if not isinstance(self.provider, Provider):
            raise ValueError("Provider must be typed.")
        for key, value in asdict(self).items():
            if key not in {"provider", "authentication_metadata"} and value is not None and not isinstance(value, str):
                raise ValueError("Notice facts must use exact strings, never floats.")
        if not isinstance(self.authentication_metadata, tuple) or any(
            not isinstance(value, str) for value in self.authentication_metadata
        ):
            raise ValueError("Authentication provenance must be immutable strings.")
        if not isinstance(self.reported_currency, str) or not re.fullmatch(r"[A-Z]{2,16}", self.reported_currency):
            raise ValueError("Reported currency must be explicit.")
        if not isinstance(self.raw_currency_token, str) or not self.raw_currency_token:
            raise ValueError("Raw currency token must be retained.")
        if not isinstance(self.reported_amount, str) or not re.fullmatch(
            r"[0-9]{1,38}(?:\.[0-9]{1,18})?", self.reported_amount
        ) or Decimal(self.reported_amount) <= 0:
            raise ValueError("Amount must be a positive exact decimal string.")
        if self.direction not in {"credit", "debit"}:
            raise ValueError("Notice direction must be explicit.")
        for value in (self.event_at, self.notification_at):
            if value is not None and datetime.fromisoformat(value).tzinfo is None:
                raise ValueError("Timestamps must have explicit timezone provenance.")
        if self.event_at is not None and not self.timezone_provenance:
            raise ValueError("Event time requires timezone provenance.")
        if self.provider is Provider.GANADERO:
            if self.reported_currency != "BOB" or self.raw_currency_token != "Bs":
                raise ValueError("Ganadero currency must retain Bs mapped to BOB.")
            if any(value is not None for value in (
                self.merchant, self.raw_glosa, self.transaction_id, self.receipt_id,
                self.event_at, self.origin, self.destination, self.beneficiary, self.bank,
            )):
                raise ValueError("Ganadero notice cannot synthesize absent event facts.")
        if self.provider is Provider.BCP_QR and self.reported_currency != "BOB":
            raise ValueError("BCP QR requires reported BOB.")

    def payload(self) -> dict:
        return json.loads(json.dumps(asdict(self)))


@dataclass(frozen=True)
class Predicate:
    field: MatchField
    value: str

    def __post_init__(self):
        if not isinstance(self.field, MatchField) or not isinstance(self.value, str):
            raise ValueError("Predicate must use a typed field and exact string.")


@dataclass(frozen=True)
class Rule:
    id: str
    version: int
    priority: int
    predicate: Predicate
    target: HintField
    value: str

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id or type(self.version) is not int or self.version < 1:
            raise ValueError("Rule identity and positive integer version are required.")
        if type(self.priority) is not int or not isinstance(self.predicate, Predicate):
            raise ValueError("Rule order and predicate must be typed.")
        if not isinstance(self.target, HintField) or not isinstance(self.value, str) or not self.value:
            raise ValueError("Rules may only propose non-financial classification hints.")


@dataclass(frozen=True)
class RuleEvidence:
    rule_id: str
    version: int
    priority: int
    outcome: str
    matched_field: str
    matched_value: str | None
    target: str
    proposed_value: str


@dataclass(frozen=True)
class StageOutcome:
    stage: Stage
    status: str
    code: str


@dataclass(frozen=True)
class PipelineResult:
    status: str
    source: SourceRef
    stages: tuple[StageOutcome, ...]
    parsed: NoticeFacts | None
    hints: tuple[tuple[str, str], ...]
    rules: tuple[RuleEvidence, ...]
    review_reasons: tuple[str, ...]
    error_code: str | None = None

    def payload(self) -> dict:
        # Return the same JSON representation before and after PostgreSQL replay.
        return json.loads(json.dumps(asdict(self)))
