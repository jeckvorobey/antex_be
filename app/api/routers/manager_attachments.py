"""Protected upload/download endpoints for manager chat attachments."""

from __future__ import annotations

from pathlib import PurePath
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.deps import DbDep, ManagerUser
from app.models.chat import ChatAttachment
from app.schemas.chat import ChatMessageOut
from app.services.chat import ChatService
from app.services.chat_attachments import (
    ALLOWED_ATTACHMENT_KINDS,
    MAX_MANAGER_ATTACHMENT_BYTES,
    download_manager_attachment,
    send_manager_attachment,
)

router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post("/chats/{conversation_id}/attachments", response_model=ChatMessageOut)
async def upload_chat_attachment(
    conversation_id: int,
    request: Request,
    db: DbDep,
    manager: ManagerUser,
    client_request_id: str = Query(..., alias="clientRequestId", min_length=8, max_length=64),
    filename: str = Query(..., min_length=1, max_length=255),
    mime_type: str = Query(
        "application/octet-stream",
        alias="mimeType",
        min_length=1,
        max_length=255,
    ),
    kind: str = Query(..., min_length=1, max_length=24),
) -> ChatMessageOut:
    del manager
    if kind not in ALLOWED_ATTACHMENT_KINDS:
        raise HTTPException(status_code=422, detail="Unsupported attachment kind")

    safe_filename = PurePath(filename).name.strip() or "attachment"
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_MANAGER_ATTACHMENT_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Attachment exceeds 20 MB limit",
            )
    if not content:
        raise HTTPException(status_code=422, detail="Attachment is empty")

    try:
        message, conversation, created = await send_manager_attachment(
            db,
            conversation_id=conversation_id,
            client_request_id=client_request_id,
            content=bytes(content),
            filename=safe_filename,
            mime_type=mime_type,
            kind=kind,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await db.commit()
    service = ChatService(db)
    if created:
        await service.publish_outbound(message, conversation)
    return service.message_out(message)


@router.get("/chat-attachments/{attachment_id}")
async def get_chat_attachment(
    attachment_id: int,
    db: DbDep,
    manager: ManagerUser,
) -> Response:
    del manager
    attachment = await db.get(ChatAttachment, attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail="Attachment not found")
    try:
        content = await download_manager_attachment(attachment)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Telegram attachment is unavailable") from exc

    filename = attachment.filename or f"attachment-{attachment.id}"
    headers = {"Content-Disposition": f"inline; filename*=UTF-8''{quote(filename)}"}
    return Response(
        content=content,
        media_type=attachment.mime_type or "application/octet-stream",
        headers=headers,
    )
