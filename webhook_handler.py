"""Trello -> Google Sheets inventory webhook. One card represents one unit."""
import base64
import hashlib
import hmac
import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

from google_sheets import authenticate_google_sheets, transfer_quantity, get_item_priority
from trello import set_card_priority

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
STAGES = frozenset({'Printing', 'Post-Processing', 'Assembly', 'Inventory'})


def _response(status, message):
    return {'statusCode': status, 'body': message}


def _verify_signature(event):
    """Verify Trello's X-Trello-Webhook signature over body + callback URL."""
    callback_url = os.environ.get('TRELLO_CALLBACK_URL')
    secret = os.environ.get('TRELLO_API_SECRET')
    if not callback_url or not secret:
        raise RuntimeError('Set TRELLO_CALLBACK_URL and TRELLO_API_SECRET before accepting POSTs')
    headers = {k.lower(): v for k, v in (event.get('headers') or {}).items()}
    supplied = headers.get('x-trello-webhook', '')
    raw_body = event.get('body') or ''
    body_bytes = base64.b64decode(raw_body) if event.get('isBase64Encoded') else raw_body.encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), body_bytes + callback_url.encode('utf-8'), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode('ascii')
    return hmac.compare_digest(supplied, expected), body_bytes


def lambda_handler(event, context):
    method = (event.get('requestContext', {}).get('http', {}).get('method')
              or event.get('httpMethod', '')).upper()
    if method == 'HEAD':
        return _response(200, '')
    if method != 'POST':
        return _response(405, 'Method Not Allowed')

    valid, body_bytes = _verify_signature(event)
    if not valid:
        return _response(401, 'Invalid Trello signature')

    payload = json.loads(body_bytes)
    action = payload.get('action') or {}
    data = action.get('data') or {}
    if action.get('type') != 'updateCard' or not all(k in data for k in ('card', 'listBefore', 'listAfter')):
        return _response(200, 'Ignored')

    from_stage = data['listBefore']['name']
    to_stage = data['listAfter']['name']
    if from_stage not in STAGES or to_stage not in STAGES or from_stage == to_stage:
        return _response(200, 'Ignored')

    item_name = data['card']['name']
    action_id = action['id']
    table_name = os.environ.get('TRELLO_ACTIONS_TABLE')
    if not table_name:
        raise RuntimeError('TRELLO_ACTIONS_TABLE must be configured before inventory updates')
    table = boto3.resource('dynamodb').Table(table_name)

    try:
        table.put_item(
            Item={'action_id': action_id, 'status': 'PROCESSING'},
            ConditionExpression='attribute_not_exists(action_id)'
        )
    except ClientError as exc:
        if exc.response['Error']['Code'] != 'ConditionalCheckFailedException':
            raise
        existing = table.get_item(Key={'action_id': action_id}, ConsistentRead=True).get('Item')
        if existing and existing.get('status') == 'DONE':
            logger.info('Skipping already processed action %s', action_id)
            return _response(200, 'Already processed')
        # Never acknowledge an uncertain in-progress action as completed.
        return _response(503, 'Action processing; retry later')

    try:
        creds = authenticate_google_sheets()
        transfer_quantity(creds, item_name, from_stage, to_stage, 1)
        table.update_item(
            Key={'action_id': action_id},
            UpdateExpression='SET #status = :done',
            ExpressionAttributeNames={'#status': 'status'},
            ExpressionAttributeValues={':done': 'DONE'}
        )
    except Exception:
        # Leave PROCESSING for investigation. Removing it could double-apply a
        # successfully written sheet update if the failure happened afterward.
        logger.exception('Action %s needs investigation; do not replay without reconciliation', action_id)
        raise

    try:
        priority = get_item_priority(creds, item_name)
        set_card_priority(data['card']['id'], priority)
    except Exception:
        logger.exception('Inventory updated but card priority cover could not be refreshed')

    logger.info('Moved one %s: %s -> %s (action %s)', item_name, from_stage, to_stage, action_id)
    return _response(200, 'OK')
