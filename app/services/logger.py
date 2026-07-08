"""日志服务 — 调用日志写入 + 用量统计"""

from datetime import datetime, timedelta
from app.database import db


async def log_call(
    api_key_id: int = 0,
    category_name: str = "",
    model_used: str = "",
    provider_name: str = "",
    is_stream: bool = False,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: int = 0,
    success: bool = True,
    error_msg: str = "",
):
    """异步记录一次 API 调用（入队，不阻塞）"""
    now = datetime.now().isoformat()
    await db.enqueue_write(
        """INSERT INTO call_logs
           (api_key_id, category_name, model_used, provider_name, is_stream,
            prompt_tokens, completion_tokens, total_tokens, duration_ms,
            success, error_msg, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            api_key_id, category_name, model_used, provider_name,
            1 if is_stream else 0,
            prompt_tokens, completion_tokens, total_tokens, duration_ms,
            1 if success else 0, error_msg, now,
        ),
    )


async def get_logs(user_id: int = 0, limit: int = 100, offset: int = 0) -> list:
    return await db.fetch_all(
        """SELECT cl.*, COALESCE(ak.name, '') as api_key_name
           FROM call_logs cl
           LEFT JOIN api_keys ak ON cl.api_key_id = ak.id
           WHERE (? = 0 OR ak.user_id = ?)
           ORDER BY cl.created_at DESC LIMIT ? OFFSET ?""",
        (user_id, user_id, limit, offset),
    )


async def get_token_stats(user_id: int = 0) -> list:
    """按模型汇总 Token 使用量（当前用户）"""
    return await db.fetch_all(
        """SELECT cl.model_used, cl.provider_name,
                  SUM(cl.prompt_tokens) as total_prompt,
                  SUM(cl.completion_tokens) as total_completion,
                  SUM(cl.total_tokens) as total_tokens,
                  COUNT(*) as call_count
           FROM call_logs cl
           LEFT JOIN api_keys ak ON cl.api_key_id = ak.id
           WHERE cl.success = 1 AND (? = 0 OR ak.user_id = ?)
           GROUP BY cl.model_used
           ORDER BY total_tokens DESC""",
        (user_id, user_id),
    )


def _today_start() -> str:
    """今天 00:00 UTC（与 created_at 一致）"""
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _today_start_local() -> str:
    """今天 00:00 本地时间（按服务器时区）"""
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


async def get_token_stats_by_hour(user_id: int = 0) -> dict:
    """今日按小时聚合的 Token 用量，返回给前端用于堆叠柱状图
    返回格式：{
        "hours": ["00","01",...,"23"],
        "models": [{"model_used": "gpt-4o", "color": "#xxx", "data": [0,0,0,...]}, ...],
        "total": 12345
    }
    """
    today_start = _today_start_local()
    rows = await db.fetch_all(
        """SELECT cl.model_used,
                  strftime('%H', cl.created_at) as hour,
                  SUM(cl.prompt_tokens) as prompt_t,
                  SUM(cl.completion_tokens) as completion_t,
                  SUM(cl.total_tokens) as total_t
           FROM call_logs cl
           LEFT JOIN api_keys ak ON cl.api_key_id = ak.id
           WHERE cl.created_at >= ? AND cl.success = 1 AND (? = 0 OR ak.user_id = ?)
           GROUP BY cl.model_used, hour""",
        (today_start, user_id, user_id),
    )

    # 拉取所有模型的颜色映射
    model_rows = await db.fetch_all("SELECT model_id, color FROM models")
    color_map = {r["model_id"]: r["color"] for r in model_rows}

    model_data: dict = {}
    total = 0
    for r in rows:
        mid = r["model_used"]
        if mid not in model_data:
            model_data[mid] = {
                "model_used": mid,
                "color": color_map.get(mid, "#94a3b8"),
                "data": [0] * 24,
                "prompt": [0] * 24,
                "completion": [0] * 24,
            }
        h = int(r["hour"] or 0)
        model_data[mid]["data"][h] = r["total_t"] or 0
        model_data[mid]["prompt"][h] = r["prompt_t"] or 0
        model_data[mid]["completion"][h] = r["completion_t"] or 0
        total += r["total_t"] or 0

    return {
        "hours": [f"{h:02d}" for h in range(24)],
        "models": list(model_data.values()),
        "total": total,
    }


async def get_token_stats_by_range(range_key: str, user_id: int = 0) -> dict:
    """按日期范围汇总
    range_key: today / yesterday / last3 / last7
    """
    now = datetime.now()
    if range_key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_key == "yesterday":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today_start - timedelta(days=1)
        now = today_start - timedelta(microseconds=1)
    elif range_key == "last3":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=2)
    elif range_key == "last7":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    start_iso = start.isoformat()
    end_iso = now.isoformat()

    summary = await db.fetch_one(
        """SELECT SUM(cl.total_tokens) as total_t,
                  COUNT(*) as call_count,
                  AVG(cl.duration_ms) as avg_duration
           FROM call_logs cl
           LEFT JOIN api_keys ak ON cl.api_key_id = ak.id
           WHERE cl.created_at >= ? AND cl.created_at <= ? AND cl.success = 1
             AND (? = 0 OR ak.user_id = ?)""",
        (start_iso, end_iso, user_id, user_id),
    )

    rows = await db.fetch_all(
        """SELECT cl.model_used,
                  SUM(cl.prompt_tokens) as prompt_t,
                  SUM(cl.completion_tokens) as completion_t,
                  SUM(cl.total_tokens) as total_t,
                  COUNT(*) as call_count
           FROM call_logs cl
           LEFT JOIN api_keys ak ON cl.api_key_id = ak.id
           WHERE cl.created_at >= ? AND cl.created_at <= ? AND cl.success = 1
             AND (? = 0 OR ak.user_id = ?)
           GROUP BY cl.model_used
           ORDER BY total_t DESC""",
        (start_iso, end_iso, user_id, user_id),
    )

    model_rows = await db.fetch_all("SELECT model_id, color FROM models")
    color_map = {r["model_id"]: r["color"] for r in model_rows}

    models = []
    total = summary["total_t"] or 0
    total_calls = summary["call_count"] or 0
    avg_duration = summary["avg_duration"] or 0
    for r in rows:
        m_total = r["total_t"] or 0
        models.append({
            "model_used": r["model_used"],
            "color": color_map.get(r["model_used"], "#94a3b8"),
            "prompt": r["prompt_t"] or 0,
            "completion": r["completion_t"] or 0,
            "total": m_total,
            "call_count": r["call_count"] or 0,
        })

    return {
        "range": range_key,
        "start": start_iso,
        "end": end_iso,
        "total": total,
        "total_calls": total_calls,
        "avg_duration": avg_duration,
        "models": models,
    }
