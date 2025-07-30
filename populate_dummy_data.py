import pandas as pd
from datetime import datetime, timedelta
import random
import os

# File path
EXCEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'transactions.xlsx')

# Categories and their typical expense ranges
CATEGORIES = {
    'Food': (10, 100),
    'Transport': (5, 50),
    'Shopping': (20, 200),
    'Entertainment': (15, 150),
    'Utilities': (50, 300),
    'Rent': (800, 2000),
    'Salary': (3000, 5000),
    'Freelance': (500, 1500),
    'Healthcare': (20, 200),
    'Education': (50, 500)
}

# Description templates for each category
DESCRIPTIONS = {
    'Food': ['Groceries', 'Restaurant', 'Coffee shop', 'Take-out', 'Lunch', 'Dinner'],
    'Transport': ['Bus fare', 'Train ticket', 'Taxi', 'Fuel', 'Car maintenance', 'Parking'],
    'Shopping': ['Clothing', 'Electronics', 'Home goods', 'Books', 'Accessories'],
    'Entertainment': ['Movie tickets', 'Concert', 'Gaming', 'Streaming service', 'Sports event'],
    'Utilities': ['Electricity bill', 'Water bill', 'Internet bill', 'Phone bill', 'Gas bill'],
    'Rent': ['Monthly rent', 'Apartment rent', 'Housing payment'],
    'Salary': ['Monthly salary', 'Work payment', 'Regular income'],
    'Freelance': ['Project payment', 'Consulting fee', 'Freelance work'],
    'Healthcare': ['Doctor visit', 'Medicine', 'Health insurance', 'Dental care'],
    'Education': ['Course fee', 'Books', 'Online class', 'Training program', 'Workshop']
}

def generate_dummy_data(num_months=3):
    # Initialize empty list for transactions
    transactions = []
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=num_months*30)
    current_date = start_date
    
    # Generate monthly recurring transactions
    while current_date <= end_date:
        # Monthly salary (income)
        salary = random.randint(CATEGORIES['Salary'][0], CATEGORIES['Salary'][1])
        transactions.append({
            'Date': current_date,
            'Description': random.choice(DESCRIPTIONS['Salary']),
            'Amount': salary,
            'Category': 'Salary',
            'Type': 'Income'
        })
        
        # Monthly rent (expense)
        rent = random.randint(CATEGORIES['Rent'][0], CATEGORIES['Rent'][1])
        transactions.append({
            'Date': current_date,
            'Description': random.choice(DESCRIPTIONS['Rent']),
            'Amount': rent,
            'Category': 'Rent',
            'Type': 'Expense'
        })
        
        # Monthly utilities
        for utility in ['Electricity bill', 'Water bill', 'Internet bill']:
            amount = random.randint(CATEGORIES['Utilities'][0], CATEGORIES['Utilities'][1])
            transactions.append({
                'Date': current_date + timedelta(days=random.randint(0, 5)),
                'Description': utility,
                'Amount': amount,
                'Category': 'Utilities',
                'Type': 'Expense'
            })
        
        # Generate some random transactions throughout the month
        for _ in range(30):  # Approximately one transaction per day
            category = random.choice(list(CATEGORIES.keys()))
            # Skip rent and salary as they're handled separately
            if category in ['Rent', 'Salary']:
                continue
                
            amount = random.randint(CATEGORIES[category][0], CATEGORIES[category][1])
            trans_type = 'Income' if category in ['Freelance'] else 'Expense'
            
            transactions.append({
                'Date': current_date + timedelta(days=random.randint(0, 30)),
                'Description': random.choice(DESCRIPTIONS[category]),
                'Amount': amount,
                'Category': category,
                'Type': trans_type
            })
        
        # Move to next month
        current_date += timedelta(days=30)
    
    # Create DataFrame and sort by date
    df = pd.DataFrame(transactions)
    df = df.sort_values('Date')
    
    # Calculate running balance
    balance = 0
    for _, row in df.iterrows():
        if row['Type'] == 'Income':
            balance += row['Amount']
        else:
            balance -= row['Amount']
    
    # Save to Excel
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Expenses')
        pd.DataFrame({'Balance': [balance]}).to_excel(writer, index=False, sheet_name='Balance')
    
    print(f"Generated {len(transactions)} transactions over {num_months} months")
    print(f"Final balance: ${balance:.2f}")

if __name__ == "__main__":
    # Generate 3 months of dummy data
    generate_dummy_data(3)
