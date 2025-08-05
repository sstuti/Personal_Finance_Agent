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
        Table Name: df
        This table contains all financial transactions with the following columns:

        Table Schema:
        CREATE TABLE df (
            Date DATE,             -- Transaction date in YYYY-MM-DD format
            Description TEXT,      -- What the transaction was for
            Amount FLOAT,         -- How much money (positive number)
            Category TEXT,        -- Transaction category (Food, Transport, Salary, etc.)
            Type TEXT            -- Either "Income" or "Expense"
        );

        Example Queries:
        -- For general category analysis (show all transactions):
        SELECT Date, Description, Amount, Category, Type 
        FROM df 
        WHERE Type = 'Expense' AND Category LIKE '%food%' 
        ORDER BY Date DESC;

        -- For summary analysis (when specifically asked for totals):
        SELECT Category, SUM(Amount) as Total 
        FROM df 
        WHERE Type = 'Expense' 
        GROUP BY Category;

        -- For time-based analysis:
        SELECT strftime('%Y-%m', Date) as Month, SUM(Amount) as Total 
        FROM df 
        WHERE Type = 'Expense' 
        GROUP BY Month 
        ORDER BY Month;

        Rules:
        1. ALWAYS use 'df' as the table name
        2. Start with SELECT
        3. No prefixes or explanations
        4. Return only the SQL query
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

            # Create an enhanced prompt for SQL query generation
            enhanced_prompt = f"""
You are a SQL expert working with financial transaction data. The data is stored in a table named 'df'.

User Question: "{query}"

Write a SQL query to analyze this data. Follow these guidelines:
1. For category analysis (e.g., "show food expenses", "analyze travel spending"):
   - Use: SELECT Date, Description, Amount, Category, Type FROM df WHERE Type = 'Expense' AND Category LIKE '%category%'
   - DO NOT use SUM() unless specifically asked for totals
   - Order by Date DESC

2. Only use aggregations (SUM, COUNT, AVG) when explicitly asked for:
   - "total spending in food" -> use SUM
   - "how many transactions" -> use COUNT
   - "average spending" -> use AVG

3. Default filters:
   - For spending analysis: WHERE Type = 'Expense'
   - For income analysis: WHERE Type = 'Income'

4. For monthly trends, use:
   strftime('%Y-%m', Date) as Month

5. For unclear requests:
   SELECT * FROM df ORDER BY Date DESC LIMIT 10

{self._get_schema()}

Important:
- Return ONLY the SQL query
- Do not include any explanations
- If the request is unclear, use the default SELECT query
- Make sure to always use 'df' as the table name
"""
            # Convert enhanced prompt to SQL and validate
            def clean_sql_query(raw_query: str) -> str:
                """Clean and validate SQL query"""
                # Extract query if it's wrapped in a message
                query = raw_query.message if hasattr(raw_query, 'message') else str(raw_query)
                query = query.strip()
                
                # Remove common prefixes
                prefixes = ['sql query:', 'query:', 'sql:', 'here\'s the sql query:', 'sql statement:']
                for prefix in prefixes:
                    if query.lower().startswith(prefix):
                        query = query[len(prefix):].strip()
                
                # Validate basic SQL structure
                if not query.lower().startswith('select'):
                    return "SELECT * FROM df ORDER BY Date DESC LIMIT 10"
                
                if 'from' not in query.lower():
                    return "SELECT * FROM df ORDER BY Date DESC LIMIT 10"
                
                return query

            # Get and clean SQL query
            model_output = get_sql_query(model, enhanced_prompt)
            sql_query = clean_sql_query(model_output)
            
            # Replace incompatible SQL syntax with SQLite compatible versions
            sql_query = sql_query.replace(' ILIKE ', ' LIKE ')  # SQLite doesn't support ILIKE
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
                    {"role": "system", "content": "You are a professional financial analyst. Provide only data-driven insights using bullet points. Focus on numbers, percentages, and key trends. No recommendations or tips - just facts and analysis."},
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
        Query: "{query}"

        Data Summary:
        - Total: {data_context['total_transactions']} transactions
        - Period: {data_context['date_range']}
        - Spending: ${data_context['total_spending']:.2f}
        - Income: ${data_context['total_income']:.2f}
        
        Details:
        {json.dumps(data_context['transactions'], indent=2)}

        Return only:
        - Key metrics and percentages
        - Notable trends
        - Significant changes in numbers
        No tips, recommendations, or suggestions.
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
