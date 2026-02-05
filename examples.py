#!/usr/bin/env python3
"""
Example script demonstrating various AML system use cases
"""
from aml_monitor import AMLMonitor
from simulator import TransactionSimulator
from transaction import Transaction
from datetime import datetime


def example_basic_monitoring():
    """Example: Basic transaction monitoring"""
    print("=" * 70)
    print("EXAMPLE 1: Basic Transaction Monitoring")
    print("=" * 70)
    print()
    
    monitor = AMLMonitor(threshold=10000.0)
    
    # Create a few manual transactions
    transactions = [
        Transaction(
            transaction_id="TXN001",
            timestamp=datetime.now(),
            sender_id="ACC123",
            receiver_id="ACC456",
            amount=5000.0,
            currency="USD",
            transaction_type="TRANSFER",
            country="US"
        ),
        Transaction(
            transaction_id="TXN002",
            timestamp=datetime.now(),
            sender_id="ACC789",
            receiver_id="ACC012",
            amount=75000.0,
            currency="USD",
            transaction_type="WIRE",
            country="US"
        ),
    ]
    
    for txn in transactions:
        result = monitor.evaluate_transaction(txn)
        status = "SUSPICIOUS" if result.is_suspicious else "NORMAL"
        print(f"{result.transaction_id}: ${result.amount:,.2f} - {status} (Risk: {result.risk_score:.1f})")
    
    print()


def example_velocity_detection():
    """Example: Detecting velocity patterns"""
    print("=" * 70)
    print("EXAMPLE 2: Velocity Pattern Detection")
    print("=" * 70)
    print()
    
    monitor = AMLMonitor(velocity_limit=3)
    simulator = TransactionSimulator(seed=100)
    
    # Generate multiple transactions from same sender
    sender_id = "ACC_SUSPECT"
    velocity_txns = simulator.generate_velocity_pattern(sender_id, count=5)
    
    print(f"Monitoring {len(velocity_txns)} transactions from {sender_id}:")
    print()
    
    for txn in velocity_txns:
        result = monitor.evaluate_transaction(txn)
        status = "⚠️  FLAGGED" if result.is_suspicious else "✓ OK"
        print(f"  {result.transaction_id}: Risk={result.risk_score:5.1f} {status}")
    
    print()


def example_batch_processing():
    """Example: Processing large batch of transactions"""
    print("=" * 70)
    print("EXAMPLE 3: Batch Processing with Statistics")
    print("=" * 70)
    print()
    
    monitor = AMLMonitor()
    simulator = TransactionSimulator(seed=200)
    
    # Generate a large batch
    batch_size = 100
    transactions = simulator.generate_batch(count=batch_size, suspicious_ratio=0.15)
    
    print(f"Processing batch of {batch_size} transactions...")
    
    for txn in transactions:
        monitor.evaluate_transaction(txn)
    
    stats = monitor.get_statistics()
    suspicious = monitor.get_suspicious_transactions()
    
    print()
    print("Results:")
    print(f"  Total Transactions:      {stats['total_transactions']}")
    print(f"  Suspicious Transactions: {stats['suspicious_transactions']}")
    print(f"  Detection Rate:          {stats['suspicious_rate']*100:.2f}%")
    print(f"  Total Amount:            ${stats['total_amount']:,.2f}")
    print(f"  Average Risk Score:      {stats['average_risk_score']:.2f}")
    print()
    
    if suspicious:
        print(f"Top 3 Highest Risk Transactions:")
        sorted_suspicious = sorted(suspicious, key=lambda t: t.risk_score, reverse=True)
        for txn in sorted_suspicious[:3]:
            print(f"  {txn.transaction_id}: ${txn.amount:,.2f} {txn.currency} - Risk: {txn.risk_score:.1f}")
    
    print()


def example_custom_thresholds():
    """Example: Using custom risk thresholds"""
    print("=" * 70)
    print("EXAMPLE 4: Custom Risk Thresholds")
    print("=" * 70)
    print()
    
    # Create monitors with different thresholds
    strict_monitor = AMLMonitor(threshold=5000.0, velocity_limit=3)
    normal_monitor = AMLMonitor(threshold=10000.0, velocity_limit=5)
    lenient_monitor = AMLMonitor(threshold=50000.0, velocity_limit=10)
    
    simulator = TransactionSimulator(seed=300)
    test_txn = Transaction(
        transaction_id="TXN_TEST",
        timestamp=datetime.now(),
        sender_id="ACC001",
        receiver_id="ACC002",
        amount=15000.0,
        currency="USD",
        transaction_type="WIRE",
        country="US"
    )
    
    print(f"Testing transaction: ${test_txn.amount:,.2f} {test_txn.transaction_type}")
    print()
    
    results = [
        ("Strict", strict_monitor),
        ("Normal", normal_monitor),
        ("Lenient", lenient_monitor)
    ]
    
    for name, monitor in results:
        result = monitor.evaluate_transaction(test_txn)
        status = "FLAGGED" if result.is_suspicious else "OK"
        print(f"  {name:8} Monitor: Risk={result.risk_score:5.1f} [{status}]")
    
    print()


def example_international_transfers():
    """Example: Monitoring international transfers"""
    print("=" * 70)
    print("EXAMPLE 5: International Transfer Monitoring")
    print("=" * 70)
    print()
    
    monitor = AMLMonitor()
    
    # Create international transfers
    international_txns = [
        Transaction(
            transaction_id="TXN_INT1",
            timestamp=datetime.now(),
            sender_id="ACC_US_001",
            receiver_id="ACC_UK_002",
            amount=25000.0,
            currency="USD",
            transaction_type="INTERNATIONAL",
            country="UK"
        ),
        Transaction(
            transaction_id="TXN_INT2",
            timestamp=datetime.now(),
            sender_id="ACC_US_003",
            receiver_id="ACC_XX_004",
            amount=15000.0,
            currency="USD",
            transaction_type="WIRE",
            country="XX"  # High-risk country
        ),
    ]
    
    print("Evaluating international transfers:")
    print()
    
    for txn in international_txns:
        result = monitor.evaluate_transaction(txn)
        status = "⚠️  SUSPICIOUS" if result.is_suspicious else "✓ NORMAL"
        print(f"  {result.transaction_id}:")
        print(f"    Amount:   ${result.amount:,.2f}")
        print(f"    Type:     {result.transaction_type}")
        print(f"    Country:  {result.country}")
        print(f"    Risk:     {result.risk_score:.1f}/100")
        print(f"    Status:   {status}")
        print()


def main():
    """Run all examples"""
    example_basic_monitoring()
    example_velocity_detection()
    example_batch_processing()
    example_custom_thresholds()
    example_international_transfers()
    
    print("=" * 70)
    print("All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()
