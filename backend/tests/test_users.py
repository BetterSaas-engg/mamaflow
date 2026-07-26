"""Tests for the User model + get_or_create_user service (Phase A)."""

from api.services.users import get_or_create_user


async def test_creates_user_when_absent(db):
    user = await get_or_create_user(db, "parent@example.com")

    assert user.id is not None
    assert user.email == "parent@example.com"


async def test_is_idempotent_for_same_email(db):
    first = await get_or_create_user(db, "parent@example.com")
    second = await get_or_create_user(db, "parent@example.com")

    assert first.id == second.id


async def test_email_is_normalized_to_lowercase(db):
    upper = await get_or_create_user(db, "Parent@Example.COM")
    lower = await get_or_create_user(db, "parent@example.com")

    assert upper.email == "parent@example.com"
    assert upper.id == lower.id


async def test_new_user_defaults_to_google_provider(db):
    user = await get_or_create_user(db, "parent@example.com")
    assert user.provider == "google"


async def test_new_user_with_explicit_provider(db):
    user = await get_or_create_user(db, "parent@rogers.com", provider="yahoo")
    assert user.provider == "yahoo"


async def test_signin_via_other_provider_switches_provider(db):
    """A successful sign-in through a different provider proves mailbox
    ownership there — Phase 1 keeps exactly one active mail source per user."""
    first = await get_or_create_user(db, "parent@yahoo.com")  # google identity
    assert first.provider == "google"

    switched = await get_or_create_user(db, "parent@yahoo.com", provider="yahoo")

    assert switched.id == first.id  # same account, not a duplicate
    assert switched.provider == "yahoo"
