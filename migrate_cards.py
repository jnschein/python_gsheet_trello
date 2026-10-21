"""Preview legacy aggregate-card conversion; --apply creates unit cards and archives legacy cards.

Run only with webhook processing disabled, after backing up the Trello board.
Never adjusts Google Sheets quantities.
"""
import argparse
from collections import Counter
from google_sheets import authenticate_google_sheets, get_inventory
from trello import get_trello_board_by_name, get_trello_cards, create_trello_card, TRELLO_SHEET_MAP, TRELLO_LIST_NAMES, _request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('board_name')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    inventory = get_inventory(authenticate_google_sheets())
    by_name = {item['Name']: item for item in inventory}
    if len(by_name) != len(inventory):
        raise ValueError('Duplicate item names in Google Sheets; cannot migrate safely')
    board = get_trello_board_by_name(args.board_name)
    for stage in TRELLO_LIST_NAMES:
        list_id = next(lst['id'] for lst in board['inventory_lists'] if lst['name'] == stage)
        cards = get_trello_cards(list_id)
        legacy = [card for card in cards if (card.get('desc') or '').strip().startswith('Quantity:')]
        for card in legacy:
            name = card['name']
            if name not in by_name:
                print(f'SKIP unknown item {name!r} in {stage}')
                continue
            if stage == 'Printing':
                print(f'Printing placeholder {name!r}: archive only (no quantity in sheet for Printing)')
                if args.apply:
                    _request('PUT', f"cards/{card['id']}", closed='true')
                continue
            target = int(by_name[name].get(TRELLO_SHEET_MAP[stage]) or 0)
            # Count all other unit cards, including ones created during a previous interrupted migration.
            other_cards = [c for c in cards if c['name'] == name and c['id'] != card['id']
                           and not (c.get('desc') or '').strip().startswith('Quantity:')]
            needed = max(0, target - len(other_cards))
            print(f'{stage}: {name!r}: sheet={target}, existing units={len(other_cards)}, create={needed}, archive legacy={card["id"]}')
            if args.apply:
                for _ in range(needed):
                    new_card = create_trello_card(list_id, name)
                    cards.append(new_card)
                _request('PUT', f"cards/{card['id']}", closed='true')
    print('Applied changes.' if args.apply else 'DRY RUN ONLY: no Trello cards changed.')


if __name__ == '__main__':
    main()
