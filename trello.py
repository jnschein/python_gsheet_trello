"""Trello helpers and safe spreadsheet-to-board reconciliation.

Printing: exactly one desired card per item with Total == 0.
Assembly, Post-Processing, Inventory: one card per physical unit.
Existing excess cards are reported, never deleted automatically.
"""
import os
from collections import Counter
import requests

TRELLO_SHEET_MAP = {'Assembly': 'Assembly', 'Post-Processing': 'Post', 'Inventory': 'Inventory'}
TRELLO_LIST_NAMES = ['Printing', 'Assembly', 'Post-Processing', 'Inventory']
PRIORITY_COLORS = {'high': 'red', 'medium': 'yellow', 'low': 'blue'}


def _request(method, path, **params):
    auth = {'key': os.environ['TRELLO_API_KEY'], 'token': os.environ['TRELLO_API_TOKEN']}
    response = requests.request(method, f'https://api.trello.com/1/{path}', params={**auth, **params}, timeout=15)
    response.raise_for_status()
    return response.json() if response.content else {}


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


def set_card_priority(card_id, priority, current_cover=None):

    color = PRIORITY_COLORS.get(str(priority or '').strip().lower())
    if not color:
        return None

    # Remove any existing priority-color labels.
    card = _request('GET', f'cards/{card_id}', fields='id', labels='all')

    for label in card.get('labels', []):
        if label.get('color') in PRIORITY_COLORS.values():
            _request('DELETE', f'cards/{card_id}/idLabels/{label["id"]}')

    # Add the appropriate color label.
    _request('PUT', f'cards/{card_id}/cover', color='none')
    return _request('POST', f'cards/{card_id}/labels', color=color, name='')


def create_trello_card(list_id, card_name, card_desc='', priority=None):
    card = _request('POST', 'cards', idList=list_id, name=card_name, desc=card_desc)
    if priority:
        set_card_priority(card['id'], priority)
    return card


def delete_trello_card(card_id):
    return _request('DELETE', f'cards/{card_id}')


def update_trello_card(card_id, card_name=None, card_desc=None):
    changes = {}
    if card_name is not None:
        changes['name'] = card_name
    if card_desc is not None:
        changes['desc'] = card_desc
    return _request('PUT', f'cards/{card_id}', **changes) if changes else None


def _legacy(card):
    return (card.get('desc') or '').strip().startswith('Quantity:')


def sync_inventory_to_trello(inventory, board, apply=False):
    """Reconcile missing cards and priority colors; never delete excess cards.

    Defaults to preview. Running --apply creates missing cards and updates covers.
    Legacy aggregate cards are reported for separate migration.
    """
    by_name = {item['Name']: item for item in inventory}
    if len(by_name) != len(inventory):
        raise ValueError('Duplicate item names in Google Sheets')
    lists = {entry['name']: entry for entry in check_trello_lists(board['id'])
             if entry['name'] in TRELLO_LIST_NAMES}
    plan = []
    for stage in TRELLO_LIST_NAMES:
        list_id = lists[stage]['id']
        cards = get_trello_cards(list_id)
        grouped = {}
        for card in cards:
            grouped.setdefault(card['name'], []).append(card)
        for item in inventory:
            name = item['Name']
            target = (1 if int(item.get('Total') or 0) == 0 else 0) if stage == 'Printing' else int(item.get(TRELLO_SHEET_MAP[stage]) or 0)
            if target < 0:
                raise ValueError(f'Negative quantity for {name} in {stage}')
            matching = grouped.get(name, [])
            legacy = [c for c in matching if _legacy(c)]
            if legacy:
                plan.append({'stage': stage, 'item': name, 'action': 'MIGRATE_LEGACY', 'ids': [c['id'] for c in legacy]})
                continue
            delta = target - len(matching)
            if delta > 0:
                plan.append({'stage': stage, 'item': name, 'action': 'CREATE', 'count': delta})
                if apply:
                    for _ in range(delta):
                        card = create_trello_card(list_id, name, priority=item.get('Priority'))
                        matching.append(card)
            elif delta < 0:
                plan.append({'stage': stage, 'item': name, 'action': 'EXCESS', 'count': -delta})
            color = PRIORITY_COLORS.get(str(item.get('Priority') or '').strip().lower())
            if color:
                for card in matching:
                    if not any(label.get('color') == color for label in card.get('labels', [])):
                        plan.append({'stage': stage, 'item': name, 'action': 'COLOR', 'card_id': card['id'], 'color': color})
                        if apply:
                            set_card_priority(card['id'], item['Priority'], cover)
        for name, unknown_cards in grouped.items():
            if name not in by_name:
                plan.append({'stage': stage, 'item': name, 'action': 'UNKNOWN', 'count': len(unknown_cards)})
    return plan


def calculate_inventory_adjustments(from_stage, to_stage, quantity=1):
    adjustments = {'Post-Processing': 0, 'Assembly': 0, 'Inventory': 0}
    if from_stage in adjustments:
        adjustments[from_stage] -= quantity
    if to_stage in adjustments:
        adjustments[to_stage] += quantity
    return adjustments
