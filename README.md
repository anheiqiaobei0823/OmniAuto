# OmniAuto

> AI API 智能路由网关 —— 一个入口，接入所有模型。

---

## 这是什么

你有多个 AI 供应商（硅基流动、OpenAI、DeepSeek……），每个供应商有多个模型。客户端要一个个配 API Key，还要自己决定调用哪个模型——烦不烦？

**OmniAuto 帮你做两件事：**

1. **统一入口** —— 对外只暴露一个 `auto` 模型名和一个 API 地址，客户端不用管后面有多少供应商
2. **智能路由** —— 收到请求后自动判断"这是聊天还是写代码还是生图"，然后从你配置的模型优先级列表里选最好的发过去。某个模型挂了自动切下一个

说白了就是个带脑子的 API 中转站。跟 one-api / New API 的区别：它不是简单的随机/轮询分发，而是**按任务类型智能匹配模型**。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 🔀 智能路由 | 7 个任务分类（聊天/写代码/写作/翻译/生图/长任务/默认），每个分类可自定义模型优先级 |
| 🩺 健康检测 | 每 30 分钟自动检测供应商连通性，故障自动跳过 |
| 📊 用量统计 | Token 消耗按小时/天/模型维度统计，图表可视化 |
| 🔑 API Key 管理 | 按供应商分组管理 Key 权限，支持批量导入 |
| 👥 用户隔离 | 多用户各自管理自己的供应商和 Key，互不干扰 |
| 🖼️ 图片生成 | 生图自动下载到本地，返回本地链接而非临时 URL |
| 🏷️ 版本标签 | 每个模型可标记能力标签（视觉/工具/推理/流式），路由时自动过滤 |
| 🐳 一键部署 | Docker Compose 一条命令跑起来 |

---

## 架构

```
客户端  ──→  /v1/chat/completions  ──→  [分类器]  ──→  [分发器]  ──→  最佳模型
                ↑                                    ↓ 失败
                └────────── [降级切换下一个] ←────────┘

客户端只看到 "auto" 一个模型，后面的一切对它是透明的。
```

---

## 快速开始

### 前提

- 装了 Docker 和 Docker Compose
- 至少有一个 AI 供应商的 API Key（硅基流动、OpenAI 等）

### 部署

```bash
# 1. 克隆
git clone https://github.com/anheiqiaobei0823/OmniAuto.git
cd OmniAuto

# 2. （可选）配置环境变量
cp .env.example .env
# 编辑 .env，设置 OMNIAUTO_JWT_SECRET

# 3. 启动
docker compose up -d --build
```

### 初始化

1. 浏览器打开 `http://你的服务器IP:8000/OmniAuto`
2. 用默认账号登录：用户名 `admin`，密码 `admin123`
3. 去「设置」页面配置路由模型的 API Key（用于任务分类）
4. 去「供应商」页面添加你的 AI 供应商
5. 去「模型入口」页面设置每个分类用什么模型

---

## 使用

### 聊天接口

OmniAuto 对外的模型名叫 `auto`，接口兼容 OpenAI 格式：

```bash
curl http://你的服务器IP:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的API-KEY" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### 流式输出

```bash
curl http://你的服务器IP:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的API-KEY" \
  -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "写一首诗"}],
    "stream": true
  }'
```

### 指定模型（跳过路由）

如果你知道要用哪个内部模型，可以直接指定模型名而非 `auto`：

```bash
curl http://你的服务器IP:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的API-KEY" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### 兼容的客户端

任何支持 OpenAI API 格式的客户端都能直接接入：
- **ChatBox / NextChat / LobeChat** —— 填 API 地址和 Key，选 `auto` 模型即可
- **Kelivo** —— 同上
- **Cursor / Continue** —— 填 API Base URL + Key，模型名填 `auto`

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OMNIAUTO_ADMIN_PASSWORD` | `admin123` | 管理员初始密码 |
| `OMNIAUTO_REQUIRE_AUTH` | `1` | 是否启用登录验证（0 关闭） |
| `OMNIAUTO_JWT_SECRET` | — | JWT 签名密钥，生产环境务必设置 |
| `OMNIAUTO_DB_PATH` | `/app/data/omniauto.db` | 数据库路径 |
| `OMNIAUTO_IMAGES_DIR` | `/app/data/images` | 图片存储目录 |
| `TZ` | `Asia/Shanghai` | 时区 |

---

## 技术栈

- **后端**：Python + FastAPI + SQLite + APScheduler
- **前端**：纯 HTML/CSS/JS（Chart.js + SortableJS）
- **部署**：Docker + Docker Compose
- **路由模型**：默认使用硅基流动 Qwen2.5-72B-Instruct（可在后台设置页更换）

---

## 版本

- **v0.1.1**（当前）：用户隔离、手机端适配、管理员面板
- **v0.1.0**：初始版本，核心路由 + 供应商管理 + 用量统计

详见 [更新日志](更新日志.md)。

---

## 许可

MIT
