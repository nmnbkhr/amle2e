"""
Unit tests for the Transaction Simulator
"""
import unittest
from datetime import datetime
from simulator import TransactionSimulator
from transaction import Transaction


class TestTransactionSimulator(unittest.TestCase):
    """Test cases for TransactionSimulator class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.simulator = TransactionSimulator(seed=42)
    
    def test_simulator_initialization(self):
        """Test simulator initialization"""
        self.assertIsNotNone(self.simulator.transaction_types)
        self.assertIsNotNone(self.simulator.currencies)
        self.assertIsNotNone(self.simulator.countries)
    
    def test_generate_transaction_id(self):
        """Test transaction ID generation"""
        txn_id = self.simulator.generate_transaction_id()
        self.assertTrue(txn_id.startswith("TXN"))
        self.assertEqual(len(txn_id), 13)  # TXN + 10 digits
    
    def test_generate_account_id(self):
        """Test account ID generation"""
        acc_id = self.simulator.generate_account_id()
        self.assertTrue(acc_id.startswith("ACC"))
        self.assertEqual(len(acc_id), 11)  # ACC + 8 digits
    
    def test_generate_normal_transaction(self):
        """Test generating a normal transaction"""
        txn = self.simulator.generate_normal_transaction()
        
        self.assertIsInstance(txn, Transaction)
        self.assertTrue(txn.transaction_id.startswith("TXN"))
        self.assertTrue(txn.sender_id.startswith("ACC"))
        self.assertTrue(txn.receiver_id.startswith("ACC"))
        self.assertGreaterEqual(txn.amount, 10)
        self.assertLessEqual(txn.amount, 5000)
        self.assertIn(txn.currency, self.simulator.currencies)
        self.assertIn(txn.transaction_type, ['DEPOSIT', 'WITHDRAWAL', 'TRANSFER'])
    
    def test_generate_suspicious_transaction(self):
        """Test generating a suspicious transaction"""
        txn = self.simulator.generate_suspicious_transaction()
        
        self.assertIsInstance(txn, Transaction)
        self.assertGreaterEqual(txn.amount, 8000)  # Suspicious amounts are high
        self.assertIn(txn.transaction_type, ['WIRE', 'INTERNATIONAL'])
    
    def test_generate_batch(self):
        """Test generating a batch of transactions"""
        count = 20
        suspicious_ratio = 0.2
        transactions = self.simulator.generate_batch(count, suspicious_ratio)
        
        self.assertEqual(len(transactions), count)
        
        # Check that transactions are sorted by timestamp
        for i in range(len(transactions) - 1):
            self.assertLessEqual(
                transactions[i].timestamp,
                transactions[i + 1].timestamp
            )
    
    def test_generate_batch_suspicious_ratio(self):
        """Test that batch generation respects suspicious ratio"""
        # With seed, we should get consistent results
        simulator = TransactionSimulator(seed=123)
        transactions = simulator.generate_batch(count=100, suspicious_ratio=0.2)
        
        # Count how many would likely be flagged (high amount or risky type)
        high_amount_count = sum(1 for t in transactions if t.amount > 10000)
        risky_type_count = sum(1 for t in transactions 
                               if t.transaction_type in ['WIRE', 'INTERNATIONAL'])
        
        # At least some should be risky
        self.assertGreater(high_amount_count + risky_type_count, 0)
    
    def test_generate_velocity_pattern(self):
        """Test generating velocity pattern"""
        sender_id = "ACC12345678"
        count = 10
        transactions = self.simulator.generate_velocity_pattern(sender_id, count)
        
        self.assertEqual(len(transactions), count)
        
        # All transactions should be from the same sender
        for txn in transactions:
            self.assertEqual(txn.sender_id, sender_id)
        
        # Transactions should be chronologically ordered
        for i in range(len(transactions) - 1):
            self.assertLess(
                transactions[i].timestamp,
                transactions[i + 1].timestamp
            )
    
    def test_reproducibility_with_seed(self):
        """Test that using the same seed produces same results"""
        sim1 = TransactionSimulator(seed=999)
        batch1 = sim1.generate_batch(count=10, suspicious_ratio=0.2)
        
        sim2 = TransactionSimulator(seed=999)
        batch2 = sim2.generate_batch(count=10, suspicious_ratio=0.2)
        
        # With same seed, batches should have same amounts
        for i in range(10):
            self.assertEqual(batch1[i].amount, batch2[i].amount)
            self.assertEqual(batch1[i].currency, batch2[i].currency)
            self.assertEqual(batch1[i].transaction_type, batch2[i].transaction_type)


if __name__ == '__main__':
    unittest.main()
