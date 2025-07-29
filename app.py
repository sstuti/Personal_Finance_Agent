import os
import json
import gradio as gr
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import openai

# Load environment variables
load_dotenv()

# Get the API key from environment
api_key = os.getenv('API_KEY')
if not api_key:
    raise ValueError("API_KEY not found in .env file. Please add your OpenAI API key to the .env file.")

# Create OpenAI client
client = openai.OpenAI(api_key=api_key)

# File paths
EXCEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'transactions.xlsx')
TOTAL_MONEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'total_money.json')

# Create Excel file if it doesn't exist
if not os.path.exists(EXCEL_FILE):
    df = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type'])
    with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Expenses')
        pd.DataFrame({'Balance': [0.0]}).to_excel(writer, index=False, sheet_name='Balance')

def get_balance():
    """Read the current balance from the Balance sheet"""
    if os.path.exists(EXCEL_FILE):
        try:
            all_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
            if 'Balance' in all_sheets:
                balance_df = all_sheets['Balance']
                if not balance_df.empty and 'Balance' in balance_df.columns:
                    return float(balance_df['Balance'].iloc[0])
        except Exception as e:
            print(f"Error reading balance: {e}")
    return 0.0

def set_balance(new_balance):
    """Set the user's total balance in the Balance sheet"""
    try:
        if os.path.exists(EXCEL_FILE):
            all_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
        else:
            all_sheets = {}
        
        # Update or create Balance sheet
        balance_df = pd.DataFrame({'Balance': [float(new_balance)]})
        all_sheets['Balance'] = balance_df
        
        # Write all sheets back
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            for sheet, sheet_df in all_sheets.items():
                sheet_df.to_excel(writer, index=False, sheet_name=sheet)
        return True
    except Exception as e:
        print(f"Error setting balance: {e}")
        return False

