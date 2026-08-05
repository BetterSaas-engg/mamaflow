"""The sync window must not silently drop mail (found in the 2026-07-27 audit).

`_list_recent_ids` returned only the newest 50 of the 30-day window. Once those
50 were synced, anything older was never listed again — permanently unextracted.
Worst case is a NEW user: a 30-day backlog of hundreds of messages, of which
only the newest 50 are ever processed. That silently breaks the core promise
that nothing falls through the cracks.

Gmail/Claude are mocked — never live.
"""

from api.auth.jwt import create_access_token
from api.config.settings import settings as app_settings
from api.schemas.family_event import ExtractionResponse
from api.services import sync_runner
from api.services.ai_extractor import ExtractionUsage
from api.services.users import get_or_create_user
from tests.helpers import user_with_mailbox


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    return await user_with_mailbox(db, email)


async def test_backlog_larger_than_one_run_is_eventually_all_processed(
    client, db, monkeypatch
):
    """A 120-message backlog must drain across successive syncs — not stop at
    the newest run-sized slice with the rest lost forever."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    _, token = await _user_with_token(db)

    # Newest-first, as Gmail returns them.
    all_ids = [f"m{i:03d}" for i in range(120)]
    monkeypatch.setattr(
        sync_runner,
        "list_recent_ids",
        lambda email, provider="google": list(all_ids),
    )
    monkeypatch.setattr(
        sync_runner,
        "fetch_metadata",
        lambda email, ids, provider="google": [
            {"message_id": i, "sender": "school@x.org", "subject": "Practice", "date": "Mon"}
            for i in ids
        ],
    )
    monkeypatch.setattr(
        sync_runner,
        "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )

    extracted = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        extracted.append(message_id)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=1, output_tokens=1)

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    # Run enough syncs to cover the backlog at the per-run cap.
    for _ in range(6):
        await client.post("/api/v1/sync", headers=_auth(token))

    assert set(extracted) == set(all_ids), (
        f"{len(set(all_ids) - set(extracted))} messages were never extracted"
    )


async def test_one_run_is_still_bounded(client, db, monkeypatch):
    """Draining the backlog must not mean one giant unbounded run."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "sync_max_messages_per_run", 50)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    _, token = await _user_with_token(db)

    all_ids = [f"m{i:03d}" for i in range(120)]
    monkeypatch.setattr(sync_runner, "list_recent_ids", lambda email, provider="google": list(all_ids))
    monkeypatch.setattr(
        sync_runner, "fetch_metadata",
        lambda email, ids, provider="google": [
            {"message_id": i, "sender": "school@x.org", "subject": "S", "date": "Mon"} for i in ids
        ],
    )
    monkeypatch.setattr(
        sync_runner, "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )

    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=1, output_tokens=1)

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))

    assert len(calls) == 50


async def test_metadata_is_only_fetched_for_unsynced_ids(client, db, monkeypatch):
    """Dedup must happen on ids BEFORE the per-message metadata fetch —
    otherwise every hourly tick re-fetches headers for the whole window."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    _, token = await _user_with_token(db)

    monkeypatch.setattr(sync_runner, "list_recent_ids", lambda email, provider="google": ["a", "b"])
    meta_calls = []

    def fake_metadata(email, ids, provider="google"):
        meta_calls.append(list(ids))
        return [
            {"message_id": i, "sender": "school@x.org", "subject": "S", "date": "Mon"} for i in ids
        ]

    monkeypatch.setattr(sync_runner, "fetch_metadata", fake_metadata)
    monkeypatch.setattr(
        sync_runner, "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )
    monkeypatch.setattr(
        sync_runner, "extract_events",
        lambda *a, **k: (ExtractionResponse(events=[]), ExtractionUsage()),
    )

    await client.post("/api/v1/sync", headers=_auth(token))
    await client.post("/api/v1/sync", headers=_auth(token))

    assert set(meta_calls[0]) == {"a", "b"}  # (oldest-first, so order differs)
    assert meta_calls[1] == []  # second sync: both already synced, no header re-fetch


async def test_blocked_senders_cannot_starve_real_mail(client, db, monkeypatch):
    """Blocked messages never produced a marker, so with oldest-first selection
    they re-entered every batch forever. With more in-window blocked mail than
    the per-run cap (easy: the seed blocklist covers high-volume senders), real
    mail newer than them was NEVER reached — the silent-loss bug, reborn."""
    from api.models.sender_blocklist import SenderBlocklist

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "sync_max_messages_per_run", 50)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    db.add(SenderBlocklist(domain="blocked.com", category="financial", reason="test"))
    await db.commit()
    _, token = await _user_with_token(db)

    # Newest-first: 10 real messages, then 70 older blocked ones.
    real_ids = [f"real{i:02d}" for i in range(10)]
    blocked_ids = [f"blk{i:02d}" for i in range(70)]
    meta = {
        **{i: {"message_id": i, "sender": "school@allowed.org",
               "subject": "Practice", "date": "Mon"} for i in real_ids},
        **{i: {"message_id": i, "sender": "noreply@blocked.com",
               "subject": "Promo", "date": "Mon"} for i in blocked_ids},
    }
    order = real_ids + blocked_ids  # newest first

    monkeypatch.setattr(sync_runner, "list_recent_ids", lambda email, provider="google": list(order))
    monkeypatch.setattr(
        sync_runner, "fetch_metadata",
        lambda email, ids, provider="google": [meta[i] for i in ids if i in meta],
    )
    monkeypatch.setattr(
        sync_runner, "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )

    extracted = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        extracted.append(message_id)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=1, output_tokens=1)

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    for _ in range(4):
        await client.post("/api/v1/sync", headers=_auth(token))

    assert set(extracted) == set(real_ids), (
        "real mail starved behind blocked senders — "
        f"only reached {sorted(extracted)}"
    )
