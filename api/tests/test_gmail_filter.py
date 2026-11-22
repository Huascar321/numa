from __future__ import annotations

import pytest

from app.gmail.filter import metadata_is_allowed, sender_query


def metadata(value="Notice <notice@example.com>", labels=None):
    return {"id": "one", "labelIds": labels or [],
            "payload": {"headers": [{"name": "From", "value": value}]}}


@pytest.mark.parametrize("value", [
    "notice@example.com", "Notice <NOTICE@example.COM>",
    "=?utf-8?b?QXZpc28=?= <notice@example.com>",
])
def test_exact_sender_match_with_optional_display_name(value):
    assert metadata_is_allowed(metadata(value), "one", ["notice@example.com"])


@pytest.mark.parametrize("value", [
    "", "notice@example.com.evil.test", "fake-notice@example.com",
    '"notice@example.com" <attacker@example.com>',
    "notice@example.com, attacker@example.com", "notice@example.com junk",
    "Group:notice@example.com;", "Notice <notice@example.com>\r\nBcc: other@example.com",
])
def test_unapproved_malformed_ambiguous_and_display_name_spoofs_are_rejected(value):
    assert not metadata_is_allowed(metadata(value), "one", ["notice@example.com"])


@pytest.mark.parametrize("data", [
    {}, {"id": "other"}, {"id": "one", "payload": None},
    {"id": "one", "payload": {"headers": []}},
    {"id": "one", "payload": {"headers": "bad"}},
    {"id": "one", "payload": {"headers": [{"name": "From", "value": None}]}},
    {"id": "one", "payload": {"headers": [
        {"name": "From", "value": "notice@example.com"},
        {"name": "From", "value": "notice@example.com"},
    ]}},
    metadata(labels=["SPAM"]), metadata(labels=["TRASH"]),
    {**metadata(), "labelIds": None},
])
def test_invalid_metadata_and_spam_trash_fail_closed(data):
    assert not metadata_is_allowed(data, "one", ["notice@example.com"])


def test_empty_saved_scope_and_empty_query_never_allow_whole_mailbox():
    assert not metadata_is_allowed(metadata(), "one", [])
    with pytest.raises(ValueError):
        sender_query([])
    with pytest.raises(ValueError):
        sender_query(["*"])
    assert sender_query(["notice@example.com", "Bank@example.com"]) == "{from:notice@example.com from:bank@example.com}"


@pytest.mark.parametrize("sender", ["do-not-reply@ses.binance.com", "notificaciones@bg.com.bo"])
def test_approved_local_scope_accepts_each_financial_sender(sender):
    assert metadata_is_allowed(metadata(sender), "one", [
        "do-not-reply@ses.binance.com", "notificaciones@bg.com.bo",
    ])
