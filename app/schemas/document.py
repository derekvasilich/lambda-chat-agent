from datetime import datetime
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

StatusType = Literal["PENDING", "PROCESSING", "FAILED", "READY"]

class UploadRequest(BaseModel):
    file_name: str
    file_type: str  # e.g., "application/pdf" or "text/plain"

class UploadResponse(BaseModel):
    upload_url: str
    object_key: str

class DocumentCreate(BaseModel):
    object_key: str = Field(
        min_length=1,
        max_length=512,
        examples=["billing", "hr_api", "legacy_system"],
    )
    user_id: str
    status: StatusType = Field(
        examples=["PENDING", "PROCESSING", "FAILED", "READY"],
    )
    extracted_text: Optional[str] = Field(
        None,
        examples=["Full text extracted from the document, if available."],
    )
    etag: Optional[str] = Field(
        None,
        examples=["9b2cf535f27731c974343d356d109eb"],
    )
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = Field(
        None,
        examples=[{
            "source": "user_upload", 
            "pages": 10, 
            "word_count": 2500,
            "language": "en"
        }],
    )

class DocumentUpdate(BaseModel):
    status: Optional[StatusType] = Field(
        None,
        examples=["PENDING", "PROCESSING", "FAILED", "READY"],
    )
    extracted_text: Optional[str] = Field(
        None,
        examples=["Updated text extracted from the document, if available."],
    )
    etag: Optional[str] = Field(
        None,
        examples=["9b2cf535f27731c974343d356d109eb"],
    )    
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = Field(
        None,
        examples=[{
            "source": "user_upload", 
            "pages": 10, 
            "word_count": 2500,
            "language": "en"
        }],
    )


class DocumentResponse(BaseModel):
    object_key: str
    user_id: str
    status: StatusType
    etag: Optional[str] = None
    extracted_text: Optional[str] = None
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = None
    last_fetched_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
