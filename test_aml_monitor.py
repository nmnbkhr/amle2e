"""
Unit tests for the AML Monitor
"""
import unittest
from datetime import datetime
from aml_monitor import AMLMonitor
from transaction import Transaction


class TestAMLMonitor(unittest.TestCase):
    """Test cases for AMLMonitor class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.monitor = AMLMonitor(threshold=10000.0, velocity_limit=5)
    
    def test_monitor_initialization(self):
        """Test monitor initialization"""
        self.assertEqual(self.monitor.threshold, 10000.0)
        self.assertEqual(self.monitor.velocity_limit, 5)
        self.assertEqual(len(self.monitor.transactions), 0)
    
    def test_add_transaction(self):
        """Test adding a transaction"""
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
        
        self.monitor.add_transaction(txn)
        self.assertEqual(len(self.monitor.transactions), 1)
    
    def test_risk_score_low_amount(self):
        """Test risk score for low amount transaction"""
        txn = Transaction(
            transaction_id="TXN001",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=1000.0,
            currency="USD",
            transaction_type="DEPOSIT",
            country="US"
        )
        
        score = self.monitor.calculate_risk_score(txn)
        self.assertLessEqual(score, 30.0)  # Should be low risk
    
    def test_risk_score_high_amount(self):
        """Test risk score for high amount transaction"""
        txn = Transaction(
            transaction_id="TXN002",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=50000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US"
        )
        
        score = self.monitor.calculate_risk_score(txn)
        self.assertGreaterEqual(score, 50.0)  # Should be high risk
    
    def test_risk_score_wire_transfer(self):
        """Test risk score for wire transfer"""
        txn = Transaction(
            transaction_id="TXN003",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=5000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US"
        )
        
        score = self.monitor.calculate_risk_score(txn)
        self.assertGreaterEqual(score, 20.0)  # Wire transfers add risk
    
    def test_risk_score_high_risk_country(self):
        """Test risk score for high-risk country"""
        txn = Transaction(
            transaction_id="TXN004",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=5000.0,
            currency="USD",
            transaction_type="TRANSFER",
            country="XX"
        )
        
        score = self.monitor.calculate_risk_score(txn)
        self.assertGreaterEqual(score, 10.0)  # High-risk country adds risk
    
    def test_velocity_detection(self):
        """Test velocity pattern detection"""
        sender_id = "ACC001"
        
        # Add multiple transactions from same sender
        for i in range(6):
            txn = Transaction(
                transaction_id=f"TXN00{i}",
                timestamp=datetime.now(),
                sender_id=sender_id,
                receiver_id=f"ACC00{i}",
                amount=1000.0,
                currency="USD",
                transaction_type="TRANSFER",
                country="US"
            )
            self.monitor.evaluate_transaction(txn)
        
        # Get the last transaction's risk score
        last_txn = self.monitor.transactions[-1]
        self.assertGreaterEqual(last_txn.risk_score, 30.0)  # Velocity should add risk
    
    def test_evaluate_transaction(self):
        """Test evaluating a transaction"""
        txn = Transaction(
            transaction_id="TXN001",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=60000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US"
        )
        
        result = self.monitor.evaluate_transaction(txn)
        
        self.assertIsNotNone(result.risk_score)
        self.assertIsNotNone(result.is_suspicious)
        self.assertTrue(result.is_suspicious)  # High amount wire should be flagged
    
    def test_get_suspicious_transactions(self):
        """Test getting suspicious transactions"""
        # Add normal transaction
        normal_txn = Transaction(
            transaction_id="TXN001",
            timestamp=datetime.now(),
            sender_id="ACC001",
            receiver_id="ACC002",
            amount=1000.0,
            currency="USD",
            transaction_type="TRANSFER",
            country="US"
        )
        self.monitor.evaluate_transaction(normal_txn)
        
        # Add suspicious transaction
        suspicious_txn = Transaction(
            transaction_id="TXN002",
            timestamp=datetime.now(),
            sender_id="ACC003",
            receiver_id="ACC004",
            amount=100000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US"
        )
        self.monitor.evaluate_transaction(suspicious_txn)
        
        suspicious = self.monitor.get_suspicious_transactions()
        self.assertEqual(len(suspicious), 1)
        self.assertEqual(suspicious[0].transaction_id, "TXN002")
    
    def test_get_statistics(self):
        """Test getting statistics"""
        # Add some transactions
        for i in range(5):
            txn = Transaction(
                transaction_id=f"TXN00{i}",
                timestamp=datetime.now(),
                sender_id="ACC001",
                receiver_id="ACC002",
                amount=1000.0 * (i + 1),
                currency="USD",
                transaction_type="TRANSFER",
                country="US"
            )
            self.monitor.evaluate_transaction(txn)
        
        stats = self.monitor.get_statistics()
        
        self.assertEqual(stats['total_transactions'], 5)
        self.assertGreaterEqual(stats['total_amount'], 0)
        self.assertGreaterEqual(stats['average_risk_score'], 0)
        self.assertIsInstance(stats['suspicious_rate'], float)


if __name__ == '__main__':
    unittest.main()
