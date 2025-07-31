import os
import os
import pandas as pd
from datetime import datetime

def initialize_excel_file(file_path: str) -> None:
    """Initialize the Excel file with required sheets if it doesn't exist"""
    if not os.path.exists(file_path):
        df = pd.DataFrame(columns=['Date', 'Description', 'Amount', 'Category', 'Type'])
        with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Expenses')
            pd.DataFrame({'Balance': [0.0]}).to_excel(writer, index=False, sheet_name='Balance')
