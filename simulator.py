"""
AML Transaction Simulator
Generates simulated transactions for testing AML monitoring
"""
import random
import string
from datetime import datetime, timedelta
from typing import List
from transaction import Transaction


class TransactionSimulator:
    """
    Simulator for generating test transactions
    """
    
    def __init__(self, seed: int = None):
        """
        Initialize the simulator
        
        Args:
            seed: Random seed for reproducibility
        """
        if seed is not None:
            random.seed(seed)
            
        self.transaction_types = ['DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'WIRE', 'INTERNATIONAL']
        self.currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF']
        self.countries = ['US', 'UK', 'DE', 'FR', 'JP', 'CH', 'XX', 'YY']
        
    def generate_transaction_id(self) -> str:
        """Generate a unique transaction ID"""
        return 'TXN' + ''.join(random.choices(string.digits, k=10))
    
    def generate_account_id(self) -> str:
        """Generate a random account ID"""
        return 'ACC' + ''.join(random.choices(string.digits, k=8))
    
    def generate_normal_transaction(self, timestamp: datetime = None) -> Transaction:
        """
        Generate a normal (non-suspicious) transaction
        
        Args:
            timestamp: Transaction timestamp (default: now)
            
        Returns:
            A normal transaction
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        return Transaction(
            transaction_id=self.generate_transaction_id(),
            timestamp=timestamp,
            sender_id=self.generate_account_id(),
            receiver_id=self.generate_account_id(),
            amount=round(random.uniform(10, 5000), 2),
            currency=random.choice(self.currencies),
            transaction_type=random.choice(['DEPOSIT', 'WITHDRAWAL', 'TRANSFER']),
            country=random.choice(['US', 'UK', 'DE', 'FR', 'JP'])
        )
    
    def generate_suspicious_transaction(self, timestamp: datetime = None) -> Transaction:
        """
        Generate a suspicious transaction
        
        Args:
            timestamp: Transaction timestamp (default: now)
            
        Returns:
            A suspicious transaction
        """
        if timestamp is None:
            timestamp = datetime.now()
            
        # Create patterns that should be flagged
        suspicious_patterns = [
            # Large amount
            {'amount': random.uniform(50000, 200000), 'type': 'WIRE'},
            # International wire
            {'amount': random.uniform(15000, 50000), 'type': 'INTERNATIONAL'},
            # High-risk country
            {'amount': random.uniform(8000, 15000), 'type': 'WIRE', 'country': 'XX'}
        ]
        
        pattern = random.choice(suspicious_patterns)
        
        return Transaction(
            transaction_id=self.generate_transaction_id(),
            timestamp=timestamp,
            sender_id=self.generate_account_id(),
            receiver_id=self.generate_account_id(),
            amount=round(pattern.get('amount', 20000), 2),
            currency=random.choice(self.currencies),
            transaction_type=pattern.get('type', 'WIRE'),
            country=pattern.get('country', random.choice(['US', 'UK', 'DE']))
        )
    
    def generate_batch(self, count: int, suspicious_ratio: float = 0.1) -> List[Transaction]:
        """
        Generate a batch of transactions
        
        Args:
            count: Number of transactions to generate
            suspicious_ratio: Ratio of suspicious transactions (0.0 to 1.0)
            
        Returns:
            List of transactions
        """
        transactions = []
        start_time = datetime.now() - timedelta(days=7)
        
        for i in range(count):
            # Distribute transactions over time
            timestamp = start_time + timedelta(
                seconds=random.randint(0, 7 * 24 * 60 * 60)
            )
            
            # Decide if this should be suspicious
            if random.random() < suspicious_ratio:
                transaction = self.generate_suspicious_transaction(timestamp)
            else:
                transaction = self.generate_normal_transaction(timestamp)
                
            transactions.append(transaction)
        
        # Sort by timestamp
        transactions.sort(key=lambda t: t.timestamp)
        
        return transactions
    
    def generate_velocity_pattern(self, sender_id: str, count: int = 10) -> List[Transaction]:
        """
        Generate a velocity pattern (many transactions from same sender)
        
        Args:
            sender_id: The sender account ID
            count: Number of transactions to generate
            
        Returns:
            List of transactions from the same sender
        """
        transactions = []
        base_time = datetime.now()
        
        for i in range(count):
            timestamp = base_time + timedelta(minutes=i * 5)
            transaction = Transaction(
                transaction_id=self.generate_transaction_id(),
                timestamp=timestamp,
                sender_id=sender_id,
                receiver_id=self.generate_account_id(),
                amount=round(random.uniform(1000, 5000), 2),
                currency=random.choice(self.currencies),
                transaction_type='TRANSFER',
                country=random.choice(['US', 'UK', 'DE'])
            )
            transactions.append(transaction)
            
        return transactions
