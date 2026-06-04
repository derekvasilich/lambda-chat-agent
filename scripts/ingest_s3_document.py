import os
import json
import urllib.parse
import boto3
from app.schemas.document import DocumentUpdate
from app.routers.documents import DocumentRepository
import pdfplumber
from app.dynamodb import get_documents_table

from dotenv import load_dotenv
load_dotenv()

# Initialize AWS resource clients
s3_client = boto3.client("s3")

async def lambda_handler(event, context):
    """
    AWS Lambda handler automatically invoked by an S3 's3:ObjectCreated:Put' event for injesting a new document upload. It performs the following steps:
    1. Parses the S3 event to extract bucket name, object key, and metadata.
    2. Creates a new document record in DynamoDB with status "PROCESSING".
    3. Downloads the file from S3 to the Lambda's temporary storage.
    4. Extracts text content based on file type (PDF or TXT).
    5. Updates the DynamoDB record with the extracted text and changes status to "READY" for UI consumption.
    6. Handles errors gracefully by updating the document status to "FAILED" if any step encounters an issue, ensuring the UI can reflect the failure state.
    """
    async for table in get_documents_table():
        repo = DocumentRepository(table)
        try:
            # 1. Parse the S3 Event details out of the AWS invocation payload
            for record in event['Records']:
                bucket_name = record['s3']['bucket']['name']

                # S3 keys can contain spaces or special characters. AWS URL-encodes them in events, 
                # so we MUST decode it to get the actual valid filename path.
                raw_key = record['s3']['object']['key']
                object_key = urllib.parse.unquote_plus(raw_key)

                # The ETag can act as an integrity checksum hash if needed
                etag = record['s3']['object'].get('eTag', '').replace('"', '')
                size = record['s3']['object']['size']
                user_id = object_key.split('/')[1]  # Assuming the key format is "uploads/{user_id}/filename.ext"

                metadata = {
                    "source": "s3_ingestion",
                    "file_extension": object_key.split('.')[-1].lower(),
                    "word_count": "",
                    "file_name": object_key.split("/")[-1],
                    "bucket": bucket_name,
                    "size": size
                }

                # Push the processing state directly into DynamoDB
                await repo.update(object_key, user_id, DocumentUpdate(
                    status="PROCESSING",
                    etag=etag,
                    metadata=metadata
                ))

                # 2. Establish our unique Document ID using the S3 object key
                local_file_path = f"/tmp/processing_target.{metadata['file_extension']}"
                s3_client.download_file(bucket_name, object_key, local_file_path)

                # Extract raw text based on the file layout rules
                extracted_text = ""

                if metadata["file_extension"] == "pdf":
                    with pdfplumber.open(local_file_path) as pdf:
                        for index, page in enumerate(pdf.pages):
                            extracted_text += f"Page {index} \n"
                            print(f"Extracted page {index}.")
                            page_text = page.extract_text()
                            if page_text:
                                extracted_text += page_text + "\n\n"

                elif metadata["file_extension"] == "txt":
                    with open(local_file_path, "r", encoding="utf-8") as f:
                        extracted_text = f.read()

                # Update metadata with word count for observability and potential UI display
                metadata["word_count"] = len(extracted_text.split())

                # Push the ready text context and state directly into DynamoDB
                await repo.update(object_key, user_id, DocumentUpdate(
                    status="READY",
                    extracted_text=extracted_text.strip(),
                    etag=etag,
                    metadata=metadata
                ))

                # 6. Housekeeping: Remove the local file to keep your serverless container clean
                if os.path.exists(local_file_path):
                    os.remove(local_file_path)

                print(f"Successfully indexed document: {object_key} with {len(extracted_text.split())} words.")

            return {"statusCode": 200, "body": json.dumps("File successfully parsed and indexed.")}
        except Exception as e:
            print(f"Critical Ingestion Failure: {str(e)}")
            # If your database item structure exists, log the failure state so the UI unblocks
            try:
                await repo.update(object_key, user_id, DocumentUpdate(
                    status="FAILED",
                    extracted_text=str(e),
                    etag=etag,
                    metadata=metadata,
                ))
            except:
                pass
            raise e
