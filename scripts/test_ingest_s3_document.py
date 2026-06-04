import json

# Import your actual lambda file and its handler function
from scripts.ingest_s3_document import lambda_handler
import asyncio

# Actual S3 object key for testing
UPLOAD_KEY = "uploads/4ced8598-2041-70c1-fea4-167ad45682e5/Full%20job%20description.pdf"

# 1. Load your mock event data
S3_EVENT = {
    "Records": [
        {
            "eventVersion": "2.0",
            "eventSource": "aws:s3",
            "awsRegion": "us-east-1",
            "eventTime": "1970-01-01T00:00:00.000Z",
            "eventName": "ObjectCreated:Put",
            "userIdentity": {
                "principalId": "EXAMPLE"
            },
            "requestParameters": {
                "sourceIPAddress": "127.0.0.1"
            },
            "responseElements": {
                "x-amz-request-id": "EXAMPLE123456789",
                "x-amz-id-2": "EXAMPLE123/5678abcdefghijklambdaisawesome/mnopqrstuvwxyzABCDEFGH"
            },
            "s3": {
                "s3SchemaVersion": "1.0",
                "configurationId": "testConfigRule",
                "bucket": {
                    "name": "ai-chat-documents-142731142295-ca-central-1-an",
                    "ownerIdentity": {
                        "principalId": "EXAMPLE"
                    },
                    "arn": "arn:aws:s3:::ai-chat-documents-142731142295-ca-central-1-an"
                },
                "object": {
                    "key": UPLOAD_KEY,
                    "size": 1700000,
                    "eTag": "0123456789abcdef0123456789abcdef",
                    "sequencer": "0A1B2C3D4E5F678901"
                }
            }
        }
    ]
}

# 2. Create a mock context object
mock_context = {}

# 3. Execute the handler locally
print("--- Starting Local Lambda Execution ---")
response = asyncio.run(lambda_handler(S3_EVENT, mock_context))
print("--- Execution Success! Response below: ---")
print(json.dumps(response, indent=2))