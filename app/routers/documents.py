from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
import boto3
from botocore.config import Config
import urllib
from app.auth import get_current_user, UserClaims
from app.config import settings
from app.repositories.documents import DocumentRepository
from app.schemas.document import DocumentCreate, DocumentListResponse, DocumentResponse, DocumentUpdate, DocumentUpdate, UploadRequest, UploadResponse
from app.dynamodb import get_documents_table

router = APIRouter()

REGIONAL_S3_ENDPOINT = f"https://s3.{settings.AWS_REGION}.amazonaws.com"

# Force signature version 4 for modern, secure S3 requests
s3_client = boto3.client(
    "s3", 
    region_name=settings.AWS_REGION,
    endpoint_url=REGIONAL_S3_ENDPOINT,  # Allow for custom S3-compatible endpoints
    config=Config(signature_version="s3v4")
)

async def get_doc_repo(doc_table=Depends(get_documents_table)) -> DocumentRepository:
    return DocumentRepository(doc_table)

@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List documents",
    tags=["Documents"],
)
async def list_documents(
    page_size: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    repo: DocumentRepository = Depends(get_doc_repo),
    user: UserClaims = Depends(get_current_user),
):
    docs, next_cursor = await repo.list(user.sub, page_size, cursor)
    return DocumentListResponse(items=docs, next_cursor=next_cursor)


@router.get(
    "/documents/status",
    response_model=DocumentResponse,
    summary="Get the processing status of an uploaded document",
    tags=["Documents"],
)
async def get_document_status(
    object_key: str = Query(..., description="The unique S3 object key of the uploaded document"),
    repo: DocumentRepository = Depends(get_doc_repo),
    user: UserClaims = Depends(get_current_user),
):
    object_key = urllib.parse.unquote_plus(object_key)
    doc = await repo.get(user.sub, object_key)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "not_found", "message": "Document not found", "details": {}}},
        )
    return doc

@router.post(
    "/documents/upload-url",
    response_model=UploadResponse,
    summary="Generate a pre-signed S3 URL for secure document upload",
    tags=["Documents"],
)
async def generate_upload_url(
    request: UploadRequest,
    user: UserClaims = Depends(get_current_user),
    repo=Depends(get_doc_repo),
):
    # Restrict file types at the gate
    allowed_types = ["application/pdf", "text/plain"]
    if request.file_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported file format. Only PDF and Text files allowed.")

    # Create a unique, multi-tenant safe object path inside S3
    # This prevents users from overwriting each other's documents
    object_key = f"uploads/{user.sub}/{request.file_name}"

    try:
        # Generate the secure URL valid for exactly 15 minutes
        presigned_url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET,
                "Key": object_key,
                "ContentType": request.file_type
            },
            ExpiresIn=900  # 15 minutes
        )

        if await repo.get(user.sub, object_key):
            await repo.update(object_key, user.sub, DocumentUpdate(
                status="PENDING",
            ))           
        else:
            await repo.create(user.sub, DocumentCreate(
                object_key=object_key,
                user_id=user.sub,
                status="PENDING",
            ))

        return UploadResponse(upload_url=presigned_url, object_key=object_key)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to secure upload channel: {str(e)}")
