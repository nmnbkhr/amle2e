"""
Main application entry point for AML E2E system
"""
from aml_monitor import AMLMonitor
from simulator import TransactionSimulator


def main():
    """Main function to run AML monitoring with simulator"""
    print("=" * 60)
    print("AML E2E - Anti-Money Laundering End-to-End System")
    print("=" * 60)
    print()
    
    # Initialize AML Monitor
    print("Initializing AML Monitor...")
    monitor = AMLMonitor(threshold=10000.0, velocity_limit=5)
    print(f"  - Amount threshold: ${monitor.threshold:,.2f}")
    print(f"  - Velocity limit: {monitor.velocity_limit} transactions")
    print()
    
    # Initialize Simulator
    print("Initializing Transaction Simulator...")
    simulator = TransactionSimulator(seed=42)
    print("  - Seed: 42 (for reproducibility)")
    print()
    
    # Generate test transactions
    print("Generating test transactions...")
    transactions = simulator.generate_batch(count=50, suspicious_ratio=0.15)
    print(f"  - Generated {len(transactions)} transactions")
    print()
    
    # Process transactions through AML monitor
    print("Processing transactions through AML monitor...")
    for transaction in transactions:
        monitor.evaluate_transaction(transaction)
    print(f"  - Processed {len(transactions)} transactions")
    print()
    
    # Display suspicious transactions
    suspicious = monitor.get_suspicious_transactions()
    print(f"Suspicious Transactions Detected: {len(suspicious)}")
    print("-" * 60)
    
    if suspicious:
        for txn in suspicious[:10]:  # Show first 10
            print(f"  ID: {txn.transaction_id}")
            print(f"    From: {txn.sender_id} -> To: {txn.receiver_id}")
            print(f"    Amount: {txn.amount:,.2f} {txn.currency}")
            print(f"    Type: {txn.transaction_type}")
            print(f"    Country: {txn.country}")
            print(f"    Risk Score: {txn.risk_score:.1f}/100")
            print(f"    Time: {txn.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        
        if len(suspicious) > 10:
            print(f"  ... and {len(suspicious) - 10} more suspicious transactions")
            print()
    
    # Display statistics
    stats = monitor.get_statistics()
    print("=" * 60)
    print("AML Monitoring Statistics")
    print("=" * 60)
    print(f"  Total Transactions:        {stats['total_transactions']}")
    print(f"  Suspicious Transactions:   {stats['suspicious_transactions']}")
    print(f"  Suspicious Rate:           {stats['suspicious_rate']*100:.2f}%")
    print(f"  Total Amount Processed:    ${stats['total_amount']:,.2f}")
    print(f"  Average Risk Score:        {stats['average_risk_score']:.2f}/100")
    print("=" * 60)
    print()
    
    # Test velocity pattern detection
    print("Testing Velocity Pattern Detection...")
    print("-" * 60)
    velocity_txns = simulator.generate_velocity_pattern("ACC12345678", count=7)
    print(f"  - Generated {len(velocity_txns)} transactions from same sender")
    
    for txn in velocity_txns:
        result = monitor.evaluate_transaction(txn)
        status = "FLAGGED" if result.is_suspicious else "OK"
        print(f"    {txn.transaction_id}: Risk={result.risk_score:.1f} [{status}]")
    
    print()
    print("AML E2E system demonstration complete!")


if __name__ == "__main__":
    main()
