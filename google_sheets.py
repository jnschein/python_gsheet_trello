from google_auth_oauthlib.flow import InstalledAppFlow 
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
SPREADSHEET_ID = '17IKUlHOxm4wzk9oOi1hy56zYPxiM9f6iMtk3XuhTp6k'
SHEET_NAME = 'Items'
NUMERIC_COLUMNS = ['Assembly', 'Post', 'Inventory', 'Total']


def authenticate_google_sheets():
    token_file_exists = os.path.exists('token.json')

    if token_file_exists:
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                './credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        
    return creds

def find_header_row(creds, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME):
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
        return None

    for row in values:
        if row and 'Priority' in row:
            return row

    return None

def get_inventory(creds, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME):
    found_header = False
    header_row = find_header_row(creds, spreadsheet_id, sheet_name)
    if header_row is None:
        raise ValueError("Header row not found in the sheet.")
    else:
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
        values = result.get('values', [])

        if not values:
            print('No data found.')
            return []

        returned_items = []
        for row in values:
            if row and row == header_row:

                found_header = True
                continue

            if found_header and row: 
                item = {}
                for i, header in enumerate(header_row):
                    if header:
                        if i < len(row):
                            if(header in NUMERIC_COLUMNS):
                                try:
                                    item[header] = int(row[i])
                                except ValueError as error:
                                    if row[i] == '':
                                        item[header] = 0
                                    else:
                                        raise ValueError(f"Invalid value for {header}: {row[i]}") from error
                            else:
                                item[header] = row[i]
                        else:
                            if(header in NUMERIC_COLUMNS):
                                item[header] = 0
                            else:
                                item[header] = None
                returned_items.append(item)

        return returned_items

def find_row_by_name(creds, name, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME):
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_name).execute()
    values = result.get('values', [])

    if not values:
        print('No data found.')
        return None

    for row_index, row in enumerate(values):

        if row and any(cell.strip() == name for cell in row):
            return row_index + 1  # Return the 1-based index of the row

    return None


def update_quantity(creds, data_list, spreadsheet_id=SPREADSHEET_ID, sheet_name=SHEET_NAME):

    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()

    body = {
        'valueInputOption': 'RAW',
        'data': data_list
    }
    result = sheet.values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body=body).execute()
    return result   

def transfer_quantity(creds, item_name, from_stage, to_stage, quantity):
    data_list = []
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValueError("Transfer quantity must be a positive integer.")
    
    header_row = find_header_row(creds)
    if header_row is None:
        raise ValueError("Header row not found in the sheet.")
    
    row = find_row_by_name(creds, item_name)
    if row is None: 
        raise ValueError(f"Item '{item_name}' not found in the sheet.")

    if from_stage == "Post-Processing":
        from_stage = "Post"
    if to_stage == "Post-Processing":
        to_stage = "Post"

    if from_stage == to_stage:
        raise ValueError("Source and destination stages must be different.")

    from_col = next((chr(i + 65) for i, header in enumerate(header_row) if header == from_stage), None)
    to_col = next((chr(i + 65) for i, header in enumerate(header_row) if header == to_stage), None)

    if from_col is None or to_col is None:
        raise ValueError(f"One or both columns '{from_stage}' and '{to_stage}' not found.")

    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()

    # Get current quantities
    from_range_name = f"{SHEET_NAME}!{from_col}{row}"
    to_range_name = f"{SHEET_NAME}!{to_col}{row}"

    from_result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=from_range_name).execute()
    to_result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=to_range_name).execute()

    current_from_quantity = int(from_result.get('values', [[0]])[0][0]) if from_result.get('values') else 0
    current_to_quantity = int(to_result.get('values', [[0]])[0][0]) if to_result.get('values') else 0

    # Update quantities
    if(current_from_quantity - quantity >= 0):
        new_from_quantity = current_from_quantity - quantity
    else:
        raise ValueError(f"Not enough quantity in '{from_stage}' to transfer. Current: {current_from_quantity}, Requested: {quantity}")
    new_to_quantity = current_to_quantity + quantity

    data_list.append({
        'range': from_range_name,
        'values': [[new_from_quantity]]
    })
    if to_stage != "Printing":  # Only update the "to" stage if it's not "Printing"`
        data_list.append({
            'range': to_range_name,
            'values': [[new_to_quantity]]
        })

    return update_quantity(creds, data_list)
