# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
This module is the set_max_queue_position_expired API handler.
It sets the MAX_QUEUE_POSITION_EXPIRED value and optionally increments the serving counter.
"""

import boto3
import os
import redis
import json
from botocore import config
from time import time
from boto3.dynamodb.conditions import Key
from counters import MAX_QUEUE_POSITION_EXPIRED, QUEUE_COUNTER, RESET_IN_PROGRESS, SERVING_COUNTER

SECRET_NAME_PREFIX = os.environ["STACK_NAME"]
SOLUTION_ID = os.environ['SOLUTION_ID']
EVENT_ID = os.environ["EVENT_ID"]
REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = os.environ["REDIS_PORT"]
QUEUE_POSITION_ENTRYTIME_TABLE = os.environ["QUEUE_POSITION_ENTRYTIME_TABLE"]
QUEUE_POSITION_EXPIRY_PERIOD = os.environ["QUEUE_POSITION_EXPIRY_PERIOD"]
SERVING_COUNTER_ISSUEDAT_TABLE = os.environ["SERVING_COUNTER_ISSUEDAT_TABLE"]
INCR_SVC_ON_QUEUE_POS_EXPIRY = os.environ["INCR_SVC_ON_QUEUE_POS_EXPIRY"]
EVENT_BUS_NAME = os.environ["EVENT_BUS_NAME"]

user_agent_extra = {"user_agent_extra": SOLUTION_ID}
user_config = config.Config(**user_agent_extra)
boto_session = boto3.session.Session()
region = boto_session.region_name
ddb_resource = boto3.resource('dynamodb', endpoint_url=f'https://dynamodb.{region}.amazonaws.com', config=user_config)
ddb_table_queue_position_entry_time = ddb_resource.Table(QUEUE_POSITION_ENTRYTIME_TABLE)
ddb_table_serving_counter_issued_at = ddb_resource.Table(SERVING_COUNTER_ISSUEDAT_TABLE)
secrets_client = boto3.client('secretsmanager', config=user_config, endpoint_url=f'https://secretsmanager.{region}.amazonaws.com')
response = secrets_client.get_secret_value(SecretId=f"{SECRET_NAME_PREFIX}/redis-auth")
redis_auth = response.get("SecretString")
rc = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, ssl=True, decode_responses=True, password=redis_auth)
events_client = boto3.client('events', endpoint_url=f'https://events.{region}.amazonaws.com', config=user_config)

def lambda_handler(event, _):
    """
    This function is the entry handler for Lambda.
    """
    print(event)
    if int(rc.get(RESET_IN_PROGRESS)) != 0:
        print('Reset in progress. Skipping execution')
        return

    current_time = int(time())
    max_queue_position_expired = int(rc.get(MAX_QUEUE_POSITION_EXPIRED))
    current_serving_counter_position = int(rc.get(SERVING_COUNTER))
    queue_counter = int(rc.get(QUEUE_COUNTER))
    print(f'Queue counter: {queue_counter}. Max position expired: {max_queue_position_expired}. Serving counter: {current_serving_counter_position}')

    # find items in the serving counter table that are greater than the max queue position expired
    response = ddb_table_serving_counter_issued_at.query(
        KeyConditionExpression=Key('event_id').eq(EVENT_ID) & Key('serving_counter').gt(max_queue_position_expired),
    )
    serving_counter_items = response['Items']

    if not serving_counter_items:
        print('No serving counter items eligible')
        return

    # set previous serving counter to max queue position expired
    previous_serving_counter_position = max_queue_position_expired

    for serving_counter_item in serving_counter_items:

        serving_counter_item_position = int(serving_counter_item['serving_counter'])
        serving_counter_item_issue_time = int(serving_counter_item['issue_time'])
        
        # query queue position table for corresponding serving counter item position
        response = ddb_table_queue_position_entry_time.query(
            KeyConditionExpression=Key('queue_position').eq(serving_counter_item_position),
            IndexName='QueuePositionIndex',
        )
        queue_position_items = response['Items']
        
        if not queue_position_items:
            print('No queue postions items eligible')
            break
        
        queue_item_entry_time = int(queue_position_items[0]['entry_time'])
        queue_time = max(queue_item_entry_time, serving_counter_item_issue_time)

        # if time in queue has not exceeded expiry period, we can stop checking
        if current_time - queue_time < int(QUEUE_POSITION_EXPIRY_PERIOD):
            break
                
        # set max queue position to serving counter item position
        if rc.set(MAX_QUEUE_POSITION_EXPIRED, serving_counter_item_position):
            max_queue_position_expired = serving_counter_item_position
            print(f'Max queue expiry position set to: {max_queue_position_expired}')
        else:
            print(f'Failed to set max queue position served: Current value: {max_queue_position_expired}')

        if INCR_SVC_ON_QUEUE_POS_EXPIRY == 'true':
            queue_positions_served = int(serving_counter_item['queue_positions_served'])
            incr_serving_counter(rc, queue_positions_served, serving_counter_item_position, previous_serving_counter_position)

        # set prevous serving counter position to item serving counter position for the loop
        previous_serving_counter_position = serving_counter_item_position


def incr_serving_counter(rc, queue_positions_served, serving_counter_item_position, previous_serving_counter_position):
    """
    Function to increment the serving counter based on queue postions served (indirectly expired positions)
    """
    # increment the serving counter by taking the difference of counter item entries and subtract positions served in that range
    # [(Current counter - Previous counter) - (Queue positions served in that range)]
    increment_by = (serving_counter_item_position - previous_serving_counter_position) - queue_positions_served
    
    # should never happen, addl guard
    if increment_by <= 0:
        print(f'Increment value calculated as {increment_by}, incrementing serving counter skipped')
        return

    cur_serving = int(rc.incrby(SERVING_COUNTER, int(increment_by)))
    item = {
        'event_id': EVENT_ID,
        'serving_counter': cur_serving,
        'issue_time': int(time()),
        'queue_positions_served': 0
    }
    ddb_table_serving_counter_issued_at.put_item(Item=item)
    print(f'Item: {item}')
    print(f'Serving counter incremented by {increment_by}. Current value: {cur_serving}')

    events_client.put_events(
        Entries=[
            {
                'Source': 'custom.waitingroom',
                'DetailType': 'automatic_serving_counter_incr',
                'Detail': json.dumps(
                    {
                        'previous_serving_counter_position': cur_serving - increment_by,
                        'increment_by': increment_by,
                        'current_serving_counter_position': cur_serving,
                    }
                ),
                'EventBusName': EVENT_BUS_NAME
            }
        ]
    )
