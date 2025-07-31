import os
import json
import gradio as gr
from dotenv import load_dotenv
from services.transaction_service import TransactionService
from services.analysis_service import AnalysisService
from services.utils import initialize_excel_file

# Load environment variables
load_dotenv()

# Get the API key from environment
api_key = os.getenv('API_KEY')
if not api_key:
    raise ValueError("API_KEY not found in .env file. Please add your OpenAI API key to the .env file.")

# File paths
EXCEL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'transactions.xlsx')

# Initialize services
transaction_service = TransactionService(EXCEL_FILE, api_key)
analysis_service = AnalysisService(EXCEL_FILE, api_key)

# Initialize Excel file if it doesn't exist
initialize_excel_file(EXCEL_FILE)

def handle_transaction(text: str) -> str:
    """Handle transaction input from Gradio interface"""
    if not text:
        return "Please enter a transaction or removal request."

    is_removal = text.lower().startswith(('remove', 'delete'))
    if is_removal:
        text = text.replace('remove', '').replace('delete', '').strip()

    transactions = transaction_service.parse_transaction(text)
    if not transactions:
        return "Could not parse the transaction(s). Please try again."

    results = []
    for transaction_data in transactions:
        if is_removal:
            success, message = transaction_service.remove_transaction(transaction_data)
        else:
            success, message = transaction_service.update_transaction(transaction_data)
        results.append(message)

    return "\n".join(results)

def update_balance(amount: float) -> str:
    """Update the total balance"""
    try:
        amount = float(amount)
        if transaction_service.set_balance(amount):
            return f"Balance updated successfully to: ${amount:.2f}"
        return "Error updating balance."
    except ValueError:
        return "Please enter a valid number."
    except Exception as e:
        return f"Error: {str(e)}"

def analyze_spending(query: str) -> str:
    """Analyze spending patterns based on user query"""
    return analysis_service.analyze_spending(query)

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
            
        with gr.Tab("Reports & Analysis"):
            gr.Markdown("""
            ### Spending Analysis
            
            Ask questions about your spending patterns. Examples:
            - Compare this week's spending to my average weekly spending
            - What category do I spend the most on?
            - Analyze my spending for this month
            - Show me charts of my spending by category
            - Compare income vs expenses for the last 3 months
            """)
            analysis_input = gr.Textbox(
                label="Enter your analysis question",
                placeholder="e.g., What category do I spend the most on?"
            )
            analysis_output = gr.Textbox(
                label="Analysis Result",
                lines=10
            )
            analysis_button = gr.Button("Get Analysis")
            analysis_button.click(
                fn=analyze_spending,
                inputs=analysis_input,
                outputs=analysis_output
            )

if __name__ == "__main__":
    app.launch(share=True)
