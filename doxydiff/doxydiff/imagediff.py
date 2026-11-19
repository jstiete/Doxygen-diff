"""Pixel-level diff for embedded images (logos, screenshots, ...), as
opposed to generated call/inheritance graphs which are diffed structurally
in graphdiff.py. Uses OpenCV to locate the bounding box of the changed
region and draws a red rectangle around it, git-diff style.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np


@dataclass
class ImageDiffResult:
    identical: bool
    size_changed: bool
    changed_pixel_ratio: float
    bbox: Optional[Tuple[int, int, int, int]]  # x1,y1,x2,y2 in the new image
    old_size: Tuple[int, int]
    new_size: Tuple[int, int]


def _read(path: str):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"could not read image: {path}")
    return img


def diff_images(old_path: str, new_path: str, threshold: int = 25) -> ImageDiffResult:
    old_img = _read(old_path)
    new_img = _read(new_path)
    old_size = (old_img.shape[1], old_img.shape[0])
    new_size = (new_img.shape[1], new_img.shape[0])
    size_changed = old_size != new_size

    # Compare on a common canvas (top-left aligned, padded with white) so
    # that a resized image still yields a meaningful bounding box instead of
    # failing outright.
    h = max(old_img.shape[0], new_img.shape[0])
    w = max(old_img.shape[1], new_img.shape[1])
    canvas_old = np.full((h, w, 3), 255, dtype=np.uint8)
    canvas_new = np.full((h, w, 3), 255, dtype=np.uint8)
    canvas_old[: old_img.shape[0], : old_img.shape[1]] = old_img
    canvas_new[: new_img.shape[0], : new_img.shape[1]] = new_img

    gray_old = cv2.cvtColor(canvas_old, cv2.COLOR_BGR2GRAY)
    gray_new = cv2.cvtColor(canvas_new, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(gray_old, gray_new)
    _, mask = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)

    changed_pixels = int(np.count_nonzero(mask))
    total_pixels = mask.shape[0] * mask.shape[1]
    ratio = changed_pixels / total_pixels if total_pixels else 0.0

    if changed_pixels == 0 and not size_changed:
        return ImageDiffResult(True, False, 0.0, None, old_size, new_size)

    bbox = None
    if changed_pixels > 0:
        # dilate a bit so nearby changed regions merge into one bounding box
        kernel = np.ones((5, 5), np.uint8)
        mask_dilated = cv2.dilate(mask, kernel, iterations=2)
        contours, _ = cv2.findContours(mask_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            xs1, ys1, xs2, ys2 = [], [], [], []
            for c in contours:
                x, y, cw, ch = cv2.boundingRect(c)
                xs1.append(x)
                ys1.append(y)
                xs2.append(x + cw)
                ys2.append(y + ch)
            bbox = (min(xs1), min(ys1), max(xs2), max(ys2))
            # clip bbox to the new image's actual size
            bbox = (
                min(bbox[0], new_img.shape[1]),
                min(bbox[1], new_img.shape[0]),
                min(bbox[2], new_img.shape[1]),
                min(bbox[3], new_img.shape[0]),
            )

    return ImageDiffResult(False, size_changed, ratio, bbox, old_size, new_size)


def render_highlighted_image(new_path: str, bbox: Optional[Tuple[int, int, int, int]], out_path: str, pad: int = 6) -> str:
    """Save a copy of the new image with a red rectangle drawn around bbox."""
    img = _read(new_path)
    if bbox is not None:
        x1, y1, x2, y2 = bbox
        h, w = img.shape[:2]
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 220), 3)  # BGR red, git-diff style
    cv2.imwrite(out_path, img)
    return out_path
