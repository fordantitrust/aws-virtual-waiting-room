# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""
This module is the used to reset the counters and DynamoDB table used by the core API.
"""

import redis
import json
import os
import boto3
from botocore import config
from counters import QUEUE_COUNTER, SERVING_COUNTER, TOKEN_COUNTER, ABANDONED_SESSION_COUNTER, COMPLETED_SESSION_COUNTER, MAX_QUEUE_POSITION_EXPIRED, RESET_IN_PROGRESS
from vwr.common.sanitize import deep_clean

TOKEN_TABLE = os.environ["TOKEN_TABLE"]
EVENT_ID = os.environ["EVENT_ID"]
REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = os.environ["REDIS_PORT"]
SOLUTION_ID = os.environ['SOLUTION_ID']
SECRET_NAME_PREFIX = os.environ["STACK_NAME"]
QUEUE_POSITION_ENTRYTIME_TABLE = os.environ["QUEUE_POSITION_ENTRYTIME_TABLE"]
SERVING_COUNTER_ISSUEDAT_TABLE = os.environ["SERVING_COUNTER_ISSUEDAT_TABLE"]

user_agent_extra = {"user_agent_extra": SOLUTION_ID}
user_config = config.Config(**user_agent_extra)
boto_session = boto3.session.Session()
region = boto_session.region_name
ddb_client = boto3.client('dynamodb', endpoint_url=f"https://dynamodb.{region}.amazonaws.com", config=user_config)
secrets_client = boto3.client('secretsmanager', config=user_config, endpoint_url=f"https://secretsmanager.{region}.amazonaws.com")
response = secrets_client.get_secret_value(SecretId=f"{SECRET_NAME_PREFIX}/redis-auth")
redis_auth = response.get("SecretString")
rc = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, ssl=True, decode_responses=True, password=redis_auth)

def lambda_handler(event, _):
    """
    This function is the entry handler for Lambda.
    """

    print(event)
    client_event_id = deep_clean(event['event_id'])
    response = {}
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
    }

    if EVENT_ID == client_event_id:
        rc.getset(RESET_IN_PROGRESS, 1)
        print('Reset in progress')

        # reset counters
        rc.getset(SERVING_COUNTER, 0)
        rc.getset(QUEUE_COUNTER, 0)
        rc.getset(TOKEN_COUNTER, 0)
        rc.getset(COMPLETED_SESSION_COUNTER, 0)
        rc.getset(ABANDONED_SESSION_COUNTER, 0)
        rc.getset(MAX_QUEUE_POSITION_EXPIRED, 0)
        print("Counters reset")

        try:                       
            response = ddb_client.delete_table(TableName=TOKEN_TABLE)
            waiter = ddb_client.get_waiter('table_not_exists')
            # wait for table to get deleted
            waiter.wait(TableName=TOKEN_TABLE)
            print("Token table deleted")
            # recreate table
            create_token_table()
            waiter = ddb_client.get_waiter('table_exists')
            # wait for table to get created
            waiter.wait(TableName=TOKEN_TABLE)
            print("Token table recreated")
            # enable PITR
            ddb_client.update_continuous_backups(
                TableName=TOKEN_TABLE,
                PointInTimeRecoverySpecification={
                    'PointInTimeRecoveryEnabled': True
                }
            )

            response = ddb_client.delete_table(TableName=QUEUE_POSITION_ENTRYTIME_TABLE)
            waiter = ddb_client.get_waiter('table_not_exists')
            # wait for table to get deleted
            waiter.wait(TableName=QUEUE_POSITION_ENTRYTIME_TABLE)
            print("QueuePositionEntryTimeTable table deleted")
            # recreate table
            create_queueposition_issuedat_table()
            waiter = ddb_client.get_waiter('table_exists')
            # wait for table to get created
            waiter.wait(TableName=QUEUE_POSITION_ENTRYTIME_TABLE)
            print("QueuePositionEntryTimeTable recreated")
            # enable PITR
            ddb_client.update_continuous_backups(
                TableName=QUEUE_POSITION_ENTRYTIME_TABLE,
                PointInTimeRecoverySpecification={
                    'PointInTimeRecoveryEnabled': True
                }
            )

            response = ddb_client.delete_table(TableName=SERVING_COUNTER_ISSUEDAT_TABLE)
            waiter = ddb_client.get_waiter('table_not_exists')
            # wait for table to get deleted
            waiter.wait(TableName=SERVING_COUNTER_ISSUEDAT_TABLE)
            print("ServingCounterIssuedAt table deleted")
            # recreate table
            create_servingcounter_issuedat_table()
            waiter = ddb_client.get_waiter('table_exists')
            # wait for table to get created
            waiter.wait(TableName=SERVING_COUNTER_ISSUEDAT_TABLE)
            print("ServingCounterIssuedAt recreated")
            # enable PITR
            ddb_client.update_continuous_backups(
                TableName=SERVING_COUNTER_ISSUEDAT_TABLE,
                PointInTimeRecoverySpecification={
                    'PointInTimeRecoveryEnabled': True
                }
            )
            print("DynamoDB tables recreated")
            
            rc.set(RESET_IN_PROGRESS, 0)
            print('Reset completed')
            
            response = {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({ "message": "Reset completed" })
            }
        except Exception as other_exception:
            print(other_exception)
            raise other_exception
    else:
        response = {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Invalid event ID"})
        }
    print(response)

    return response


def create_token_table():
    """
    Create TOKEN_TABLE
    """
    ddb_client.create_table(
        TableName= TOKEN_TABLE,
        BillingMode = "PAY_PER_REQUEST",
        AttributeDefinitions = [
            {
                "AttributeName": "request_id",
                "AttributeType": "S"
            },
            {
                "AttributeName": "expires",
                "AttributeType": "N"
            },
            {
                "AttributeName": "event_id",
                "AttributeType": "S"
            }
        ],
        KeySchema = [
            {
                "AttributeName": "request_id",
                "KeyType": "HASH"
            }
        ],
        GlobalSecondaryIndexes = [
            {
                "IndexName": "EventExpiresIndex",
                "KeySchema": [
                    {
                        "AttributeName": "event_id",
                        "KeyType": "HASH"
                    },
                    {
                        "AttributeName": "expires",
                        "KeyType": "RANGE"
                    }
                ],
                "Projection": {
                    "ProjectionType": "ALL"
                }
            }
        ],
        SSESpecification = {
            "Enabled": True
        }
    )


def create_queueposition_issuedat_table():
    """
    Create QUEUE_POSITION_ENTRYTIME_TABLE
    """
    ddb_client.create_table(
        TableName = QUEUE_POSITION_ENTRYTIME_TABLE,
        BillingMode = "PAY_PER_REQUEST",
        AttributeDefinitions = [
            {
                "AttributeName": "queue_position",
                "AttributeType": "N"
            },
            {
                "AttributeName": "request_id",
                "AttributeType": "S"
            }
        ],
        KeySchema = [
            {
                "AttributeName": "request_id",
                "KeyType": "HASH"
            }
        ],
        GlobalSecondaryIndexes = [
            {
                "IndexName": "QueuePositionIndex",
                "KeySchema": [
                    {
                        "AttributeName": "queue_position",
                        "KeyType": "HASH"
                    }
                ],
                "Projection": {
                    "ProjectionType": "ALL"
                }
            }
        ],
        SSESpecification = {
            "Enabled": True
        }
    )


def create_servingcounter_issuedat_table():
    """
    Create SERVING_COUNTER_ISSUEDAT_TABLE
    """
    ddb_client.create_table(
        TableName = SERVING_COUNTER_ISSUEDAT_TABLE,
        BillingMode = "PAY_PER_REQUEST",
        AttributeDefinitions = [
            {
                "AttributeName": "event_id",
                "AttributeType": "S"
            },
            {
                "AttributeName": "serving_counter",
                "AttributeType": "N"
            }
        ],
        KeySchema = [
            {
                "AttributeName": "event_id",
                "KeyType": "HASH"
            },
            {
                "AttributeName": "serving_counter",
                "KeyType": "RANGE"
            }
        ],
        SSESpecification = {
            "Enabled": True
        }
    )
    