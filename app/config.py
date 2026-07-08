"""OmniAuto 配置模块 — 从环境变量加载运行时配置"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（优先项目根目录，本地开发用；Docker 中由 compose 直接注入）
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(str(env_path))

# 管理后台密码（通过环境变量传入，默认 admin123）
ADMIN_PASSWORD = os.getenv("OMNIAUTO_ADMIN_PASSWORD", "admin123")

# JWT 签名密钥（生产环境务必设置）
JWT_SECRET = os.getenv("OMNIAUTO_JWT_SECRET", "omniauto-default-secret")

# 是否要求密码验证（默认关闭，正式部署时设为 1）
REQUIRE_AUTH = os.getenv("OMNIAUTO_REQUIRE_AUTH", "0") == "1"

# 数据库路径（本地开发时使用项目根目录下的 data 文件夹，Docker 中由环境变量覆盖）
_DEFAULT_DB = str(Path(__file__).parent.parent / "data" / "omniauto.db")
DB_PATH = os.getenv("OMNIAUTO_DB_PATH", _DEFAULT_DB)

# 图片存储目录
_DEFAULT_IMAGES = str(Path(__file__).parent.parent / "data" / "images")
IMAGES_DIR = os.getenv("OMNIAUTO_IMAGES_DIR", _DEFAULT_IMAGES)

# 日志目录
_DEFAULT_LOGS = str(Path(__file__).parent.parent / "data" / "logs")
LOGS_DIR = os.getenv("OMNIAUTO_LOGS_DIR", _DEFAULT_LOGS)

# 图片保留天数
IMAGE_RETENTION_DAYS = 7

# 默认路由器模型
DEFAULT_ROUTER_MODEL = "Qwen/Qwen2.5-72B-Instruct"  # 硅基流动模型 ID

# 心跳检测间隔（分钟）
HEARTBEAT_INTERVAL_MINUTES = 30

# Token 用量统计写入间隔（秒）
TOKEN_FLUSH_INTERVAL = 30
