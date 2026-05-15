from __future__ import annotations

import base64
import binascii
import sys
import threading
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field


def _bootstrap_packaging_imports() -> None:
    """Make sibling packaging modules importable in source and PyInstaller modes."""
    package_root = Path(__file__).resolve().parents[1]
    package_root_str = str(package_root)
    if package_root_str not in sys.path:
        sys.path.insert(0, package_root_str)


_bootstrap_packaging_imports()

from cli_entry import (  # noqa: E402
    _add_repo_python_to_sys_path,
    _patch_upstream_data_paths,
    bundled_path,
    model_cache_params,
)
from serve.result_adapter import json_compatible, serialize_ocr_result  # noqa: E402

_add_repo_python_to_sys_path()
_patch_upstream_data_paths()

app = FastAPI(title="RapidOCR Server", version="0.1.0")
_ocr_engine = None
_ocr_lock = threading.Lock()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": json_compatible(exc.errors())})


class OCRRequest(BaseModel):
    image: str = Field(..., min_length=1, description="Base64-encoded image bytes")
    use_det: Optional[bool] = None
    use_cls: Optional[bool] = None
    use_rec: Optional[bool] = None
    return_word_box: Optional[bool] = None
    return_single_char_box: Optional[bool] = None
    text_score: Optional[float] = None
    box_thresh: Optional[float] = None
    unclip_ratio: Optional[float] = None

    class Config:
        extra = "forbid"


def _get_ocr_engine():
    """Initialize RapidOCR lazily and reuse it for subsequent requests."""
    global _ocr_engine

    if _ocr_engine is not None:
        return _ocr_engine

    with _ocr_lock:
        if _ocr_engine is None:
            from rapidocr import RapidOCR

            _ocr_engine = RapidOCR(params=model_cache_params())

    return _ocr_engine


def _index_html_path() -> Path:
    return bundled_path(Path("serve") / "index.html")


def _payload_options(payload: OCRRequest) -> Dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude={"image"}, exclude_none=True)

    return payload.dict(exclude={"image"}, exclude_none=True)


def _decode_base64_image(value: str) -> bytes:
    raw_value = value.strip()
    if not raw_value:
        raise HTTPException(status_code=400, detail="Field 'image' must not be empty.")

    if raw_value.startswith("data:"):
        _, separator, raw_value = raw_value.partition(",")
        if not separator:
            raise HTTPException(status_code=400, detail="Invalid data URL image value.")

    try:
        image_bytes = base64.b64decode(raw_value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Field 'image' must be valid base64.") from exc

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Decoded image is empty.")

    try:
        from PIL import Image, UnidentifiedImageError

        with Image.open(BytesIO(image_bytes)) as image:
            image.verify()
    except ImportError:
        return image_bytes
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="Decoded image is not a valid image.") from exc

    return image_bytes


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    index_path = _index_html_path()
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Web UI file is missing.")

    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/ocr")
def ocr(payload: OCRRequest, request: Request) -> Dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type.lower():
        raise HTTPException(status_code=400, detail="Only application/json is supported.")

    image_bytes = _decode_base64_image(payload.image)
    options = _payload_options(payload)

    try:
        ocr_engine = _get_ocr_engine()
        result = ocr_engine(image_bytes, **options)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail="OCR runtime error.") from exc

    return serialize_ocr_result(result)
