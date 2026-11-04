"""
Tests for AccountRouter
"""

import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from slproxy.core.account_router import AccountRouter
from slproxy.core.plugin_base import Account


@pytest.fixture
def router():
    return AccountRouter()


@pytest.fixture
def sample_accounts():
    return [
        Account(id="acc_1", provider_id="prov_a", name="Account 1", priority=1),
        Account(id="acc_2", provider_id="prov_a", name="Account 2", priority=2),
        Account(id="acc_3", provider_id="prov_a", name="Account 3", priority=3),
    ]


def test_fallback_routing_priority_order(router, sample_accounts):
    """
    Fallback routing selects the account with the highest priority (lowest number).
    """
    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected is not None
    assert selected.id == "acc_1"

    # When acc_1 is disabled, fallback selects acc_2
    sample_accounts[0].is_active = False
    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected is not None
    assert selected.id == "acc_2"

    # When acc_2 is also disabled, fallback selects acc_3
    sample_accounts[1].is_active = False
    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected is not None
    assert selected.id == "acc_3"


def test_fallback_routing_rate_limited_exclusion(router, sample_accounts):
    """
    Rate-limited accounts are excluded from selection in fallback routing.
    """
    router.mark_rate_limited(sample_accounts[0], cooldown_seconds=60.0)
    assert not sample_accounts[0].is_available()
    assert sample_accounts[0].error_count == 1

    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected is not None
    assert selected.id == "acc_2"


def test_cooldown_recovery(router, sample_accounts):
    """
    Accounts in cooldown recover and become available again after the cooldown expires.
    """
    # Rate limit acc_1 with a tiny cooldown
    router.mark_rate_limited(sample_accounts[0], cooldown_seconds=0.05)
    assert not sample_accounts[0].is_available()

    # While in cooldown, acc_2 is selected
    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected.id == "acc_2"

    # Wait for cooldown to expire
    time.sleep(0.08)
    assert sample_accounts[0].is_available()

    # After cooldown expires, acc_1 is selected again
    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected.id == "acc_1"


def test_all_accounts_unavailable_returns_none(router, sample_accounts):
    """
    Returns None if all accounts are inactive or rate limited.
    """
    for acc in sample_accounts:
        acc.is_active = False

    selected = router.select_account(sample_accounts, strategy="fallback")
    assert selected is None

    # Test empty list
    assert router.select_account([], strategy="fallback") is None
    assert router.select_account([], strategy="round_robin") is None


def test_round_robin_cycling(router, sample_accounts):
    """
    Round-robin cyclically selects next available account.
    """
    selections = [
        router.select_account(sample_accounts, strategy="round_robin").id
        for _ in range(7)
    ]
    # Expected pattern: acc_1, acc_2, acc_3, acc_1, acc_2, acc_3, acc_1
    assert selections == [
        "acc_1",
        "acc_2",
        "acc_3",
        "acc_1",
        "acc_2",
        "acc_3",
        "acc_1",
    ]


def test_round_robin_with_rate_limited_account(router, sample_accounts):
    """
    Round-robin skips rate-limited accounts and cycles only through healthy ones.
    """
    # Rate limit acc_2
    router.mark_rate_limited(sample_accounts[1], cooldown_seconds=60.0)

    selections = [
        router.select_account(sample_accounts, strategy="round_robin").id
        for _ in range(4)
    ]
    # acc_2 should be excluded, cycling between acc_1 and acc_3
    assert "acc_2" not in selections
    assert set(selections) == {"acc_1", "acc_3"}


def test_mark_success(router, sample_accounts):
    """
    mark_success increments success_count and updates last_used_at.
    """
    acc = sample_accounts[0]
    initial_success = acc.success_count
    assert acc.last_used_at is None

    before = time.time()
    router.mark_success(acc)
    after = time.time()

    assert acc.success_count == initial_success + 1
    assert acc.last_used_at is not None
    assert before <= acc.last_used_at <= after


def test_mark_error(router, sample_accounts):
    """
    mark_error increments error_count.
    """
    acc = sample_accounts[0]
    initial_errors = acc.error_count

    router.mark_error(acc, error_msg="Connection timeout")
    assert acc.error_count == initial_errors + 1
