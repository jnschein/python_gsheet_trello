# Trello inventory v2

## Behavior
- **Printing:** exactly one desired card for each sheet item with `Total == 0`; no card when `Total != 0`. This is a *placeholder*, not a physical unit count.
- **Assembly**, **Post-Processing**, **Inventory:** one card per unit based on sheet columns `Assembly`, `Post`, and `Inventory`.
- Card movement between any two lists adjusts the tracked quantities by one; Printing has no stored count.
- High / Medium / Low priority: Trello full-card covers in red / yellow / blue. Trello supplies the available shades, not exact custom pastel colors.

## Deploy
Replace `trello.py`, `google_sheets.py`, and `webhook_handler.py` in your repository. Keep `requirements.txt`. Your GitHub Action must package `trello.py` with Lambda because the webhook now imports it. The existing DynamoDB table, webhook signature settings, and IAM permissions remain necessary. Restore handler `webhook_handler.lambda_handler`.

## Synchronize the board
Run from a local environment that already has your Google OAuth credentials and `TRELLO_API_KEY` / `TRELLO_API_TOKEN`:

```bash
python sync_board.py "YOUR BOARD NAME"
python sync_board.py "YOUR BOARD NAME" --apply
```

The preview can create a missing Trello list, including Inventory, because board lookup ensures required lists exist. `--apply` creates missing cards and updates card colors. **It does not delete excess cards**, including Printing cards when Total becomes nonzero. Such cases are reported as `EXCESS` for manual reconciliation. A new Printing placeholder is created when a subsequent synchronization sees Total zero and no Printing card.

If old `Quantity: N` cards still exist, first preview and run `migrate_cards.py` with `--apply` only after backing up the board and disabling webhook processing. The migration archives legacy cards, creates individual cards, and never changes the spreadsheet.

**Do not run the sync while webhook movements are in progress.** It uses sheet counts as source of truth; webhook updates must finish before syncing.

## Important constraints
- The Printing list is a work queue based on `Total == 0`, **not** a physical quantity. Moving a Printing placeholder into a tracked list adds one unit and removes the placeholder from Printing. A later sync can recreate the placeholder if Total remains zero.
- Sheet `Total` must reflect your intended zero/positive rule; if it is a formula, ensure Google Sheets recalculates it after inventory updates.
- Trello colors use the native `red`, `yellow`, and `blue` palette, with full-card covers.
- Existing DynamoDB idempotency behavior is preserved. A failed sheet update can leave an action marked `PROCESSING`, requiring manual reconciliation.
- Lambda's concurrency should be limited to 1 to reduce simultaneous sheet read/modify/write races; DynamoDB action-ID deduplication does not serialize different actions.
- This code has been syntax-checked and locally tested with mocks, not against your live Trello board or Google Sheet.
