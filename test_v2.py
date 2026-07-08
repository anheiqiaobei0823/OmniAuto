"""OmniAuto 端到端测试 v2 — 覆盖所有新接口"""

import json
import sys
sys.path.insert(0, '.')

import urllib.request
import urllib.parse
import urllib.error

BASE = 'http://localhost:8000'
PWD = 'admin123'


def req(path, method='GET', data=None, auth=True):
    url = BASE + path
    headers = {'Content-Type': 'application/json'}
    if auth:
        headers['x-admin-password'] = PWD
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(r, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode())
            return e.code, err_data
        except Exception:
            return e.code, {}


def expect(label, ok, msg=''):
    mark = '✅' if ok else '❌'
    print(f'  {mark} {label}{(": " + msg) if msg else ""}')
    return ok


results = []
print('=' * 60)
print('1. 登录')
print('=' * 60)
code, _ = req('/admin/auth/login', 'POST', {'password': PWD})
results.append(expect('密码登录', code == 200))
code, _ = req('/admin/auth/login', 'POST', {'password': 'wrong'})
results.append(expect('错误密码拒绝', code == 401))

print('\n' + '=' * 60)
print('2. 供应商管理')
print('=' * 60)
code, providers = req('/admin/providers')
results.append(expect('列出供应商', code == 200 and isinstance(providers, list)))

# 添加供应商
code, r = req('/admin/providers', 'POST', {
    'name': '测试供应商A', 'api_base': 'https://api.test.com/v1', 'api_key': 'sk-test-123'
})
results.append(expect('添加供应商', code == 200))
new_pid = r.get('id')

# 编辑
code, _ = req(f'/admin/providers/{new_pid}', 'PUT', {'name': '测试供应商A-已编辑'})
results.append(expect('编辑供应商', code == 200))

print('\n' + '=' * 60)
print('3. 模型发现（预期失败，因为URL是假的）')
print('=' * 60)
code, r = req(f'/admin/providers/{new_pid}/discover', 'POST')
results.append(expect('发现模型（应失败）', code == 400 or (code == 200 and isinstance(r, dict))))

# 手动添加模型
from app.database import db, init_db_sync
import asyncio
init_db_sync()
async def add_test_models():
    await db.connect()
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    await db.execute(
        """INSERT INTO models (provider_id, model_id, display_name, color, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (new_pid, 'test-model-1', '测试模型1', '#3b82f6', now, now)
    )
    await db.execute(
        """INSERT INTO models (provider_id, model_id, display_name, color, is_active, created_at, updated_at)
           VALUES (?, ?, ?, ?, 1, ?, ?)""",
        (new_pid, 'test-model-2', '测试模型2', '#10b981', now, now)
    )
asyncio.run(add_test_models())
asyncio.run(db.disconnect())

code, models = req('/admin/models')
results.append(expect('列出模型', code == 200 and len(models) >= 2))
test_model_id = next((m['id'] for m in models if m['model_id'] == 'test-model-1'), None)
results.append(expect('模型有 color 字段', test_model_id is not None and any('color' in m for m in models)))

# 模型能力更新
code, _ = req(f'/admin/models/{test_model_id}', 'PUT', {'supports_stream': True})
results.append(expect('更新模型能力', code == 200))

print('\n' + '=' * 60)
print('4. 分类路由')
print('=' * 60)
code, cats = req('/admin/categories')
results.append(expect('列出分类', code == 200 and len(cats) >= 7))

cat_names = [c['name'] for c in cats]
results.append(expect('含"翻译"分类', '翻译' in cat_names))
results.append(expect('含"默认"分类', '默认' in cat_names))

# 取一个分类，往里加模型
test_cat = next((c for c in cats if c['name'] == '写代码'), None)
if test_cat:
    code, _ = req(f'/admin/categories/{test_cat["id"]}/models/{test_model_id}', 'POST')
    results.append(expect('添加模型到分类', code == 200))

    code, _ = req(f'/admin/categories/{test_cat["id"]}/models', 'PUT', {'model_ids': [test_model_id]})
    results.append(expect('排序分类模型', code == 200))

print('\n' + '=' * 60)
print('5. API Key')
print('=' * 60)
code, r = req('/admin/api-keys', 'POST', {'name': '测试Key', 'allowed_models': [test_model_id]})
results.append(expect('生成 API Key', code == 200 and r.get('data', {}).get('key', '').startswith('sk-')))
new_key_id = r.get('data', {}).get('id')

code, keys = req('/admin/api-keys')
results.append(expect('列出 API Key 含 allowed_models', code == 200 and 'allowed_models' in (keys[0] if keys else {})))

code, _ = req(f'/admin/api-keys/{new_key_id}', 'PUT', {'name': '测试Key-已编辑'})
results.append(expect('编辑 API Key', code == 200))

print('\n' + '=' * 60)
print('6. 用量统计')
print('=' * 60)
code, r = req('/admin/logs/hourly')
results.append(expect('按小时统计', code == 200 and 'hours' in r and 'models' in r))

code, r = req('/admin/logs/range?range=today')
results.append(expect('今日范围', code == 200 and 'models' in r))

code, r = req('/admin/logs/range?range=last3')
results.append(expect('近3天范围', code == 200))

code, r = req('/admin/logs/range?range=last7')
results.append(expect('近7天范围', code == 200))

print('\n' + '=' * 60)
print('7. 心跳历史')
print('=' * 60)
code, r = req('/admin/heartbeat/history')
results.append(expect('心跳历史', code == 200 and isinstance(r, list)))

print('\n' + '=' * 60)
print('8. 设置')
print('=' * 60)
code, r = req('/admin/settings', 'PUT', {
    'router_enabled': '1',
    'router_api_base': 'https://api.siliconflow.cn/v1',
    'router_api_key': 'sk-test',
    'router_model': 'THUDM/GLM-4-9B-Chat',
})
results.append(expect('保存设置', code == 200))

code, s = req('/admin/settings')
results.append(expect('读取设置', code == 200 and s.get('router_model') == 'THUDM/GLM-4-9B-Chat'))

print('\n' + '=' * 60)
print('9. 清理测试数据')
print('=' * 60)
code, _ = req(f'/admin/api-keys/{new_key_id}', 'DELETE')
results.append(expect('删除 API Key', code == 200))

code, _ = req(f'/admin/providers/{new_pid}', 'DELETE')
results.append(expect('删除供应商', code == 200))

print('\n' + '=' * 60)
total = len(results)
passed = sum(results)
print(f'通过：{passed}/{total}')
if passed == total:
    print('🎉 全部测试通过！')
    sys.exit(0)
else:
    print(f'⚠️ {total - passed} 项失败')
    sys.exit(1)
