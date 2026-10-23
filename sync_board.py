"""Preview or apply Sheets -> Trello reconciliation. Does not delete cards."""
import argparse
from google_sheets import authenticate_google_sheets, get_inventory
from trello import get_trello_board_by_name, sync_inventory_to_trello


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('board_name')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    inventory = get_inventory(authenticate_google_sheets())
    board = get_trello_board_by_name(args.board_name)
    plan = sync_inventory_to_trello(inventory, board, apply=args.apply)
    for item in plan:
        print(item)
    print(f'{len(plan)} planned operations; ' + ('applied' if args.apply else 'DRY RUN (no cards modified; missing lists may be created)'))


if __name__ == '__main__':
    main()
