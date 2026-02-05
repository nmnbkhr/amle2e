"""
AML Transaction Model
Defines the structure of a transaction for AML monitoring
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Transaction:
    """Represents a financial transaction"""
    transaction_id: str
    timestamp: datetime
    sender_id: str
    receiver_id: str
    amount: float
    currency: str
    transaction_type: str
    country: str
    risk_score: Optional[float] = None
    is_suspicious: Optional[bool] = None

    def __str__(self):
        return (f"Transaction({self.transaction_id}: "
                f"{self.sender_id} -> {self.receiver_id}, "
                f"{self.amount} {self.currency})")
