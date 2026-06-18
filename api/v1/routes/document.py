from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.response import success_response
from api.v1.dependencies.auth import get_current_user
from api.v1.models.user import User
from api.v1.schemas.document import DocumentResponse
from api.v1.services import document_service

document_router = APIRouter(prefix="/documents", tags=["Documents"])


@document_router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    document = await document_service.create_document(user.id, file, db)
    return success_response(
        message="Document uploaded successfully",
        status_code=status.HTTP_201_CREATED,
        data=DocumentResponse.model_validate(document).model_dump(),
    )