def parse_transaction(text):
    """Use OpenAI to parse transaction details from natural language input"""
    current_date = datetime.now().strftime('%Y-%m-%d')
    
    prompt = f"""
    Parse the following financial transaction(s) into a structured format. If multiple transactions are mentioned, return a list of JSON objects.
    Text: "{text}"
    
    Extract and return JSON with these fields for each transaction:
    - date: string in YYYY-MM-DD format (if no date is mentioned, use "{current_date}")
    - amount: number (positive)
    - description: string
    - category: string (e.g., Food, Transport, Salary, etc.)
    - type: string (either "Income" or "Expense")
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": f"You are a financial transaction parser. Respond only with valid JSON. For relative dates like 'yesterday' or 'last week', convert them to actual dates based on the current date being {current_date}. If multiple transactions are mentioned, return a list of JSON objects. If no date is mentioned, use {current_date}."},
                {"role": "user", "content": prompt}
            ]
        )
        
        parsed = json.loads(response.choices[0].message.content)
        if isinstance(parsed, dict):
            return [parsed]
        return parsed
    except Exception as e:
        return None

def update_transaction(transaction_data):
    """Add a new transaction and update balance"""
    try:
        # Read existing data
        if os.path.exists(EXCEL_FILE):
            all_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
            df = all_sheets.get('Expenses', pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type']))
        else:
            all_sheets = {}
            df = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type'])
        
        # Create new row
        new_row = pd.DataFrame([{
            'Date': pd.to_datetime(transaction_data['date']),
            'Description': transaction_data['description'],
            'Amount': transaction_data['amount'],
            'Category': transaction_data['category'],
            'Type': transaction_data['type']
        }])
        
        # Append and sort
        df = pd.concat([df, new_row], ignore_index=True)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date', ascending=True).reset_index(drop=True)
        df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # Update Expenses sheet
        all_sheets['Expenses'] = df
        
        # Update balance
        current_balance = get_balance()
        if transaction_data['type'].lower() == 'income':
            new_balance = current_balance + float(transaction_data['amount'])
        else:
            new_balance = current_balance - float(transaction_data['amount'])
        
        # Save everything
        with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
            for sheet, sheet_df in all_sheets.items():
                sheet_df.to_excel(writer, index=False, sheet_name=sheet)
        
        set_balance(new_balance)
        return True, f"Transaction added. New balance: ${new_balance:.2f}"
    except Exception as e:
        return False, f"Error: {str(e)}"

def handle_transaction(text):
    """Handle transaction input from Gradio interface"""
    if not text:
        return "Please enter a transaction or removal request."

    is_removal = text.lower().startswith(('remove', 'delete'))
    if is_removal:
        text = text.replace('remove', '').replace('delete', '').strip()

    transactions = parse_transaction(text)
    if not transactions:
        return "Could not parse the transaction(s). Please try again."

    results = []
    for transaction_data in transactions:
        try:
            # Read all sheets
            if os.path.exists(EXCEL_FILE):
                all_sheets = pd.read_excel(EXCEL_FILE, sheet_name=None)
                df = all_sheets.get('Expenses', pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type']))
            else:
                if is_removal:
                    return "No transactions file exists."
                all_sheets = {}
                df = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type'])

            if is_removal:
                # Find matching transaction
                mask = (
                    (df['Date'] == transaction_data['date']) &
                    (df['Description'] == transaction_data['description']) &
                    (df['Amount'] == transaction_data['amount'])
                )
                
                if not mask.any():
                    results.append("Transaction not found.")
                    continue

                # Get transaction details before removal
                removed_type = df.loc[mask, 'Type'].iloc[0].lower()
                removed_amount = float(df.loc[mask, 'Amount'].iloc[0])
                
                # Remove transaction
                df = df[~mask]
                
                # Update balance (subtract income or add back expense)
                current_balance = get_balance()
                if removed_type == 'income':
                    new_balance = current_balance - removed_amount
                else:
                    new_balance = current_balance + removed_amount
                
                results.append(f"Transaction removed. New balance: ${new_balance:.2f}")
            
            else:
                # Add new transaction
                new_row = pd.DataFrame([{
                    'Date': pd.to_datetime(transaction_data['date']),
                    'Description': transaction_data['description'],
                    'Amount': transaction_data['amount'],
                    'Category': transaction_data['category'],
                    'Type': transaction_data['type']
                }])
                
                # Append and sort
                df = pd.concat([df, new_row], ignore_index=True)
                df['Date'] = pd.to_datetime(df['Date'])
                df = df.sort_values('Date', ascending=True).reset_index(drop=True)
                df['Date'] = df['Date'].dt.strftime('%Y-%m-%d')
                
                # Update balance (add income or subtract expense)
                current_balance = get_balance()
                if transaction_data['type'].lower() == 'income':
                    new_balance = current_balance + float(transaction_data['amount'])
                else:
                    new_balance = current_balance - float(transaction_data['amount'])
                
                results.append(f"Transaction added. New balance: ${new_balance:.2f}")

            # Update sheets and save
            all_sheets['Expenses'] = df
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                for sheet, sheet_df in all_sheets.items():
                    sheet_df.to_excel(writer, index=False, sheet_name=sheet)
            
            set_balance(new_balance)

        except Exception as e:
            results.append(f"Error: {str(e)}")

    return "\n".join(results)

def update_balance(amount):
    """Update the total balance"""
    try:
        amount = float(amount)
        if set_balance(amount):
            return f"Balance updated successfully to: ${amount:.2f}"
        return "Error updating balance."
    except ValueError:
        return "Please enter a valid number."
    except Exception as e:
        return f"Error: {str(e)}"

# Create Gradio interface
with gr.Blocks(title="Finance Tracker") as app:
    gr.Markdown("# Personal Finance Tracker")
    
    with gr.Tabs():
        with gr.Tab("Transactions"):
            gr.Markdown(f"""
            ### Add or Remove Transactions=

            Examples:
            Add transactions:
            - "Spent $50 on groceries"
            - "Received $1000 salary"
            - "$30 for lunch and $20 for coffee"

            Remove transactions:
            - "remove $50 groceries"
            - "remove $1000 salary from July 25th"
            """)
            transaction_input = gr.Textbox(
                label="Enter transaction(s)",
                placeholder="e.g., Spent $50 on groceries"
            )
            transaction_output = gr.Textbox(label="Result")
            transaction_button = gr.Button("Submit Transaction")
            transaction_button.click(
                fn=handle_transaction,
                inputs=transaction_input,
                outputs=transaction_output
            )
        
        with gr.Tab("Set Balance"):
            gr.Markdown("### Set Total Balance")
            balance_input = gr.Number(label="Enter new balance")
            balance_output = gr.Textbox(label="Result")
            balance_button = gr.Button("Update Balance")
            balance_button.click(
                fn=update_balance,
                inputs=balance_input,
                outputs=balance_output
            )

if __name__ == "__main__":
    app.launch()
