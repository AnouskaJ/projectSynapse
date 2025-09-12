"""
Evidence repository for managing evidence files and data
"""
import os
import base64
import shutil
import time
import requests
import mimetypes
from typing import List, Optional

from ..logger import get_logger

log = get_logger(__name__)

EVIDENCE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "evidence")
os.makedirs(EVIDENCE_ROOT, exist_ok=True)

def save_evidence_images(order_id: str, images: Optional[List[str]]) -> List[str]:
    """Save evidence images for an order"""
    saved = []
    if not images:
        return saved
        
    order_dir = os.path.join(EVIDENCE_ROOT, order_id)
    os.makedirs(order_dir, exist_ok=True)

    for i, src in enumerate(images):
        try:
            if isinstance(src, str) and src.startswith("data:image/"):
                # Handle base64 data URLs
                header, b64 = src.split(",", 1)
                ext = ".jpg"
                if "png" in header: ext = ".png"
                if "webp" in header: ext = ".webp"
                blob = base64.b64decode(b64)
                fp = os.path.join(order_dir, f"evidence_{int(time.time())}_{i}{ext}")
                with open(fp, "wb") as f: 
                    f.write(blob)
                saved.append(fp)
                continue

            if isinstance(src, str) and src.startswith(("http://", "https://")):
                # Handle HTTP URLs
                r = requests.get(src, timeout=15)
                r.raise_for_status()
                ct = r.headers.get("Content-Type", "image/jpeg")
                ext = mimetypes.guess_extension(ct) or ".jpg"
                fp = os.path.join(order_dir, f"evidence_{int(time.time())}_{i}{ext}")
                with open(fp, "wb") as f: 
                    f.write(r.content)
                saved.append(fp)
                continue

            if isinstance(src, str) and os.path.exists(src):
                # Handle file paths
                ext = os.path.splitext(src)[1] or ".jpg"
                fp = os.path.join(order_dir, f"evidence_{int(time.time())}_{i}{ext}")
                shutil.copyfile(src, fp)
                saved.append(fp)
                continue
                
        except Exception as e:
            log.warning(f"[evidence] save fail {i}: {e}")
    
    return saved

def load_evidence_files(order_id: str) -> List[str]:
    """Load evidence files for an order"""
    order_dir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(order_dir): 
        return []
    
    files = [os.path.join(order_dir, f) for f in os.listdir(order_dir)
             if os.path.isfile(os.path.join(order_dir, f))]
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return files

def purge_evidence(order_id: str) -> int:
    """Delete all saved evidence files for an order. Returns how many files were removed."""
    order_dir = os.path.join(EVIDENCE_ROOT, order_id)
    if not os.path.isdir(order_dir):
        return 0
    
    count = 0
    for f in os.listdir(order_dir):
        path = os.path.join(order_dir, f)
        try:
            if os.path.isfile(path):
                os.remove(path)
                count += 1
        except Exception as e:
            log.warning(f"[evidence] purge failed for {path}: {e}")
    
    return count