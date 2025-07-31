import os
import pandas as pd
from datetime import datetime
import json
from typing import List, Dict, Any, Tuple, Optional
import openai

class TransactionService:
    def __init__(self, excel_file: str, api_key: str):
        self.excel_file = excel_file
        self.client = openai.OpenAI(api_key=api_key)

    def parse_transaction(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse transaction details from natural language input"""
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
            response = self.client.chat.completions.create(
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
            print(f"Error parsing transaction: {e}")
            return None

    def update_transaction(self, transaction_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Add a new transaction and update balance"""
        try:
            # Read existing data
            if os.path.exists(self.excel_file):
                all_sheets = pd.read_excel(self.excel_file, sheet_name=None)
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
            current_balance = self.get_balance()
            if transaction_data['type'].lower() == 'income':
                new_balance = current_balance + float(transaction_data['amount'])
            else:
                new_balance = current_balance - float(transaction_data['amount'])
            
            # Save everything
            with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
                for sheet, sheet_df in all_sheets.items():
                    sheet_df.to_excel(writer, index=False, sheet_name=sheet)
            
            self.set_balance(new_balance)
            return True, f"Transaction added. New balance: ${new_balance:.2f}"
        except Exception as e:
            return False, f"Error: {str(e)}"

    def remove_transaction(self, transaction_data: Dict[str, Any]) -> Tuple[bool, str]:
        """Remove a transaction and update balance"""
        try:
            # Read all sheets
            if not os.path.exists(self.excel_file):
                return False, "No transactions file exists."
            
            all_sheets = pd.read_excel(self.excel_file, sheet_name=None)
            df = all_sheets.get('Expenses', pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type']))
            
            # Find matching transaction
            mask = (
                (df['Date'] == transaction_data['date']) &
                (df['Description'] == transaction_data['description']) &
                (df['Amount'] == transaction_data['amount'])
            )
            
            if not mask.any():
                return False, "Transaction not found."

            # Get transaction details before removal
            removed_type = df.loc[mask, 'Type'].iloc[0].lower()
            removed_amount = float(df.loc[mask, 'Amount'].iloc[0])
            
            # Remove transaction
            df = df[~mask]
            
            # Update balance
            current_balance = self.get_balance()
            if removed_type == 'income':
                new_balance = current_balance - removed_amount
            else:
                new_balance = current_balance + removed_amount
            
            # Save changes
            all_sheets['Expenses'] = df
            with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
                for sheet, sheet_df in all_sheets.items():
                    sheet_df.to_excel(writer, index=False, sheet_name=sheet)
            
            self.set_balance(new_balance)
            return True, f"Transaction removed. New balance: ${new_balance:.2f}"
            
        except Exception as e:
            return False, f"Error: {str(e)}"

    def get_balance(self) -> float:
        """Read the current balance from the Balance sheet"""
        if os.path.exists(self.excel_file):
            try:
                all_sheets = pd.read_excel(self.excel_file, sheet_name=None)
                if 'Balance' in all_sheets:
                    balance_df = all_sheets['Balance']
                    if not balance_df.empty and 'Balance' in balance_df.columns:
                        return float(balance_df['Balance'].iloc[0])
            except Exception as e:
                print(f"Error reading balance: {e}")
        return 0.0

    def set_balance(self, new_balance: float) -> bool:
        """Set the user's total balance in the Balance sheet"""
        try:
            if os.path.exists(self.excel_file):
                all_sheets = pd.read_excel(self.excel_file, sheet_name=None)
            else:
                all_sheets = {}
            
            # Update or create Balance sheet
            balance_df = pd.DataFrame({'Balance': [float(new_balance)]})
            all_sheets['Balance'] = balance_df
            
            # Write all sheets back
            with pd.ExcelWriter(self.excel_file, engine='openpyxl') as writer:
                for sheet, sheet_df in all_sheets.items():
                    sheet_df.to_excel(writer, index=False, sheet_name=sheet)
            return True
        except Exception as e:
            print(f"Error setting balance: {e}")
            return False
