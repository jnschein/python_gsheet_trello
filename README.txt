Replace google_sheets.py and webhook_handler.py with these versions, then deploy Lambda as usual.

Moves into Sold decrement the source stage (Assembly, Post-Processing, Inventory).
Moves out of Sold increment the destination stage.
Printing and Sold have no quantity columns; moving Printing -> Sold or Sold -> Printing leaves the sheet unchanged.
Moves into Sold keep the card in Sold. No other files or environment variables need changing.

Existing webhook signature checks and DynamoDB action deduplication remain unchanged.
Caution: moving an item directly from Printing to Sold records no sale quantity because Printing is a zero-total placeholder, not a tracked unit.
