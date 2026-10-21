# Trello inventory: one card per unit

Each card represents **one physical item**. Card descriptions no longer carry quantities. A movement between Printing, Post-Processing, and Assembly changes sheet quantities by exactly one. Printing is untracked in Google Sheets; Assembly and Post map to their sheet columns.

## Before deploying

1. **Back up the Trello board and the spreadsheet.** Pause moving cards during migration.
2. Create DynamoDB table (same AWS region as Lambda), with partition key `action_id` of type **String**, on-demand billing. Set Lambda environment variable `TRELLO_ACTIONS_TABLE` to its name. Add Lambda execution-role permissions `dynamodb:PutItem`, `dynamodb:GetItem`, and `dynamodb:UpdateItem` on this table.
3. Set `TRELLO_CALLBACK_URL` to the **exact registered webhook callback URL**, and `TRELLO_API_SECRET` to your Trello application's API secret (not the API key or API token). Lambda must have these environment variables. The POST handler verifies `X-Trello-Webhook` HMAC signature. Keep secrets out of source control.
4. Set Lambda **reserved concurrency to 1** to avoid simultaneous read-modify-write operations against Sheets. This does not make updates atomic against other sheet editors or external scripts.
5. Deploy `webhook_handler.py`, `google_sheets.py`, `trello.py` and requirements using your existing GitHub Actions workflow. Restore handler `webhook_handler.lambda_handler`.
6. Test with one card, check CloudWatch and sheet quantities. For testing, do not replay the same action ID and expect another adjustment.

## Convert existing cards

Run locally (where your Google OAuth `token.json` is available):

```
python migrate_cards.py "YOUR BOARD NAME"
python migrate_cards.py "YOUR BOARD NAME" --apply
```

The first command previews changes. The second creates one card per unit according to current **Assembly** and **Post** sheet quantities, and archives aggregate `Quantity: N` cards. **It never changes the spreadsheet**. Existing Printing `Quantity: 0` placeholders are archived without replacement, because there is no authoritative Printing count in the provided code. Create Printing cards manually, one per physical item/job to be printed, once you have decided how many should exist. Ensure sheet counts accurately reflect physical units before migration. If you already moved some cards under the new system, reconcile the sheet before running this migration.

`migrate_cards.py` is a **new file**. It is not needed in the Lambda deployment. Never run migration while card moves are being processed. Review dry-run output and take a board backup before applying. If migration is interrupted, re-run dry-run and verify counts; multiple legacy cards with the same name may need manual reconciliation.

## Ongoing sync

`sync_inventory_to_trello(inventory, board)` now **only previews** missing or excess unit cards and reports legacy cards. `sync_inventory_to_trello(inventory, board, apply=True)` creates missing Assembly/Post unit cards only; it never deletes cards. Do not run this automatically after every webhook, because it could conflict with in-flight changes. Printing cards are not created by sync.

## Reliability limits

- DynamoDB conditionally claims an action ID. Successfully completed actions are marked `DONE` and duplicates are ignored.
- If Sheets succeeds but DynamoDB's final status update fails, the action remains `PROCESSING` and needs manual reconciliation. This is intentional to prevent silently applying the same quantity twice. Investigate CloudWatch and the sheet before changing/removing a stuck record.
- A failed Sheets update also leaves the action `PROCESSING`; investigate and reconcile manually. The webhook responds with an error so the failure is visible.
- Trello webhook signature verification requires the exact registered callback URL. HEAD verification is still supported.
- Sheet read/modify/write is not transactional. Reserved concurrency of 1 reduces races among Lambda invocations but not against manual edits or other writers.
- Existing cards created before migration must be reconciled with sheet counts. Do not deploy the new webhook and continue moving aggregate cards.
