"""Detect faces in staff portraits and crop/zoom to centre on the face."""
from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def _load_cv2():
    try:
        import cv2  # type: ignore[import-untyped]

        return cv2
    except ImportError:
        return None


def _decode_image(image_bytes: bytes) -> tuple[object, object] | tuple[None, None]:
    cv2 = _load_cv2()
    if cv2 is None:
        return None, None
    arr = __import__("numpy").frombuffer(image_bytes, dtype=__import__("numpy").uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        return None, None
    return cv2, image


def detect_largest_face(image_bytes: bytes) -> tuple[int, int, int, int] | None:
    """Return (x, y, width, height) of the largest detected face, or None."""
    cv2, image = _decode_image(image_bytes)
    if cv2 is None or image is None:
        return None

    cascade_path = __import__("pathlib").Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=4,
        minSize=(40, 40),
    )
    if len(faces) == 0:
        return None

    x, y, w, h = max(faces, key=lambda box: int(box[2]) * int(box[3]))
    return int(x), int(y), int(w), int(h)


def face_focus_percentages(image_bytes: bytes) -> tuple[float, float] | None:
    """Return CSS object-position percentages (x, y) for the face centre."""
    face = detect_largest_face(image_bytes)
    if face is None:
        return None

    cv2, image = _decode_image(image_bytes)
    if cv2 is None or image is None:
        return None

    height, width = image.shape[:2]
    x, y, w, h = face
    cx = (x + w / 2) / width * 100.0
    cy = (y + h / 2) / height * 100.0
    return round(cx, 1), round(cy, 1)


def crop_portrait_to_face(
    image_bytes: bytes,
    *,
    is_pastor: bool = False,
) -> tuple[bytes, tuple[float, float] | None]:
    """
    Crop to a square centred on the largest face (tighter zoom for pastors).
    Returns (jpeg bytes, focus percentages). If no face is found, returns the original bytes.
    """
    cv2, image = _decode_image(image_bytes)
    if cv2 is None or image is None:
        return image_bytes, None

    face = detect_largest_face(image_bytes)
    if face is None:
        return image_bytes, None

    height, width = image.shape[:2]
    x, y, w, h = face
    cx = x + w / 2
    cy = y + h / 2

    # Pastor portraits zoom in closer on the face.
    pad = 1.45 if is_pastor else 1.75
    side = int(max(w, h) * pad)
    side = max(side, 80)

    x1 = int(round(cx - side / 2))
    y1 = int(round(cy - side / 2))
    x2 = x1 + side
    y2 = y1 + side

    if x1 < 0:
        x2 -= x1
        x1 = 0
    if y1 < 0:
        y2 -= y1
        y1 = 0
    if x2 > width:
        shift = x2 - width
        x1 = max(0, x1 - shift)
        x2 = width
    if y2 > height:
        shift = y2 - height
        y1 = max(0, y1 - shift)
        y2 = height

    cropped = image[y1:y2, x1:x2]
    if cropped.size == 0:
        return image_bytes, None

    ok, encoded = cv2.imencode(".jpg", cropped, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        return image_bytes, None

    crop_h, crop_w = cropped.shape[:2]
    focus = (50.0, 50.0) if crop_w and crop_h else None
    return encoded.tobytes(), focus


def process_image_file(path: str, *, is_pastor: bool = False, overwrite: bool = True) -> bool:
    """Batch helper: detect face and overwrite a local image file."""
    from pathlib import Path

    file_path = Path(path)
    if not file_path.is_file():
        return False

    original = file_path.read_bytes()
    processed, focus = crop_portrait_to_face(original, is_pastor=is_pastor)
    if processed == original:
        return False

    if overwrite:
        if file_path.suffix.lower() in {".jpg", ".jpeg"}:
            file_path.write_bytes(processed)
        else:
            new_path = file_path.with_suffix(".jpg")
            new_path.write_bytes(processed)
    return focus is not None
