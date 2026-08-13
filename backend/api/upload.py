"""文件上传（api_contract.md §4.7）。

- POST /api/v1/upload  multipart 上传 → {url}

文件落盘到 UPLOAD_DIR（默认 uploads/），URL 为 {upload_url_prefix}/{name}
（默认 /static/uploads/...），由 main.py 挂载 StaticFiles 提供访问。
仅接受图片扩展名，单文件上限 10MB。
"""

import os
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.config import get_settings

router = APIRouter()

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_MAX_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/api/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    settings = get_settings()
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "仅支持图片文件（jpg/png/gif/webp/svg）"},
        )
    content = await file.read()
    if len(content) > _MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail={"code": "VALIDATION_ERROR", "message": "文件过大（上限 10MB）"},
        )
    upload_dir = settings.upload_dir
    os.makedirs(upload_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(upload_dir, name)
    with open(path, "wb") as f:
        f.write(content)
    url = f"{settings.upload_url_prefix.rstrip('/')}/{name}"
    return {"url": url}
