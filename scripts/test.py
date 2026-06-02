import json
import os

# Import your actual lambda file and its handler function
from doc_to_text import lambda_handler
import asyncio

# 1. Load your mock event data
BASE_DIR = os.path.dirname(__file__)
with open(os.path.join(BASE_DIR, 's3-event.json'), 'r') as f:
    mock_event = json.load(f)

# 2. Create a mock context object
mock_context = {}

# 3. Execute the handler locally
print("--- Starting Local Lambda Execution ---")
response = asyncio.run(lambda_handler(mock_event, mock_context))
print("--- Execution Success! Response below: ---")
print(json.dumps(response, indent=2))