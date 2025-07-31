import os
import pandas as pd
import sqlite3
from datetime import datetime
import json
from typing import Dict, Any
import openai
from langchain.chat_models import ChatOpenAI
from text_to_sql import create_model, get_sql_query

class AnalysisService:
    def __init__(self, excel_file: str, api_key: str):
        self.excel_file = excel_file
        self.client = openai.OpenAI(api_key=api_key)
        self.api_key = api_key

    def _get_schema(self) -> str:
        return """
            Date DATE,           -- Stored in YYYY-MM-DD format
            Description TEXT,    -- Text description of the transaction
            Amount FLOAT,       -- Positive number representing transaction amount
            Category TEXT,      -- Transaction category (e.g., Food, Transport, Salary)
            Type TEXT          -- Either "Income" or "Expense"
        """

    def analyze_spending(self, query: str) -> str:
        """Analyze spending patterns based on user query"""
        try:
            if not os.path.exists(self.excel_file):
                return "No transaction data available for analysis."
                
            # Read the transactions data
            df = pd.read_excel(self.excel_file, sheet_name='Expenses')
            if df.empty:
                return "No transactions found for analysis."
                
            # Convert date column to datetime
            df['Date'] = pd.to_datetime(df['Date'])
            
            # Set up LLM and get SQL query
            llm = ChatOpenAI(
                openai_api_key=self.api_key,
                model_name="gpt-3.5-turbo",
            )

            model = create_model(llm=llm)
            model.load_schema_as_string(self._get_schema())

            # Convert user's query to SQL
            llm_output = get_sql_query(model, query)
            sql_query = llm_output.message

            print('SQL Query:', sql_query)
            
            # Execute SQL query
            conn = sqlite3.connect(':memory:')
            df.to_sql('Expenses', conn, index=False, if_exists='replace')
            
            try:
                result_df = pd.read_sql_query(sql_query, conn)
                filtered_df = result_df
            except Exception as e:
                print(f"Error executing SQL query: {e}")
                filtered_df = df
            finally:
                conn.close()
                
            # Prepare data context for analysis
            data_context = {
                'total_transactions': len(filtered_df),
                'date_range': f"from {filtered_df['Date'].min().strftime('%Y-%m-%d')} to {filtered_df['Date'].max().strftime('%Y-%m-%d')}",
                'categories': filtered_df['Category'].unique().tolist(),
                'total_spending': filtered_df[filtered_df['Type'] == 'Expense']['Amount'].sum(),
                'total_income': filtered_df[filtered_df['Type'] == 'Income']['Amount'].sum(),
                'transactions': json.loads(filtered_df.to_json(orient='records', date_format='iso'))
            }
            
            # Generate analysis using OpenAI
            prompt = self._create_analysis_prompt(query, data_context)
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a financial analyst providing insights from transaction data. Be specific and include numerical details when relevant."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            analysis = response.choices[0].message.content
            
            # Add charts if requested
            if 'chart' in query.lower() or 'visual' in query.lower() or 'graph' in query.lower():
                analysis = self._add_charts_to_analysis(analysis, df)
            
            return analysis
            
        except Exception as e:
            return f"Error analyzing spending: {str(e)}"

    def _create_analysis_prompt(self, query: str, data_context: Dict[str, Any]) -> str:
        """Create the analysis prompt with the given context"""
        return f"""
        Analyze the following financial data based on this query: "{query}"

        Summary:
        - {data_context['total_transactions']} transactions
        - Date range: {data_context['date_range']}
        - Categories: {', '.join(data_context['categories'])}
        - Total spending: ${data_context['total_spending']:.2f}
        - Total income: ${data_context['total_income']:.2f}

        Detailed transactions:
        {json.dumps(data_context['transactions'], indent=2)}

        Generate a detailed analysis focusing on the user's query. Include relevant statistics and insights.
        If the query asks for comparisons or trends, calculate and include them.
        If it's about specific categories or time periods, provide focused analysis on those aspects.
        """

    def _add_charts_to_analysis(self, analysis: str, df: pd.DataFrame) -> str:
        """Add charts to the analysis and return updated analysis text"""
        category_spending = df[df['Type'] == 'Expense'].groupby('Category')['Amount'].sum()
        chart_data = pd.DataFrame({
            'Category': category_spending.index,
            'Amount': category_spending.values
        })
        
        # Save chart to Excel
        with pd.ExcelWriter(self.excel_file, engine='openpyxl', mode='a') as writer:
            chart_data.to_excel(writer, sheet_name='Analysis_Charts', index=False)
        
        return analysis + "\n\nSpending by Category Chart has been generated in the Excel file."
