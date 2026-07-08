import httpx
import json

BASE = "http://localhost:8000"
PWD = "admin123"

results = []

def test(name, method, path, body=None, headers=None):
    try:
        h = headers or {}
        if method == "GET":
            r = httpx.get(f"{BASE}{path}", headers=h, timeout=10)
        elif method == "POST":
            r = httpx.post(f"{BASE}{path}", json=body, headers=h, timeout=10)
        elif method == "PUT":
            r = httpx.put(f"{BASE}{path}", json=body, headers=h, timeout=10)
        elif method == "DELETE":
            r = httpx.delete(f"{BASE}{path}", headers=h, timeout=10)
        else:
            r = None
        status = r.status_code if r else 0
        text = r.text[:200] if r else ""
        results.append((name, status, text))
        return r
    except Exception as e:
        results.append((name, "ERR", str(e)))
        return None

# 1. 登录页
test("首页加载", "GET", "/admin")

# 2. 登录
test("登录", "POST", "/admin/auth/login", {"password": PWD})

# 3. 无认证访问 API
test("未认证访问 Provider", "GET", "/admin/providers")

# 带认证头
h = {"x-admin-password": PWD}

# 4. 带认证访问 API
test("Provider 列表", "GET", "/admin/providers", headers=h)
test("Model 列表", "GET", "/admin/models", headers=h)
test("Category 列表", "GET", "/admin/categories", headers=h)
test("API Key 列表", "GET", "/admin/api-keys", headers=h)
test("日志", "GET", "/admin/logs", headers=h)
test("设置", "GET", "/admin/settings", headers=h)

# 5. 添加一个 dummy Provider（硅基流动的路由配置）
provider_body = {
    "name": "硅基流动",
    "api_base": "https://api.siliconflow.cn/v1",
    "api_key": "sk-" + "x" * 48
}
r = test("添加 Provider", "POST", "/admin/providers", provider_body, h)
provider_id = None
if r and r.status_code == 200:
    provider_id = r.json().get("id")

if provider_id:
    test("更新 Provider", "PUT", f"/admin/providers/{provider_id}", {"name": "硅基流动2"}, h)
    test("模型发现（会失败）", "POST", f"/admin/providers/{provider_id}/discover", headers=h)
    test("删除 Provider", "DELETE", f"/admin/providers/{provider_id}", headers=h)

# 6. 创建 API Key
test("创建 API Key", "POST", "/admin/api-keys", headers=h)

# 7. 对外接口：/v1/models
test("外部模型列表", "GET", "/v1/models")

# 8. 对外接口：/v1/chat/completions（无 Provider，应失败）
test("Chat 无 Provider", "POST", "/v1/chat/completions", {
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "hello"}]
})

# 9. 对外接口：/v1/images/generations（无 Provider，应失败）
test("Images 无 Provider", "POST", "/v1/images/generations", {
    "prompt": "a cat"
})

# 输出结果
print("\n========== 测试结果 ==========")
for name, status, text in results:
    print(f"[{status}] {name}")
    if status not in (200, 201) and not str(status).startswith("2"):
        print(f"    -> {text}")
