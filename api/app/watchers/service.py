from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.accounts.service import ResourceNotFound
from app.gmail.models import GmailMessage, GmailSource
from app.watchers.contracts import Rule, SourceRef
from app.watchers.engine import ENGINE_VERSION, Parser, canonical_hash, execute, rule_snapshot, ruleset_hash
from app.watchers.models import WatcherRun


def record_run(
    session: Session, *, plan_id: UUID, message_id: int,
    parser: Parser, parser_version: str, rules: tuple[Rule, ...] = (),
    protected_hints: dict[str, str] | None = None,
    replay_of: int | None = None,
) -> WatcherRun:
    """Trusted internal adapter contract; no HTTP/posting or arbitrary rule execution."""
    if type(message_id) is not int or message_id < 1:
        raise ValueError("Message identity must be a positive integer.")
    if replay_of is not None and (type(replay_of) is not int or replay_of < 1):
        raise ValueError("Replay parent must be a positive integer revision.")
    if not isinstance(parser_version, str) or not 1 <= len(parser_version) <= 64:
        raise ValueError("Explicit parser version is required.")
    message = session.scalar(
        select(GmailMessage).join(GmailSource, GmailSource.id == GmailMessage.source_id)
        .where(GmailMessage.id == message_id, GmailSource.plan_id == plan_id)
        .with_for_update(of=GmailMessage)
    )
    if message is None:
        raise ResourceNotFound("Source message not found.")
    protected = dict(protected_hints or {})
    contract_hash = ruleset_hash(rules, protected)
    if replay_of is None:
        existing = session.scalar(select(WatcherRun).where(
            WatcherRun.message_id == message_id, WatcherRun.engine_version == ENGINE_VERSION,
            WatcherRun.parser_version == parser_version, WatcherRun.ruleset_hash == contract_hash,
            WatcherRun.replayed_from.is_(None),
        ))
        if existing is not None:
            return existing
    elif session.get(WatcherRun, (message_id, replay_of)) is None:
        raise ResourceNotFound("Replay parent not found.")
    reference = SourceRef(str(plan_id), str(message.source_id), message.id, message.gmail_id)
    result = execute(parser, rules, source=reference, protected_hints=protected)
    revision = (session.scalar(select(func.max(WatcherRun.revision)).where(
        WatcherRun.message_id == message_id,
    )) or 0) + 1
    run = WatcherRun(
        message_id=message_id, revision=revision, replayed_from=replay_of,
        engine_version=ENGINE_VERSION, parser_version=parser_version,
        ruleset_hash=contract_hash, source_fingerprint=canonical_hash(message.decoded),
        status=result.status, result=result.payload(),
        config_snapshot={"rules": rule_snapshot(rules), "protected_hints": protected},
    )
    session.add(run)
    session.flush()
    return run
