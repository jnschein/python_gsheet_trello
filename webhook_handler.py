import json
import requests
import os
from google_sheets import authenticate_google_sheets, transfer_quantity
from googleapiclient.discovery import build

def test_google_auth(event, context):
    creds = authenticate_google_sheets()

    service = build("sheets", "v4", credentials=creds)

    result = service.spreadsheets().values().get(
        spreadsheetId="17IKUlHOxm4wzk9oOi1hy56zYPxiM9f6iMtk3XuhTp6k",
        range="A1:D5"
    ).execute()

    print("Spreadsheet data:", result.get("values", []))

    return {
        "statusCode": 200,
        "body": "Google Sheets read successful"
    }

def get_trello_card(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}"

    params = {
        "key": os.environ.get("TRELLO_API_KEY"),
        "token": os.environ.get("TRELLO_API_TOKEN")
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()
    
def lambda_handler(event, context):
    method = event["requestContext"]["http"]["method"]

    print("HTTP Method:", method)
    
    if method == "HEAD":
        return {"statusCode": 200, "body": ""}

    if method == "POST":
        payload = json.loads(event.get("body") or "{}")
        action = payload.get("action", {})
        data = action.get("data", {})

        if action.get("type") == "updateCard" and "listBefore" in data and "listAfter" in data:
            card_id = data["card"]["id"]
            item_name = data["card"]["name"]
            from_stage = data["listBefore"]["name"]
            to_stage = data["listAfter"]["name"]
            action_id = action["id"]
            card = get_trello_card(card_id)
            description = card["desc"]
            quantity = int(description.split(":")[1].strip())
            
            print(f"Card moved: {item_name}, {from_stage} -> {to_stage}")
            if from_stage in ("Printing", "Post-Processing", "Assembly") \
                    and to_stage in ("Printing", "Post-Processing", "Assembly"):

                creds = authenticate_google_sheets()

                transfer_quantity(
                    creds,
                    item_name,
                    from_stage,
                    to_stage,
                    quantity
                )

                print(f"Transferred {quantity} of '{item_name}' from {from_stage} to {to_stage}")
        return {"statusCode": 200, "body": "OK"}

    return {"statusCode": 405, "body": "Method Not Allowed"}