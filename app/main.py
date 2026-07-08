"""OmniAuto 主入口 — FastAPI 应用"""

import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.database import db, init_db_sync
from app.router import api, admin
from app.services.heartbeat import heartbeat_loop
from app.services.image_store import cleanup_loop
from app.config import HEARTBEAT_INTERVAL_MINUTES


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动：初始化数据库、连接、启动后台任务
    init_db_sync()
    await db.connect()

    # 启动心跳检测
    heartbeat_task = asyncio.create_task(heartbeat_loop(HEARTBEAT_INTERVAL_MINUTES))
    # 启动图片清理（每 24 小时）
    cleanup_task = asyncio.create_task(cleanup_loop(24))

    yield

    # 关闭：停止后台任务、断开数据库
    heartbeat_task.cancel()
    cleanup_task.cancel()
    await db.disconnect()


app = FastAPI(
    title="OmniAuto",
    description="AI API 智能路由网关 — 统一管理所有 AI 模型 API",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── 注册路由 ──────────────────────────────────────────

app.include_router(admin.router)
app.include_router(api.router)

# ─── 静态文件（管理后台前端） ─────────────────────────────

static_dir = Path(__file__).parent / "admin" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ─── 图片目录（生图保存） ────────────────────────────────

images_dir = Path(__file__).parent.parent / "data" / "images"
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")
