"""Plan limits (D44): free 1 mailbox, pro 2, family 2 per member + 2 members.

These pin the numbers the PM set. The limits live in ONE module precisely so a
pricing change is a single edit — if a limit ever gets hardcoded at a call site
these tests won't catch it, so the review rule is: nobody writes a literal.
"""

import pytest

from api.services.entitlements import (
    FAMILY,
    FREE,
    PRO,
    can_connect_another_mailbox,
    entitlements_for,
    mailbox_limit,
    member_limit,
)


def test_free_gets_one_mailbox_one_member_and_ads():
    ent = entitlements_for(FREE)
    assert ent.mailboxes == 1
    assert ent.members == 1
    assert ent.ads is True  # ads are the free tier's price (D21)


def test_pro_gets_two_mailboxes_and_no_ads():
    ent = entitlements_for(PRO)
    assert ent.mailboxes == 2
    assert ent.members == 1
    assert ent.ads is False


def test_family_gets_two_mailboxes_per_member_and_two_members():
    """The cap is per USER in every tier; Family's extra allowance is a second
    member (each parent has their own login and their own 2 mailboxes)."""
    ent = entitlements_for(FAMILY)
    assert ent.mailboxes == 2
    assert ent.members == 2
    assert ent.ads is False


@pytest.mark.parametrize("tier", [None, "", "enterprise", "FREE", "legacy-beta"])
def test_unknown_tier_degrades_to_free_without_raising(tier):
    """A stale row or billing bug must not 500 someone out of their own
    calendar — but must not hand out a paid allowance either. Fail closed on
    the allowance, stay alive on the request (D34's coerce-don't-reject)."""
    ent = entitlements_for(tier)
    assert ent.tier == FREE
    assert ent.mailboxes == 1
    assert ent.ads is True


def test_cap_blocks_the_mailbox_after_the_limit():
    assert can_connect_another_mailbox(FREE, 0) is True
    assert can_connect_another_mailbox(FREE, 1) is False
    assert can_connect_another_mailbox(PRO, 1) is True
    assert can_connect_another_mailbox(PRO, 2) is False
    assert can_connect_another_mailbox(FAMILY, 2) is False


def test_cap_holds_if_a_count_somehow_exceeds_the_limit():
    """Defence in depth: a downgrade from pro to free leaves 2 mailboxes
    against a limit of 1. That must not read as "room for more"."""
    assert can_connect_another_mailbox(FREE, 2) is False
    assert can_connect_another_mailbox(FREE, 99) is False


def test_helpers_agree_with_the_dataclass():
    for tier in (FREE, PRO, FAMILY):
        assert mailbox_limit(tier) == entitlements_for(tier).mailboxes
        assert member_limit(tier) == entitlements_for(tier).members
