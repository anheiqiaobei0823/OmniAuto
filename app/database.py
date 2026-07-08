"""OmniAuto 数据库层 — SQLite + 异步队列写入"""

import aiosqlite
import asyncio
import sqlite3
import random
from pathlib import Path
from datetime import datetime
from typing import Optional
from app.config import DB_PATH


# ─── 模型颜色调色板（不重复分配） ────────────────────────
# 24 种色相均匀分布，饱和度/亮度舒适，颜色辨识度高
MODEL_COLOR_PALETTE = [
    "#3b82f6",  # 蓝
    "#10b981",  # 翠绿
    "#f59e0b",  # 橙
    "#ef4444",  # 红
    "#8b5cf6",  # 紫
    "#ec4899",  # 粉
    "#06b6d4",  # 青
    "#84cc16",  # 草绿
    "#f97316",  # 橙红
    "#a855f7",  # 紫蓝
    "#eab308",  # 金
    "#0ea5e9",  # 天蓝
    "#d946ef",  # 品红
    "#14b8a6",  # 蓝绿
    "#dc2626",  # 深红
    "#65a30d",  # 橄榄
    "#7c3aed",  # 深紫
    "#0284c7",  # 深蓝
    "#f43f5e",  # 玫红
    "#059669",  # 深绿
    "#d97706",  # 棕
    "#7e22ce",  # 葡萄紫
    "#0891b2",  # 深青
    "#22c55e",  # 绿
]


# ─── 同步建表（初始化时调用） ─────────────────────────────

