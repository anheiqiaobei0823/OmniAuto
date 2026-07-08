"""OmniAuto 配置模块 — 从环境变量加载运行时配置"""

import os

# 管理后台密码（通过环境变量传入，默认 admin123）
ADMIN_PASSWORD = os.getenv("OMNIAUTO_ADMIN_PASSWORD", "admin123")

# JWT 签名密钥（生产环境务必设置）
JWT_SECRET = os.getenv("OMNIAUTO_JWT_SECRET", "omniauto-default-secret")

# 是否要求密码验证（默认关闭，正式部署时设为 1）
REQUIRE_AUTH = os.getenv("OMNIAUTO_REQUIRE_AUTH", "0") == "1"

# 数据库路径
DB_PATH = os.getenv("OMNIAUTO_DB_PATH", "/app/data/omniauto.db")

# 图片存储目录
IMAGES_DIR = os.getenv("OMNIAUTO_IMAGES_DIR", "/app/data/images")

# 日志目录
LOGS_DIR = os.getenv("OMNIAUTO_LOGS_DIR", "/app/logs")

# 图片保留天数
IMAGE_RETENTION_DAYS = 7

# 默认路由器模型
DEFAULT_ROUTER_MODEL = "Qwen/Qwen2.5-72B-Instruct"  # 硅基流动模型 ID

# 心跳检测间隔（分钟）
HEARTBEAT_INTERVAL_MINUTES = 30

# Token 用量统计写入间隔（秒）
TOKEN_FLUSH_INTERVAL = 30
