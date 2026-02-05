"""
AML Monitor
Core module for Anti-Money Laundering transaction monitoring
"""
from typing import List
from transaction import Transaction


class AMLMonitor:
    """
    AML Monitor for detecting suspicious transactions
    """
    
    def __init__(self, threshold: float = 10000.0, velocity_limit: int = 5):
        """
        Initialize AML Monitor
        
        Args:
            threshold: Amount threshold for flagging large transactions
            velocity_limit: Number of transactions in short time to flag velocity risk
        """
        self.threshold = threshold
        self.velocity_limit = velocity_limit
        self.transactions: List[Transaction] = []
        
    def add_transaction(self, transaction: Transaction) -> None:
        """Add a transaction to the monitoring system"""
        self.transactions.append(transaction)
        
    def calculate_risk_score(self, transaction: Transaction) -> float:
        """
        Calculate risk score for a transaction
        
        Args:
            transaction: Transaction to evaluate
            
        Returns:
            Risk score (0-100)
        """
        risk_score = 0.0
        
        # Large amount risk
        if transaction.amount > self.threshold:
            risk_score += 40.0
        elif transaction.amount > self.threshold * 0.5:
            risk_score += 20.0
            
        # Check transaction velocity for sender
        sender_txns = [t for t in self.transactions 
                       if t.sender_id == transaction.sender_id]
        if len(sender_txns) >= self.velocity_limit:
            risk_score += 30.0
            
        # High-risk transaction types
        if transaction.transaction_type in ['WIRE', 'INTERNATIONAL']:
            risk_score += 20.0
            
        # High-risk countries (example)
        high_risk_countries = ['XX', 'YY', 'ZZ']
        if transaction.country in high_risk_countries:
            risk_score += 10.0
            
        return min(risk_score, 100.0)
    
    def evaluate_transaction(self, transaction: Transaction) -> Transaction:
        """
        Evaluate a transaction for AML risks
        
        Args:
            transaction: Transaction to evaluate
            
        Returns:
            Transaction with updated risk_score and is_suspicious fields
        """
        transaction.risk_score = self.calculate_risk_score(transaction)
        transaction.is_suspicious = transaction.risk_score >= 50.0
        self.add_transaction(transaction)
        return transaction
    
    def get_suspicious_transactions(self) -> List[Transaction]:
        """Get all flagged suspicious transactions"""
        return [t for t in self.transactions if t.is_suspicious]
    
    def get_statistics(self) -> dict:
        """Get monitoring statistics"""
        total = len(self.transactions)
        suspicious = len(self.get_suspicious_transactions())
        
        return {
            'total_transactions': total,
            'suspicious_transactions': suspicious,
            'suspicious_rate': suspicious / total if total > 0 else 0.0,
            'total_amount': sum(t.amount for t in self.transactions),
            'average_risk_score': sum(t.risk_score or 0 for t in self.transactions) / total if total > 0 else 0.0
        }
