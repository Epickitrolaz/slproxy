"""
Account Router for SLProxy
"""

import time
from typing import Any, Dict, List, Optional
from slproxy.core.plugin_base import Account


class AccountRouter:
    """
    Manages accounts per provider plugin.
    Implements routing strategies:
    - fallback: strictly by priority/order, falling back if an account is rate-limited or fails
    - round_robin: cyclically select healthy accounts
    - cooldown tracking: rate-limited accounts enter cooldown with backoff
    """

    def __init__(self, db: Optional[Any] = None):
        self.db = db
        self.rr_indices: Dict[str, int] = {}

    def select_account(
        self,
        accounts: List[Account],
        strategy: str = "fallback",
        now: Optional[float] = None,
    ) -> Optional[Account]:
        """
        Select an available account based on the configured strategy.
        - fallback: sorts by priority ascending (1 is highest), returns first available.
        - round_robin: cyclically selects next available account.
        Returns None if all accounts are unavailable.
        """
        available = [acc for acc in accounts if acc.is_available(now=now)]
        if not available:
            return None

        strat = strategy.lower().replace("-", "_")
        if strat == "round_robin":
            key = accounts[0].provider_id if (accounts and accounts[0].provider_id) else "default"
            idx = self.rr_indices.get(key, 0)
            selected = available[idx % len(available)]
            self.rr_indices[key] = idx + 1
            return selected

        # Default strategy: fallback by priority (1 is highest)
        sorted_accounts = sorted(available, key=lambda a: a.priority)
        return sorted_accounts[0]

    def mark_rate_limited(self, account: Account, cooldown_seconds: float = 60.0):
        """
        Sets rate_limited_until = time.time() + cooldown_seconds and increments error_count.
        """
        account.rate_limited_until = time.time() + cooldown_seconds
        account.error_count += 1

    def mark_success(self, account: Account):
        """
        Increments success_count and updates last_used_at timestamp.
        """
        account.success_count += 1
        account.last_used_at = time.time()

    def mark_error(self, account: Account, error_msg: str = ""):
        """
        Increments error_count.
        """
        account.error_count += 1
