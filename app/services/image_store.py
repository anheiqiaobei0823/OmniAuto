"""图片存储管理 — 下载、存储、定时清理"""

import os
import uuid
import httpx
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from app.config import IMAGES_DIR, IMAGE_RETENTION_DAYS


async def save_image(image_url: str) -> str:
    """从 URL 下载图片并保存到本地，返回可访问的相对路径

    Returns:
        图片的相对访问路径（如 /images/uuid.png）
    """
    ext = _guess_ext(image_url)
    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = Path(IMAGES_DIR) / filename

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            save_path.write_bytes(resp.content)
    except Exception as e:
        raise RuntimeError(f"保存图片失败：{str(e)}")

    return f"/images/{filename}"


def _guess_ext(url: str) -> str:
    url = url.lower()
    if ".png" in url:
        return ".png"
    if ".jpg" in url or ".jpeg" in url:
        return ".jpg"
    if ".gif" in url:
        return ".gif"
    if ".webp" in url:
        return ".webp"
    return ".png"


async def cleanup_old_images():
    """删除超过保留天数的图片"""
    cutoff = datetime.now() - timedelta(days=IMAGE_RETENTION_DAYS)
    images_dir = Path(IMAGES_DIR)
    if not images_dir.exists():
        return

    deleted = 0
    for f in images_dir.iterdir():
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            f.unlink()
            deleted += 1


async def cleanup_loop(interval_hours: int = 24):
    """后台清理循环"""
    while True:
        try:
            await cleanup_old_images()
        except Exception:
            pass
        await asyncio.sleep(interval_hours * 3600)
