import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from google.oauth2.service_account import Credentials
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Utility Functions
def initialize_gspread_client(credentials_path='credentials/pdl-one-55f7829d5dd4.json'):
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
    client = gspread.authorize(creds)
    return client

def get_or_create_worksheet(client, spreadsheet_id, worksheet_name):
    try:
        sheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_name)
        logger.info(f"Accessed worksheet: {worksheet_name}")
    except gspread.WorksheetNotFound:
        sheet = client.open_by_key(spreadsheet_id).add_worksheet(title=worksheet_name, rows="100", cols="20")
        logger.warning(f"Worksheet not found. Created new worksheet: {worksheet_name}")
    return sheet

def load_data_from_sheet(client, spreadsheet_id, worksheet_name):
    sheet = get_or_create_worksheet(client, spreadsheet_id, worksheet_name)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    return df

def clear_and_update_sheet(client, spreadsheet_id, worksheet_name, df):
    sheet = get_or_create_worksheet(client, spreadsheet_id, worksheet_name)
    sheet.clear()
    set_with_dataframe(sheet, df)

def update_sheet(client, spreadsheet_id, worksheet_name, df):
    sheet = get_or_create_worksheet(client, spreadsheet_id, worksheet_name)
    set_with_dataframe(sheet, df)

def format_keyword_planner_df(df):
    df['Avg. Monthly Searches'] = df['Avg. Monthly Searches'].apply(lambda x: f"{x:,}")
    df['Low Bid'] = df['Low Bid'].apply(lambda x: f"{x:.2f}" if x != 0 else "0.00")
    df['High Bid'] = df['High Bid'].apply(lambda x: f"{x:.2f}" if x != 0 else "0.00")
    df['Bid Spread'] = df['Bid Spread'].apply(lambda x: f"{x:.2f}" if x != 0 else "0.00")
    df['Competition Index'] = df['Competition Index'].apply(lambda x: f"{x:,}")
    df['Trend Last 3 Months'] = df['Trend Last 3 Months'].apply(lambda x: f"{x:.2f}" if x != 0 else "0.00")
    df['Trend Last 6 Months'] = df['Trend Last 6 Months'].apply(lambda x: f"{x:.2f}" if x != 0 else "0.00")
    return df