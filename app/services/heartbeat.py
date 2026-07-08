"""心跳检测 — 定时检查每个 Provider 的连通性"""

import asyncio
from datetime import datetime
from app.database import db
from app.providers.registry import registry


async def _check_one(provider_id: int, provider_obj):
    """检测单个 Provider 并写历史"""
    import time
    start = time.time()
    is_ok, err_msg = await provider_obj.check_health()
    duration_ms = int((time.time() - start) * 1000)
    # 状态判断：成功但 >3s 算慢（黄色）
    if is_ok and duration_ms > 3000:
        status = "warn"
    else:
        status = "normal" if is_ok else "error"
    now = datetime.utcnow().isoformat()

    # 更新最新状态
    existing = await db.fetch_one(
        "SELECT id FROM heartbeat_status WHERE provider_id = ?", (provider_id,)
    )
    if existing:
        await db.execute(
            "UPDATE heartbeat_status SET status = ?, last_check_at = ?, error_msg = ? WHERE provider_id = ?",
            (status, now, err_msg, provider_id),
        )
    else:
        await db.execute(
            "INSERT INTO heartbeat_status (provider_id, status, last_check_at, error_msg, created_at) VALUES (?, ?, ?, ?, ?)",
            (provider_id, status, now, err_msg, now),
        )

    # 写历史
    await db.execute(
        "INSERT INTO heartbeat_history (provider_id, status, duration_ms, error_msg, created_at) VALUES (?, ?, ?, ?, ?)",
        (provider_id, status, duration_ms, err_msg, now),
    )

    # 同时更新该 Provider 下所有模型的状态
    await db.execute(
        "UPDATE models SET health_status = ?, last_check_at = ? WHERE provider_id = ? AND is_active = 1",
        (status, now, provider_id),
    )

    # 清理每个 Provider 只保留最近 10 条历史
    await db.execute(
        """DELETE FROM heartbeat_history
           WHERE provider_id = ? AND id NOT IN (
             SELECT id FROM heartbeat_history
             WHERE provider_id = ?
             ORDER BY created_at DESC LIMIT 10
           )""",
        (provider_id, provider_id),
    )


async def check_all_providers():
    providers = await db.get_active_providers()
    for p in providers:
        provider = await registry.get(p["id"])
        if not provider:
            continue
        try:
            await _check_one(p["id"], provider)
        except Exception:
            pass


async def heartbeat_all():
    """手动触发（接口调用）"""
    await check_all_providers()


async def heartbeat_loop(interval_minutes: int = 10):
    while True:
        try:
            await check_all_providers()
        except Exception:
            pass
        await asyncio.sleep(interval_minutes * 60)
