"""Trello board helpers and non-destructive one-card-per-unit synchronization."""
import os
import requests

TRELLO_SHEET_MAP = {'Assembly': 'Assembly', 'Post-Processing': 'Post'}
TRELLO_LIST_NAMES = ['Printing', 'Assembly', 'Post-Processing']


def _request(method, path, **params):
    auth = {'key': os.environ['TRELLO_API_KEY'], 'token': os.environ['TRELLO_API_TOKEN']}
    response = requests.request(method, f'https://api.trello.com/1/{path}', params={**auth, **params}, timeout=15)
    response.raise_for_status()
    return response.json()


def get_trello_boards():
    return _request('GET', 'members/me/boards')


def get_trello_board_by_name(board_name):
    for board in get_trello_boards():
        if board['name'] == board_name:
            board['inventory_lists'] = check_trello_lists(board['id'])
            return board
    return create_trello_board(board_name)


def check_trello_lists(board_id):
    existing = _request('GET', f'boards/{board_id}/lists')
    for name in TRELLO_LIST_NAMES:
        if not any(item['name'] == name for item in existing):
            existing.extend(create_trello_lists(board_id, [name]))
    return existing


def create_trello_board(board_name):
    board = _request('POST', 'boards/', name=board_name, defaultLists='false')
    board['inventory_lists'] = create_trello_lists(board['id'], TRELLO_LIST_NAMES)
    return board


def create_trello_lists(board_id, list_names):
    return [_request('POST', f'boards/{board_id}/lists', name=name) for name in list_names]


def get_trello_cards(list_id):
    return _request('GET', f'lists/{list_id}/cards')


def create_trello_card(list_id, card_name, card_desc=''):
    return _request('POST', 'cards', idList=list_id, name=card_name, desc=card_desc)


def delete_trello_card(card_id):
    return _request('DELETE', f'cards/{card_id}')


def update_trello_card(card_id, card_name=None, card_desc=None):
    changes = {}
    if card_name is not None:
        changes['name'] = card_name
    if card_desc is not None:
        changes['desc'] = card_desc
    return _request('PUT', f'cards/{card_id}', **changes)


def sync_inventory_to_trello(inventory, board, apply=False):
    """Plan/create missing unit cards. Never delete or modify existing cards.

    Existing Quantity: N cards are *legacy* aggregate cards and must be
    migrated separately. Printing is not derived from sheet counts.
    """
    lists = {item['name']: item for item in check_trello_lists(board['id'])
             if item['name'] in TRELLO_LIST_NAMES}
    plan = []
    for stage, column in TRELLO_SHEET_MAP.items():
        list_id = lists[stage]['id']
        cards = get_trello_cards(list_id)
        for item in inventory:
            name = item['Name']
            target = int(item.get(column) or 0)
            if target < 0:
                raise ValueError(f'Negative {column} count for {name}')
            matching = [c for c in cards if c['name'] == name]
            legacy = [c for c in matching if (c.get('desc') or '').strip().startswith('Quantity:')]
            if legacy:
                plan.append({'stage': stage, 'item': name, 'action': 'MIGRATE_LEGACY',
                             'legacy_card_ids': [c['id'] for c in legacy]})
                continue
            missing = target - len(matching)
            if missing > 0:
                plan.append({'stage': stage, 'item': name, 'action': 'CREATE', 'count': missing})
                if apply:
                    for _ in range(missing):
                        create_trello_card(list_id, name)
            elif missing < 0:
                plan.append({'stage': stage, 'item': name, 'action': 'EXCESS', 'count': -missing})
    return plan


def calculate_inventory_adjustments(from_stage, to_stage, quantity=1):
    adjustments = {'Post-Processing': 0, 'Assembly': 0}
    if from_stage in adjustments:
        adjustments[from_stage] -= quantity
    if to_stage in adjustments:
        adjustments[to_stage] += quantity
    return adjustments
