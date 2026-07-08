# OmniAuto 部署说明

## 项目概述

OmniAuto 是一个 AI API 聚合中转站，对外暴露 OpenAI 兼容接口，后端自动判断调用哪个模型（智能路由），支持故障切换。

## 版本

当前版本：**v0.1.0**

Docker 镜像：`omniauto:v0.1.0`

## 部署步骤

### 1. 确认目录

当前目录即为项目根目录，包含 `docker-compose.yml`、`Dockerfile`、`app/` 等。

### 2. 构建并启动

```bash
docker-compose up -d --build
```

### 3. 验证

```bash
# 检查容器状态
docker ps | grep omniauto

# 测试接口
curl http://localhost:8000/v1/models
# 应返回: {"object":"list","data":[{"id":"auto",...}]}
```

### 4. 访问管理后台

浏览器打开 `http://服务器IP:8000/admin`

首次登录：
- 用户名：`admin`
- 密码：默认 `admin123`（或你在 `OMNIAUTO_ADMIN_PASSWORD` 中设置的密码）

登录后可以在「设置 → 用户管理」中：
- 修改 admin 密码
- 添加更多用户
- 开启/关闭注册

## 部署后配置（在管理后台操作）

1. **设置页面** → 填写智能路由模型配置（API 地址、API Key、模型名）
2. **供应商与模型** → 导入供应商（支持 Kelivo 格式批量导入），然后自动拉取模型
3. **路由** → 为每个分类添加模型，按优先级排序
4. **API Key** → 生成 Key 供客户端使用

## 环境变量（docker-compose.yml 中可修改）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| OMNIAUTO_ADMIN_PASSWORD | admin123 | 默认管理员账号 admin 的密码 |
| OMNIAUTO_REQUIRE_AUTH | 1 | 是否要求登录验证（0=关闭，1=开启） |
| OMNIAUTO_JWT_SECRET | - | JWT 签名密钥，生产环境务必设置 |
| OMNIAUTO_DB_PATH | /app/data/omniauto.db | 数据库路径 |
| OMNIAUTO_IMAGES_DIR | /app/data/images | 图片存储目录 |
| TZ | Asia/Shanghai | 时区 |

## 技术架构

- 后端：Python + FastAPI + SQLite
- 前端：纯 HTML/CSS/JS（单文件）
- 部署：Docker Compose
- 路由模型：通过管理后台配置（推荐硅基流动 GLM-4-9B-Chat）

## 端口

- 8000：API + 管理后台

## 数据持久化

- `./data/omniauto.db`：数据库
- `./data/images/`：生成的图片（7天自动清理）
