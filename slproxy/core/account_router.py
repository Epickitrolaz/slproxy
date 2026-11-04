"""
Account Router Contract & Stub
"""

from typing import List, Optional
from slproxy.core.plugin_base import Account


class AccountRouter:
    """
    Manages accounts per provider plugin.
    Implements routing strategies:
    - fallback: strictly by priority/order, falling back if an account is rate-limited or fails
    - round_robin: cyclically select healthy accounts
    - cooldown tracking: rate-limited accounts enter cooldown with backoff
    """
    def __init__(self):
        self.rr_indices = {}

    def select_account(self, accounts: List[Account], strategy: str = "fallback") -> Optional[Account]:
        raise NotImplementedError

    def mark_rate_limited(self, account: Account, cooldown_seconds: float = 60.0):
        raise NotImplementedError

    def mark_success(self, account: Account):
        raise NotImplementedError

    def mark_error(self, account: Account, error_msg: str):
        raise NotImplementedError
