# OmniAuto

你是否也因为有一堆大模型的 API Key 而烦恼？

OmniAuto 帮你把它们合为一个入口，由一个小模型智能调度。

## 功能

- 🔀 **智能路由** — 多任务分类，每个分类自定义模型优先级，故障自动切换
- 🏢 **供应商管理** — 管理所有 AI 供应商，支持 JSON 格式批量导入
- 🩺 **健康检测** — 每 30 分钟自动检测连通性，故障模型自动跳过
- 📊 **用量统计** — Token 消耗按小时/天/模型维度统计，图表可视化
- 🔑 **API Key 管理** — 按供应商分组管理权限，支持创建、禁用、复制
- 👤 **用户系统** — JWT 登录，多用户各自管理自己的供应商和 Key
- 🖼️ **图片生成** — 生图后下载到本地保留 7 天，返回本地链接
- 🏷️ **模型能力标签** — 标记视觉、工具、推理、流式等能力，路由自动过滤
- 🐳 **Docker 部署** — `docker compose up -d --build` 一条命令跑起来

## 下载

最新版本：[v0.1.1](https://github.com/anheiqiaobei0823/OmniAuto/releases/tag/v0.1.1) · 历史版本：[Releases](https://github.com/anheiqiaobei0823/OmniAuto/releases)

## 快速开始

```bash
cd OmniAuto
cp .env.example .env   # 编辑 .env，设置 OMNIAUTO_JWT_SECRET
docker compose up -d --build
```

启动后访问 `http://<服务器地址>:8000/OmniAuto`，用 `admin` / `admin123` 登录。去「设置」配置路由模型，去「供应商」添加 AI 供应商，即用。

## 使用

兼容 OpenAI API 格式，模型名填 `OmniAuto`：

```bash
curl http://<服务器地址>:8000/v1/chat/completions \
  -H "Authorization: Bearer 你的API-KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"OmniAuto","messages":[{"role":"user","content":"你好"}]}'
```

支持 ChatBox、NextChat、LobeChat、Kelivo 等客户端直接接入。

## 技术栈

Python + FastAPI + SQLite · 纯 HTML/CSS/JS 管理后台 · Docker Compose

## 更新日志

[v0.1.1](https://github.com/anheiqiaobei0823/OmniAuto/releases/tag/v0.1.1) · [v0.1.0](https://github.com/anheiqiaobei0823/OmniAuto/releases/tag/v0.1.0) · [完整日志](更新日志.md)

## 许可

MIT
