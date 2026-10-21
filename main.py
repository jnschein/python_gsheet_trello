import os

import google_sheets
import trello
import requests

google_creds = google_sheets.authenticate_google_sheets()
inventory = google_sheets.get_inventory(google_creds)

board = trello.get_trello_board_by_name("FilaFiber Inventory")
trello.sync_inventory_to_trello(inventory, board)

#google_sheets.transfer_quantity(google_creds, "Nat", "Inventory", "Post-Processing", -3)

print(inventory)

def register_trello_webhook(board_id="6ad782b3a934e24919f35602", callback_url="https://vu1ahziyvi.execute-api.us-east-1.amazonaws.com/initial_stage/trello-webhook"):
    api_key = os.environ.get("TRELLO_API_KEY")
    api_token = os.environ.get("TRELLO_API_TOKEN")

    url = f"https://api.trello.com/1/tokens/{api_token}/webhooks"

    params = {
        "key": api_key,
        "callbackURL": callback_url,
        "idModel": board_id,
        "description": "Inventory synchronization"
    }

    response = requests.post(url, params=params, timeout=15)
    response.raise_for_status()
    return response.json()

#webhook = register_trello_webhook()

#print(webhook)