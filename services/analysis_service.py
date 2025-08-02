import os
import pandas as pd
from pandasql import sqldf
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
        Available Columns:
        - Date DATE             # Format: YYYY-MM-DD
        - Description TEXT      # Transaction description
        - Amount FLOAT         # Transaction amount (positive number)
        - Category TEXT        # e.g., Food, Transport, Salary
        - Type TEXT           # Either "Income" or "Expense"
        
        Instructions: 
        1. Output format must be EXACTLY like these examples (no prefixes, no explanations):
           SELECT * FROM df WHERE Type = 'Expense'
           SELECT Category, SUM(Amount) FROM df GROUP BY Category
           
        2. IMPORTANT:
           - Start directly with SELECT
           - Use "df" as the table name
           - Do not include "SQL query:" or any other prefix
           - No comments or explanations, just the SQL query
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

            # Convert user's query to SQL and extract the message
            model_output = get_sql_query(model, query)
            sql_query = model_output.message if hasattr(model_output, 'message') else str(model_output)
            sql_query = sql_query.strip()
            
            # Clean up the SQL query by removing common prefixes and extra whitespace
            common_prefixes = ['sql query:', 'query:', 'sql:']
            for prefix in common_prefixes:
                if sql_query.lower().startswith(prefix):
                    sql_query = sql_query[len(prefix):].strip()
            
            # Replace 'Expenses' with 'df' in the query if needed
            sql_query = sql_query.replace(' Expenses ', ' df ')
            sql_query = sql_query.replace('FROM Expenses', 'FROM df')
            sql_query = sql_query.replace('JOIN Expenses', 'JOIN df')
            print(f"Query was: {sql_query}")
            
            # Execute SQL query directly on the DataFrame
            try:
                if not isinstance(sql_query, str):
                    raise ValueError(f"Invalid SQL query type: {type(sql_query)}. Expected string.")
                
                # Define the local environment for SQL query execution
                env = {'df': df}
                
                # Execute the query with the local environment
                filtered_df = sqldf(sql_query, env)
                
                # If the query result is empty, use the original dataframe structure
                if filtered_df.empty:
                    filtered_df = df.head(0)  # Get empty dataframe with same structure
                
                # For aggregate queries that don't return all columns, merge with original structure
                if not all(col in filtered_df.columns for col in ['Date', 'Amount', 'Type', 'Category']):
                    # Create a temporary dataframe with all required columns
                    temp_df = pd.DataFrame(columns=['Date', 'Amount', 'Type', 'Category'])
                    # Merge with the filtered results, keeping all columns from both
                    filtered_df = pd.concat([filtered_df, temp_df], axis=1)
                    filtered_df = filtered_df.loc[:, ~filtered_df.columns.duplicated()]
                
                # Convert data types where columns exist
                if 'Date' in filtered_df.columns:
                    filtered_df['Date'] = pd.to_datetime(filtered_df['Date'])
                if 'Amount' in filtered_df.columns:
                    filtered_df['Amount'] = pd.to_numeric(filtered_df['Amount'], errors='coerce').fillna(0)
                
            except Exception as e:
                print(f"Error executing SQL query: {e}")
                print(f"Query was: {sql_query}")
                raise ValueError(f"Failed to execute SQL query: {str(e)}")

            print(filtered_df)

            # Prepare data context for analysis using filtered data only
            data_context = {
                'total_transactions': len(filtered_df),
                'date_range': (f"from {filtered_df['Date'].min().strftime('%Y-%m-%d')} to {filtered_df['Date'].max().strftime('%Y-%m-%d')}"
                             if 'Date' in filtered_df.columns and not filtered_df['Date'].isna().all()
                             else "date range not applicable"),
                'categories': (filtered_df['Category'].unique().tolist()
                             if 'Category' in filtered_df.columns
                             else []),
                'total_spending': (filtered_df[filtered_df['Type'] == 'Expense']['Amount'].sum()
                                 if 'Type' in filtered_df.columns and 'Amount' in filtered_df.columns
                                 else 0.0),
                'total_income': (filtered_df[filtered_df['Type'] == 'Income']['Amount'].sum()
                               if 'Type' in filtered_df.columns and 'Amount' in filtered_df.columns
                               else 0.0),
                'transactions': (json.loads(filtered_df.to_json(orient='records', date_format='iso'))
                               if not filtered_df.empty
                               else [])
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

    def _add_charts_to_analysis(self, analysis: str, filtered_df: pd.DataFrame) -> str:
        """Add charts to the analysis and return updated analysis text"""
        category_spending = filtered_df[filtered_df['Type'] == 'Expense'].groupby('Category')['Amount'].sum()
        chart_data = pd.DataFrame({
            'Category': category_spending.index,
            'Amount': category_spending.values
        })
        
        # Save chart to Excel
        with pd.ExcelWriter(self.excel_file, engine='openpyxl', mode='a') as writer:
            chart_data.to_excel(writer, sheet_name='Analysis_Charts', index=False)
        
        return analysis + "\n\nSpending by Category Chart has been generated in the Excel file."