SCHEMA_SQL = """
-- Provider（模型提供商）
CREATE TABLE IF NOT EXISTS providers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,                   -- 显示名称
    api_base    TEXT NOT NULL,                   -- Base URL（如 https://api.xxx.com/v1）
    api_path    TEXT NOT NULL DEFAULT '/chat/completions',  -- API 路径
    api_key     TEXT NOT NULL,                   -- API Key
    is_active   INTEGER NOT NULL DEFAULT 1,      -- 启用/禁用
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 模型
CREATE TABLE IF NOT EXISTS models (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id     INTEGER NOT NULL REFERENCES providers(id),
    model_id        TEXT NOT NULL,               -- 下游模型 ID（如 gpt-4o）
    display_name    TEXT,                        -- 显示名称
    color           TEXT NOT NULL DEFAULT '#3b82f6',  -- 图表颜色
    is_active       INTEGER NOT NULL DEFAULT 1,

    -- 能力标签
    supports_stream  INTEGER NOT NULL DEFAULT 1,
    supports_vision  INTEGER NOT NULL DEFAULT 0,
    supports_tools   INTEGER NOT NULL DEFAULT 0,
    supports_image_gen INTEGER NOT NULL DEFAULT 0,
    supports_reasoning INTEGER NOT NULL DEFAULT 0,

    -- 心跳状态：normal / error / cooling
    health_status   TEXT NOT NULL DEFAULT 'unknown',
    last_check_at   TEXT,

    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

-- 分类路由
CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    is_default  INTEGER NOT NULL DEFAULT 0,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

-- 分类-模型优先级（有序列表）
CREATE TABLE IF NOT EXISTS category_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    model_id    INTEGER NOT NULL REFERENCES models(id),
    priority    INTEGER NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE(category_id, model_id)
);

-- 对外 API Key（客户端调用的 Key）
CREATE TABLE IF NOT EXISTS api_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    key_value       TEXT NOT NULL UNIQUE,
    name            TEXT,                            -- 备注名
    allowed_models  TEXT NOT NULL DEFAULT '[]',      -- JSON 数组：可访问的模型 ID，空数组=全部
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL
);

-- 调用日志
CREATE TABLE IF NOT EXISTS call_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id      INTEGER REFERENCES api_keys(id),
    category_name   TEXT,
    model_used      TEXT,
    provider_name   TEXT,
    is_stream       INTEGER NOT NULL DEFAULT 0,
    prompt_tokens   INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    success         INTEGER NOT NULL DEFAULT 1,
    error_msg       TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_call_logs_created ON call_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_call_logs_api_key ON call_logs(api_key_id);
CREATE INDEX IF NOT EXISTS idx_call_logs_model ON call_logs(model_used);

-- Provider 心跳历史（最近 10 次）
CREATE TABLE IF NOT EXISTS heartbeat_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id     INTEGER NOT NULL REFERENCES providers(id),
    status          TEXT NOT NULL,
    duration_ms     INTEGER NOT NULL DEFAULT 0,
    error_msg       TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_provider ON heartbeat_history(provider_id, created_at DESC);

-- Provider 心跳状态
CREATE TABLE IF NOT EXISTS heartbeat_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id     INTEGER NOT NULL REFERENCES providers(id),
    status          TEXT NOT NULL DEFAULT 'unknown',
    last_check_at   TEXT,
    error_msg       TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE(provider_id)
);

-- 系统用户
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 路由器配置（系统设置）
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def init_db_sync():
    """同步方式初始化数据库（Docker 启动时调用一次）"""
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)

    # ─── 老库迁移：补字段 ────────────────────────────
    def has_col(table, col):
        cur = conn.execute(f"PRAGMA table_info({table})")
        return any(row[1] == col for row in cur.fetchall())

    if not has_col("models", "color"):
        conn.execute("ALTER TABLE models ADD COLUMN color TEXT NOT NULL DEFAULT '#3b82f6'")
    if not has_col("models", "health_status"):
        conn.execute("ALTER TABLE models ADD COLUMN health_status TEXT NOT NULL DEFAULT 'unknown'")
    if not has_col("models", "last_check_at"):
        conn.execute("ALTER TABLE models ADD COLUMN last_check_at TEXT")
    if not has_col("api_keys", "allowed_models"):
        conn.execute("ALTER TABLE api_keys ADD COLUMN allowed_models TEXT NOT NULL DEFAULT '[]'")
    if not has_col("providers", "api_path"):
        conn.execute("ALTER TABLE providers ADD COLUMN api_path TEXT NOT NULL DEFAULT '/chat/completions'")
    if not has_col("models", "supports_reasoning"):
        conn.execute("ALTER TABLE models ADD COLUMN supports_reasoning INTEGER NOT NULL DEFAULT 0")
    if not has_col("heartbeat_history", "duration_ms"):
        conn.execute("ALTER TABLE heartbeat_history ADD COLUMN duration_ms INTEGER NOT NULL DEFAULT 0")

    # 老数据迁移：把 api_base 末尾的 /chat/completions 剥出来当 api_path
    try:
        rows = conn.execute("SELECT id, api_base, api_path FROM providers").fetchall()
        for row in rows:
            base = (row[1] or "").rstrip("/")
            if base.endswith("/chat/completions"):
                new_base = base[:-len("/chat/completions")]
                new_path = "/chat/completions"
                conn.execute("UPDATE providers SET api_base = ?, api_path = ? WHERE id = ?",
                             (new_base, new_path, row[0]))
    except Exception:
        pass

    # ─── 老库迁移：补表 ──────────────────────────────
    conn.execute(
        """CREATE TABLE IF NOT EXISTS heartbeat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL REFERENCES providers(id),
            status TEXT NOT NULL,
            error_msg TEXT,
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_heartbeat_provider ON heartbeat_history(provider_id, created_at DESC)"
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

    # 首次启动：创建默认管理员账号
    from app.config import ADMIN_PASSWORD
    admin_exists = conn.execute("SELECT 1 FROM users WHERE username = 'admin'").fetchone()
    if not admin_exists:
        import hashlib
        pwd_hash = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("admin", pwd_hash, 1, 1, now, now)
        )

    # ─── 插入默认分类 ────────────────────────────────
    default_categories = [
        ("聊天", 0, 1),
        ("写代码", 0, 2),
        ("写作", 0, 3),
        ("翻译", 0, 4),
        ("生图", 0, 5),
        ("长任务", 0, 6),
        ("默认", 1, 99),
    ]
    now = datetime.utcnow().isoformat()
    for name, is_default, sort_order in default_categories:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, is_default, sort_order, created_at) VALUES (?, ?, ?, ?)",
            (name, is_default, sort_order, now),
        )

    # 老数据迁移：给已有模型分配颜色
    try:
        rows = conn.execute(
            "SELECT id, color FROM models WHERE color IS NULL OR color = '' OR color = '#3b82f6'"
        ).fetchall()
        existing_colors = {row[0] for row in conn.execute("SELECT DISTINCT color FROM models").fetchall()}
        for row in rows:
            available = [c for c in MODEL_COLOR_PALETTE if c not in existing_colors]
            if available:
                color = random.choice(available)
            else:
                color = f"#{random.randint(0, 0xffffff):06x}"
            existing_colors.add(color)
            conn.execute("UPDATE models SET color = ? WHERE id = ?", (color, row[0]))
    except Exception:
        pass

    conn.commit()
    conn.close()


