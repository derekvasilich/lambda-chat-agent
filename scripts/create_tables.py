"""Idempotent script to create DynamoDB tables for chat-agent.

Usage:
    python scripts/create_tables.py

Reads DYNAMODB_ENDPOINT_URL, AWS_REGION from environment or .env file.
"""

import os
import sys

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

import boto3
from botocore.exceptions import ClientError

ENDPOINT_URL = os.getenv("DYNAMODB_ENDPOINT_URL", "")
REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_CONVERSATIONS = os.getenv("DYNAMODB_TABLE_CONVERSATIONS", "chat_conversations")
TABLE_MESSAGES = os.getenv("DYNAMODB_TABLE_MESSAGES", "chat_messages")

TABLE_DEFINITIONS = [
    {
        "TableName": TABLE_CONVERSATIONS,
        "KeySchema": [
            {"AttributeName": "id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "user_id-created_at-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
    {
        "TableName": TABLE_MESSAGES,
        "KeySchema": [
            {"AttributeName": "conversation_id", "KeyType": "HASH"},
            {"AttributeName": "sort_key", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "conversation_id", "AttributeType": "S"},
            {"AttributeName": "sort_key", "AttributeType": "S"},
        ],
        "BillingMode": "PAY_PER_REQUEST",
    },
]


def create_tables():
    kwargs = {"region_name": REGION}
    if ENDPOINT_URL:
        kwargs["endpoint_url"] = ENDPOINT_URL

    client = boto3.client("dynamodb", **kwargs)

    for definition in TABLE_DEFINITIONS:
        table_name = definition["TableName"]
        try:
            client.describe_table(TableName=table_name)
            print(f"Table '{table_name}' already exists — skipping.")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            print(f"Creating table '{table_name}' ...")
            client.create_table(**definition)
            waiter = client.get_waiter("table_exists")
            waiter.wait(TableName=table_name)
            print(f"Table '{table_name}' created.")

def handler(event, context):
    create_tables()
    return {"statusCode": 200, "body": "Tables created"}

if __name__ == "__main__":
    create_tables()
