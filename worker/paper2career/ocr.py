"""Text acquisition: native PDF text first, OCR for scanned PDFs and page images.

Three OCR engines are supported:
  * tesseract (pytesseract + the tesseract binary) - used in GitHub Actions (apt-get install tesseract-ocr)
  * rapidocr (pip-only, ONNX models)              - convenient on laptops without Tesseract
  * windows  (built-in Windows 10/11 OCR)        - zero-install fallback on Windows (scripts/winocr.ps1)
Select with OCR_ENGINE=tesseract|rapidocr|windows; default picks whichever is available.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image

from .models import OcrLine

log = logging.getLogger(__name__)

Image.MAX_IMAGE_PIXELS = 200_000_000  # newspaper pages are large but trusted-size


def available_engine() -> str:
    wanted = os.environ.get("OCR_ENGINE", "").lower()
    if wanted:
        return wanted
    if shutil.which("tesseract") or os.environ.get("TESSERACT_CMD"):
        return "tesseract"
    try:
        import rapidocr  # noqa: F401
        return "rapidocr"
    except ImportError:
        pass
    if sys.platform == "win32":
        return "windows"
    raise RuntimeError("No OCR engine found: install Tesseract or `pip install rapidocr onnxruntime`")


def ocr_image(image: Image.Image) -> list[OcrLine]:
    engine = available_engine()
    log.info("OCR (%s) on %dx%d image", engine, *image.size)
    if engine == "tesseract":
        return _ocr_tesseract(image)
    if engine == "rapidocr":
        return _ocr_rapid_tiled(image)
    if engine == "windows":
        return _ocr_windows(image)
    raise RuntimeError(f"Unknown OCR_ENGINE {engine!r}")


def ocr_file(path: Path) -> list[OcrLine]:
    if path.suffix.lower() == ".pdf":
        return pdf_lines(path)
    with Image.open(path) as img:
        return ocr_image(img.convert("RGB"))


# ---------------------------------------------------------------- PDF

def pdf_lines(path: Path, page_index: int = 0, min_native_chars: int = 200) -> list[OcrLine]:
    """Native text lines from a PDF page; falls back to rendering + OCR when the page is a scan."""
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        page = doc[page_index]
        lines: list[OcrLine] = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(span["text"] for span in line["spans"]).strip()
                if text:
                    x0, y0, x1, y1 = line["bbox"]
                    lines.append(OcrLine(text, x0, y0, x1, y1, 1.0))
        if sum(len(l.text) for l in lines) >= min_native_chars:
            log.info("Using native PDF text (%d lines)", len(lines))
            return lines
        log.info("PDF page has no usable text layer; rendering for OCR")
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return ocr_image(img)


# ---------------------------------------------------------------- tesseract

def detect_columns(image: Image.Image) -> list[tuple[int, int]]:
    """Detect vertical text columns on a newspaper page using projection profile.
    Returns list of (x0, x1) column boundaries."""
    import numpy as np

    gray = image.convert("L")
    w, h = gray.size
    y0, y1 = int(h * 0.08), int(h * 0.96)
    sub = gray.crop((0, y0, w, y1))
    arr = np.asarray(sub)
    ink = (arr < 170).astype(np.float32)
    proj = ink.sum(axis=0)
    win = max(5, int(w * 0.005))
    smoothed = np.convolve(proj, np.ones(win) / win, mode="same")
    med = float(np.median(smoothed))
    thresh = med * 0.35
    is_text = smoothed > thresh

    columns = []
    in_col = False
    start = 0
    for x in range(len(is_text)):
        if is_text[x] and not in_col:
            in_col = True
            start = x
        elif not is_text[x] and in_col:
            in_col = False
            if (x - start) > w * 0.05:
                columns.append((max(0, start - 5), min(w, x + 5)))
    if in_col and (len(is_text) - start) > w * 0.05:
        columns.append((max(0, start - 5), min(w, len(is_text))))

    return columns


def _ocr_tesseract(image: Image.Image) -> list[OcrLine]:
    # Only pre-segment into columns on broadsheet / large pages (>= 2500px wide)
    if image.width >= 2500:
        columns = detect_columns(image)
        if len(columns) >= 2:
            log.info("Detected %d newspaper columns; processing column-by-column with Tesseract", len(columns))
            all_lines = []
            for x0, x1 in columns:
                strip = image.crop((x0, 0, x1, image.height))
                strip_lines = _ocr_tesseract_strip(strip, config="--psm 4")
                for ln in strip_lines:
                    all_lines.append(OcrLine(
                        ln.text,
                        ln.x0 + x0,
                        ln.y0,
                        ln.x1 + x0,
                        ln.y1,
                        ln.conf,
                    ))
            return all_lines

    return _ocr_tesseract_strip(image, config="--psm 3")


def _ocr_tesseract_strip(image: Image.Image, config: str = "--psm 4") -> list[OcrLine]:
    import pytesseract

    if os.environ.get("TESSERACT_CMD"):
        pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    gray = image.convert("L")
    data = pytesseract.image_to_data(gray, config=config, output_type=pytesseract.Output.DICT)
    grouped: dict[tuple, list[int]] = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            grouped.setdefault(key, []).append(i)

    lines = []
    for idxs in grouped.values():
        # Sort words by horizontal left position
        sorted_idxs = sorted(idxs, key=lambda idx: data["left"][idx])

        # Split words into separate sub-lines if there is a column gutter gap (> 35px or > 1.8x height)
        sub_lines: list[list[int]] = [[]]
        for idx in sorted_idxs:
            if sub_lines[-1]:
                prev_idx = sub_lines[-1][-1]
                prev_right = data["left"][prev_idx] + data["width"][prev_idx]
                gap = data["left"][idx] - prev_right
                h = max(data["height"][idx], data["height"][prev_idx])
                if gap > max(35, int(h * 1.8)):
                    sub_lines.append([])
            sub_lines[-1].append(idx)

        for s_idxs in sub_lines:
            if not s_idxs:
                continue
            text = " ".join(data["text"][i] for i in s_idxs)
            x0 = min(data["left"][i] for i in s_idxs)
            y0 = min(data["top"][i] for i in s_idxs)
            x1 = max(data["left"][i] + data["width"][i] for i in s_idxs)
            y1 = max(data["top"][i] + data["height"][i] for i in s_idxs)
            conf = sum(float(data["conf"][i]) for i in s_idxs) / len(s_idxs) / 100
            lines.append(OcrLine(text, x0, y0, x1, y1, round(conf, 3)))
    return lines


# ---------------------------------------------------------------- Windows 10/11 built-in OCR (local dev only)

def _ocr_windows(image: Image.Image) -> list[OcrLine]:
    import json
    import subprocess
    import tempfile

    script = Path(__file__).resolve().parent.parent / "scripts" / "winocr.ps1"
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "page.png"
        image.save(png)
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(png)],
            capture_output=True, text=True, encoding="utf-8", check=True, timeout=600,
        ).stdout
    return [OcrLine(d["text"], d["x0"], d["y0"], d["x1"], d["y1"], d["conf"]) for d in json.loads(out or "[]")]


# ---------------------------------------------------------------- rapidocr

@lru_cache(maxsize=1)
def _rapid_engine():
    from rapidocr import RapidOCR
    return RapidOCR()


def _ocr_rapid_tiled(image: Image.Image, tile: int = 1400, overlap: int = 160) -> list[OcrLine]:
    """RapidOCR downsizes large inputs, which destroys small classified print, so OCR in overlapping tiles."""
    import numpy as np

    engine = _rapid_engine()
    w, h = image.size
    lines: list[OcrLine] = []
    step = tile - overlap
    for top in range(0, max(h - overlap, 1), step):
        for left in range(0, max(w - overlap, 1), step):
            box = (left, top, min(left + tile, w), min(top + tile, h))
            result = engine(np.asarray(image.crop(box)))
            if result is None or getattr(result, "boxes", None) is None:
                continue
            for pts, text, score in zip(result.boxes, result.txts, result.scores):
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                ln = OcrLine(text, min(xs) + left, min(ys) + top, max(xs) + left, max(ys) + top, float(score))
                # Lines touching an inner tile edge are seen whole by the neighbouring tile; skip the cut copy.
                if _touches_inner_edge(ln, box, w, h, margin=4):
                    continue
                lines.append(ln)
    return _dedupe_overlaps(lines)


def _touches_inner_edge(ln: OcrLine, box, w, h, margin) -> bool:
    left, top, right, bottom = box
    return (
        (left > 0 and ln.x0 - left < margin)
        or (top > 0 and ln.y0 - top < margin)
        or (right < w and right - ln.x1 < margin)
        or (bottom < h and bottom - ln.y1 < margin)
    )


def _dedupe_overlaps(lines: list[OcrLine]) -> list[OcrLine]:
    kept: list[OcrLine] = []
    for ln in sorted(lines, key=lambda l: -(l.x1 - l.x0)):
        if any(_iou(ln, k) > 0.5 for k in kept):
            continue
        kept.append(ln)
    return kept


def _iou(a: OcrLine, b: OcrLine) -> float:
    ix = max(0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    if not inter:
        return 0.0
    area = lambda l: (l.x1 - l.x0) * (l.y1 - l.y0)  # noqa: E731
    return inter / (area(a) + area(b) - inter)