# ─── 异步数据库操作 ──────────────────────────────────────

class Database:
    def __init__(self):
        self.pool: Optional[aiosqlite.Connection] = None
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._write_task: Optional[asyncio.Task] = None

    async def connect(self):
        self.pool = await aiosqlite.connect(DB_PATH)
        self.pool.row_factory = aiosqlite.Row
        self._write_task = asyncio.create_task(self._write_loop())

    async def disconnect(self):
        if self._write_task:
            self._write_task.cancel()
        if self.pool:
            await self.pool.close()

    # ─── 直接同步写（管理后台用） ────────────────────────

    async def execute(self, sql: str, params: tuple = ()):
        await self.pool.execute(sql, params)
        await self.pool.commit()

    # ─── 异步写入队列（日志/高频写入） ───────────────────

    async def enqueue_write(self, sql: str, params: tuple = ()):
        await self._write_queue.put((sql, params))

    async def _write_loop(self):
        while True:
            sql, params = await self._write_queue.get()
            try:
                await self.pool.execute(sql, params)
                await self.pool.commit()
            except Exception:
                pass

    # ─── 异步查询 ──────────────────────────────────────

    async def fetch_all(self, sql: str, params: tuple = ()) -> list:
        cursor = await self.pool.execute(sql, params)
        return await cursor.fetchall()

    async def fetch_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        cursor = await self.pool.execute(sql, params)
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None

    # ─── 颜色分配 ──────────────────────────────────────

    async def get_next_available_color(self) -> str:
        """获取一个未使用的颜色（按调色板顺序分配，确保前几个模型颜色差异最大）"""
        rows = await self.fetch_all("SELECT DISTINCT color FROM models")
        used = {row["color"] for row in rows}
        for c in MODEL_COLOR_PALETTE:
            if c not in used:
                return c
        # 调色板用完，随机生成
        while True:
            color = f"#{random.randint(0, 0xffffff):06x}"
            if color not in used:
                return color

    # ─── 常用 CRUD Provider ──────────────────────────────

    async def get_active_providers(self) -> list:
        return await self.fetch_all(
            "SELECT * FROM providers WHERE is_active = 1 ORDER BY name"
        )

    async def get_provider_by_id(self, pid: int) -> Optional[dict]:
        return await self.fetch_one(
            "SELECT * FROM providers WHERE id = ?", (pid,)
        )

    async def get_models_by_provider(self, provider_id: int) -> list:
        return await self.fetch_all(
            "SELECT * FROM models WHERE provider_id = ? AND is_active = 1 ORDER BY model_id",
            (provider_id,),
        )

    async def get_all_models(self) -> list:
        return await self.fetch_all(
            """SELECT m.*, p.name as provider_name, p.api_base
               FROM models m JOIN providers p ON m.provider_id = p.id
               WHERE m.is_active = 1 AND p.is_active = 1
               ORDER BY m.model_id"""
        )

    async def get_categories(self) -> list:
        return await self.fetch_all(
            "SELECT * FROM categories ORDER BY sort_order"
        )

    async def get_category_models(self, category_id: int) -> list:
        return await self.fetch_all(
            """SELECT cm.priority, m.*, p.name as provider_name, p.api_base, p.api_key
               FROM category_models cm
               JOIN models m ON cm.model_id = m.id
               JOIN providers p ON m.provider_id = p.id
               WHERE cm.category_id = ? AND m.is_active = 1 AND p.is_active = 1
               ORDER BY cm.priority""",
            (category_id,),
        )

    async def get_default_category(self) -> Optional[dict]:
        rows = await self.fetch_all(
            "SELECT * FROM categories WHERE is_default = 1 LIMIT 1"
        )
        return rows[0] if rows else None

    async def get_api_key(self, key_value: str) -> Optional[dict]:
        return await self.fetch_one(
            "SELECT * FROM api_keys WHERE key_value = ? AND is_active = 1",
            (key_value,),
        )

    # ─── 设置 ──────────────────────────────────────────

    async def get_setting(self, key: str) -> Optional[str]:
        row = await self.fetch_one(
            "SELECT value FROM settings WHERE key = ?", (key,)
        )
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str):
        await self.enqueue_write(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


# 全局单例
db = Database()
