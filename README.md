# AML E2E - Anti-Money Laundering End-to-End System

A comprehensive Anti-Money Laundering (AML) system with transaction simulator for testing and monitoring financial transactions.

## Features

- **AML Monitor**: Core monitoring system that evaluates transactions for suspicious activity
- **Transaction Simulator**: Generates realistic test transactions including normal and suspicious patterns
- **Risk Scoring**: Multi-factor risk assessment based on:
  - Transaction amount thresholds
  - Transaction velocity (multiple transactions in short time)
  - Transaction types (wire transfers, international transfers)
  - Geographic risk factors
- **Statistics & Reporting**: Comprehensive reporting of monitoring results

## Installation

1. Clone the repository:
```bash
git clone https://github.com/nmnbkhr/amle2e.git
cd amle2e
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

### Run the Demo

Execute the main application to see the AML system in action:

```bash
python main.py
```

This will:
1. Initialize the AML monitor with configurable thresholds
2. Generate a batch of simulated transactions (mix of normal and suspicious)
3. Process all transactions through the AML monitor
4. Display detected suspicious transactions
5. Show comprehensive statistics
6. Demonstrate velocity pattern detection

### Use as a Library

You can also use the components programmatically:

```python
from aml_monitor import AMLMonitor
from simulator import TransactionSimulator
from transaction import Transaction

# Initialize monitor
monitor = AMLMonitor(threshold=10000.0, velocity_limit=5)

# Create simulator
simulator = TransactionSimulator(seed=42)

# Generate transactions
transactions = simulator.generate_batch(count=100, suspicious_ratio=0.1)

# Process transactions
for txn in transactions:
    result = monitor.evaluate_transaction(txn)
    if result.is_suspicious:
        print(f"Suspicious: {result}")

# Get statistics
stats = monitor.get_statistics()
print(stats)
```

## Components

### Transaction Model
- Defines the structure of financial transactions
- Includes metadata like sender, receiver, amount, currency, type, country
- Tracks risk scores and suspicious flags

### AML Monitor
- Core monitoring engine
- Configurable risk thresholds
- Multi-factor risk scoring algorithm
- Transaction history tracking
- Statistical reporting

### Transaction Simulator
- Generates realistic test data
- Creates both normal and suspicious transaction patterns
- Supports velocity pattern generation
- Configurable suspicious transaction ratio
- Time-based transaction distribution

## Risk Factors

The AML system evaluates the following risk factors:

1. **Amount-based Risk**: Large transactions above threshold
2. **Velocity Risk**: Multiple transactions from same sender in short time
3. **Transaction Type Risk**: Wire transfers and international transfers
4. **Geographic Risk**: Transactions from high-risk countries

## Configuration

The AML Monitor can be configured with:
- `threshold`: Amount threshold for flagging large transactions (default: $10,000)
- `velocity_limit`: Number of transactions to trigger velocity alerts (default: 5)

## Example Output

```
============================================================
AML E2E - Anti-Money Laundering End-to-End System
============================================================

Initializing AML Monitor...
  - Amount threshold: $10,000.00
  - Velocity limit: 5 transactions

Generating test transactions...
  - Generated 50 transactions

Processing transactions through AML monitor...
  - Processed 50 transactions

Suspicious Transactions Detected: 8
------------------------------------------------------------
  ID: TXN1234567890
    From: ACC12345678 -> To: ACC87654321
    Amount: 75,000.00 USD
    Type: WIRE
    Country: US
    Risk Score: 60.0/100
    Time: 2026-02-01 14:23:45

============================================================
AML Monitoring Statistics
============================================================
  Total Transactions:        50
  Suspicious Transactions:   8
  Suspicious Rate:           16.00%
  Total Amount Processed:    $425,750.50
  Average Risk Score:        28.50/100
============================================================
```

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.