"""
Unit tests for the Transaction model
"""
import unittest
from datetime import datetime
from transaction import Transaction


class TestTransaction(unittest.TestCase):
    """Test cases for Transaction class"""
    
    def test_transaction_creation(self):
        """Test creating a basic transaction"""
        txn = Transaction(
            transaction_id="TXN001",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=1000.0,
            currency="USD",
            transaction_type="TRANSFER",
            country="US"
        )
        
        self.assertEqual(txn.transaction_id, "TXN001")
        self.assertEqual(txn.sender_id, "ACC001")
        self.assertEqual(txn.receiver_id, "ACC002")
        self.assertEqual(txn.amount, 1000.0)
        self.assertEqual(txn.currency, "USD")
        self.assertEqual(txn.transaction_type, "TRANSFER")
        self.assertEqual(txn.country, "US")
        self.assertIsNone(txn.risk_score)
        self.assertIsNone(txn.is_suspicious)
    
    def test_transaction_with_risk_score(self):
        """Test transaction with risk score"""
        txn = Transaction(
            transaction_id="TXN002",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=50000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US",
            risk_score=75.0,
            is_suspicious=True
        )
        
        self.assertEqual(txn.risk_score, 75.0)
        self.assertTrue(txn.is_suspicious)
    
    def test_transaction_str(self):
        """Test transaction string representation"""
        txn = Transaction(
            transaction_id="TXN003",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=1000.0,
            currency="EUR",
            transaction_type="TRANSFER",
            country="DE"
        )
        
        str_repr = str(txn)
        self.assertIn("TXN003", str_repr)
        self.assertIn("ACC001", str_repr)
        self.assertIn("ACC002", str_repr)
        self.assertIn("1000.0", str_repr)
        self.assertIn("EUR", str_repr)


if __name__ == '__main__':
    unittest.main()
