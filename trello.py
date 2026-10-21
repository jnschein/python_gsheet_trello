import os
import requests

api_key = os.environ.get("TRELLO_API_KEY")
api_token = os.environ.get("TRELLO_API_TOKEN")
TRELLO_SHEET_MAP = { #Trello List Name: Google Sheet Column Name
    "Printing": "Total",
    "Assembly": "Assembly",
    "Post-Processing": "Post"
}
TRELLO_LIST_NAMES = list(TRELLO_SHEET_MAP.keys())

def get_trello_boards():

    url = "https://api.trello.com/1/members/me/boards"
    query = {
        'key': api_key,
        'token': api_token
    }

    response = requests.get(url, params=query, timeout=15)
    response.raise_for_status()
    return response.json()

def get_trello_board_by_name(board_name):

    boards = get_trello_boards()
    for board in boards:
        if board['name'] == board_name:
            board['inventory_lists'] = check_trello_lists(board['id'])
            return board
    new_board = create_trello_board(board_name)
    return new_board

def check_trello_lists(board_id): 

    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    query = {
        'key': api_key,
        'token': api_token
    }

    response = requests.get(url, params=query, timeout=15)
    response.raise_for_status()
    existing_lists = response.json()
    for list_name in TRELLO_LIST_NAMES:
        if not any(lst['name'] == list_name for lst in existing_lists):
            existing_lists.extend(create_trello_lists(board_id, [list_name]))
    return existing_lists


def create_trello_board(board_name):

    url = "https://api.trello.com/1/boards/"
    query = {
        'key': api_key,
        'token': api_token,
        'name': board_name,
        'defaultLists': 'false'
    }

    response = requests.post(url, params=query, timeout=15)

    response.raise_for_status()

    board = response.json()
    board['inventory_lists'] = create_trello_lists(board['id'], TRELLO_LIST_NAMES)
    return board

def create_trello_lists(board_id, list_names):
    url = f"https://api.trello.com/1/boards/{board_id}/lists"
    query = {
        'key': api_key,
        'token': api_token
    }

    created_lists = []
    for list_name in list_names:
        query['name'] = list_name
        response = requests.post(url, params=query, timeout=15)
        response.raise_for_status()
        created_lists.append(response.json())
    return created_lists

def get_trello_cards(list_id):
    url = f"https://api.trello.com/1/lists/{list_id}/cards"
    query = {
        'key': api_key,
        'token': api_token
    }

    response = requests.get(url, params=query, timeout=15)
    response.raise_for_status()
    return response.json()

def create_trello_card(list_id, card_name, card_desc):
    url = f"https://api.trello.com/1/cards"
    query = {
        'key': api_key,
        'token': api_token,
        'idList': list_id,
        'name': card_name,
        'desc': card_desc
    }

    response = requests.post(url, params=query, timeout=15)
    response.raise_for_status()
    return response.json()

def delete_trello_card(card_id):
    url = f"https://api.trello.com/1/cards/{card_id}"
    query = {
        'key': api_key,
        'token': api_token
    }

    response = requests.delete(url, params=query, timeout=15)
    response.raise_for_status()
    return response.json()

def update_trello_card(card_id, card_name=None, card_desc=None):
    url = f"https://api.trello.com/1/cards/{card_id}"
    query = {
        'key': api_key,
        'token': api_token
    }
    if card_name:
        query['name'] = card_name
    if card_desc:
        query['desc'] = card_desc

    response = requests.put(url, params=query, timeout=15)
    response.raise_for_status()
    return response.json()

def sync_inventory_to_trello(inventory, board):
    lists = check_trello_lists(board['id'])

    for list in lists:
        cards = get_trello_cards(list['id'])
        for item in inventory:
            quantity = item.get(TRELLO_SHEET_MAP.get(list['name'], ''), 0)
            existing_card = next((card for card in cards if card['name'] == item['Name']), None)

            if list['name'] == "Printing":
                if quantity == 0 and not existing_card:
                    cards.append(create_trello_card(list['id'], item['Name'], f"Quantity: {quantity}"))
                elif quantity > 0 and existing_card:
                    delete_trello_card(existing_card['id'])
                    cards.remove(existing_card)
            else:
                if quantity > 0:
                    if existing_card and existing_card['desc'] != f"Quantity: {quantity}":
                        updated_card = update_trello_card(existing_card['id'], card_desc=f"Quantity: {quantity}")
                        existing_card.update(updated_card)
                    elif not existing_card:
                        cards.append(create_trello_card(list['id'], item['Name'], f"Quantity: {quantity}"))
                elif quantity == 0 and existing_card:
                    delete_trello_card(existing_card['id'])
                    cards.remove(existing_card)

def calculate_inventory_adjustments(from_stage, to_stage, quantity):
    adjustments = {
        "Post-Processing": 0,
        "Assembly": 0
    }

    if from_stage in adjustments:
        adjustments[from_stage] -= quantity

    if to_stage in adjustments:
        adjustments[to_stage] += quantity

    return adjustments