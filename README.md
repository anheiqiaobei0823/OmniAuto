# OmniAuto

一个专注于 AI API 管理与智能模型路由的工具。

## 核心理念

- 统一管理所有 API Key
- AI 自动识别任务类型
- 智能选择最佳模型
- 用户自由配置任务对应模型
- 自动统计 Token 与使用情况

## 快速开始

```bash
docker-compose up -d --build
```

然后访问 `http://localhost:8000/admin`。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| OMNIAUTO_ADMIN_PASSWORD | admin123 | 默认管理员密码 |
| OMNIAUTO_REQUIRE_AUTH | 1 | 是否启用登录验证 |
| OMNIAUTO_JWT_SECRET | - | JWT 签名密钥（生产环境务必设置） |
| OMNIAUTO_DB_PATH | /app/data/omniauto.db | 数据库路径 |
| OMNIAUTO_IMAGES_DIR | /app/data/images | 图片存储目录 |
| TZ | Asia/Shanghai | 时区 |

## 详细部署说明

详见 `DEPLOY.md`。
