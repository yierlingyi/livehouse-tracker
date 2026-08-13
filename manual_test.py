#!/usr/bin/env python3
"""后端手动测试脚本 —— 一键验证各接口是否正常（含「青岛」默认城市校验）。

用法：
    python manual_test.py                 # 默认测 http://127.0.0.1:8000
    python manual_test.py http://IP:8000  # 指定后端地址

特性：
    * 纯标准库（urllib），无需安装任何依赖。
    * 所有「写操作」均自清理，跑完不留测试数据。
    * 输出 [PASS]/[FAIL]，最后给出汇总与退出码（0=全过，1=有失败）。
"""

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

# 让中文/特殊字符在 Windows GBK 控制台也能正常显示（UTF-8 输出）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")

_results = []


def report(name, ok, detail=""):
    _results.append((name, ok))
    mark = "PASS" if ok else "FAIL"
    suffix = f"  ->  {detail}" if detail else ""
    print(f"[{mark}] {name}{suffix}")


def call(method, path, body=None, token=None):
    """发起请求，返回 (status, parsed_json_or_None)。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, (json.loads(raw) if raw else None)
        except json.JSONDecodeError:
            return e.code, None
    except urllib.error.URLError as e:
        return 0, {"__error__": str(e.reason)}


def get(path, token=None):
    return call("GET", path, token=token)


def post(path, body, token=None):
    return call("POST", path, body=body, token=token)


def delete(path, token=None):
    return call("DELETE", path, token=token)


def main():
    print("=" * 60)
    print(f"后端手动测试  目标: {BASE}")
    print("=" * 60)

    # ---------- 0. 连通性 ----------
    print("\n[0] 连通性检查")
    status, _ = get("/api/v1/livehouses")
    if status != 200:
        report("后端可访问", False, f"HTTP {status} —— 请确认后端已启动（bash scripts/start.sh）")
        print("\n测试中止：无法连接后端。")
        sys.exit(1)
    report("后端可访问", True, f"HTTP {status}")

    # ---------- 1. 公开接口 ----------
    print("\n[1] 公开接口（无需登录）")
    status, body = get("/api/v1/livehouses")
    venues = (body or {}).get("items", [])
    report("GET /livehouses 场地列表", status == 200 and bool(venues), f"共 {len(venues)} 个场地")

    vid = venues[0]["id"] if venues else None
    if vid is not None:
        status, body = get(f"/api/v1/livehouses/{vid}")
        city = (body or {}).get("city")
        report("GET /livehouses/{id} 场地详情", status == 200 and body is not None,
               f"city={city!r}")
    else:
        report("GET /livehouses/{id} 场地详情", False, "无场地可测")

    # 青岛数据
    status, body = get("/api/v1/lives/full?city=%E9%9D%92%E5%B2%9B&page_size=20")
    data = (body or {}).get("data", [])
    all_qd = all((x.get("city") == "青岛") for x in data)
    report("GET /lives/full?city=青岛", status == 200 and bool(data) and all_qd,
           f"{len(data)} 条且 city 均为青岛={all_qd}")

    # Tokyo 应已清空
    status, body = get("/api/v1/lives/full?city=Tokyo&page_size=5")
    tokyo_empty = status == 200 and (body or {}).get("data") == []
    report("GET /lives/full?city=Tokyo", tokyo_empty, "返回空列表（Tokyo 已清除）")

    status, body = get("/api/v1/bands")
    report("GET /bands 乐队列表", status == 200, f"共 {len((body or {}).get('items', []))} 支乐队")

    status, body = get("/api/v1/cms/project")
    report("GET /cms/project 项目信息", status == 200, "")

    # ---------- 2. 管理员认证 ----------
    print("\n[2] 管理员认证")
    status, body = post("/api/v1/admin/login", {"username": ADMIN_USER, "password": ADMIN_PASS})
    token = (body or {}).get("token")
    if status == 200 and token:
        report("POST /admin/login", True, f"账号 {ADMIN_USER} 登录成功")
    else:
        report("POST /admin/login", False, f"HTTP {status}（请检查 ADMIN_USER/ADMIN_PASS）")

    # ---------- 3. 写操作 + 默认城市（自清理） ----------
    print("\n[3] 写操作 + 默认城市（跑完自动清理）")
    if token:
        status, body = post("/api/v1/livehouses", {"name": "手动测试_默认城市_临时"}, token=token)
        city = (body or {}).get("city")
        new_id = (body or {}).get("id")
        ok_default = (status == 200 and city == "青岛")
        report("POST /livehouses（不带 city 默认青岛）", ok_default, f"返回 city={city!r}")
        if new_id:
            s2, _ = delete(f"/api/v1/livehouses/{new_id}", token=token)
            report("DELETE /livehouses/{id} 清理测试数据", s2 == 200, f"id={new_id}")
        else:
            report("DELETE /livehouses/{id} 清理测试数据", False, "无 id 可清理")
    else:
        report("POST /livehouses（不带 city 默认青岛）", False, "未登录，跳过")
        report("DELETE /livehouses/{id} 清理测试数据", False, "未登录，跳过")

    # ---------- 4. 城市管理（自清理） ----------
    print("\n[4] 城市管理（跑完自动清理）")
    # GET /api/v1/cities 为公开接口，无需登录
    status, body = get("/api/v1/cities")
    cities = (body or {}).get("items", []) if status == 200 else []
    names = [c.get("name") for c in cities if isinstance(c, dict)]
    old_hardcoded = ["Tokyo", "Osaka", "Shanghai", "Beijing", "Guangzhou", "Shenzhen"]
    report("GET /cities 城市列表（公开）", status == 200 and bool(cities), f"共 {len(cities)} 个城市")
    report("GET /cities 含默认城市青岛", status == 200 and "青岛" in names,
           "青岛" if "青岛" in names else f"当前城市: {names}")
    report("GET /cities 不含旧硬编码城市",
           status == 200 and all(n not in names for n in old_hardcoded),
           f"排除 {old_hardcoded}")

    # POST 创建临时城市 → DELETE 自清理；重复名 → 400；空白名 → 400
    if token:
        tmp_name = f"手动测试城市_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        status, body = post("/api/v1/admin/cities", {"name": tmp_name}, token=token)
        new_id = (body or {}).get("id")
        ok_create = status == 200 and (body or {}).get("name") == tmp_name
        report("POST /admin/cities 创建临时城市", ok_create,
               f"status={status} name={(body or {}).get('name')!r}")
        if new_id is not None:
            s2, b2 = delete(f"/api/v1/admin/cities/{new_id}", token=token)
            report("DELETE /admin/cities/{id} 清理临时城市",
                   s2 == 200 and (b2 or {}).get("ok") is True, f"id={new_id}")
        else:
            report("DELETE /admin/cities/{id} 清理临时城市", False, "无 id 可清理")

        status, body = post("/api/v1/admin/cities", {"name": "青岛"}, token=token)
        dup_ok = status == 400 and (body or {}).get("code") == "CITIES_DUPLICATE"
        report("POST /admin/cities 重复青岛 → 400", dup_ok,
               f"status={status} code={(body or {}).get('code')!r}")

        status, body = post("/api/v1/admin/cities", {"name": "   "}, token=token)
        blank_ok = status == 400 and (body or {}).get("code") == "VALIDATION_ERROR"
        report("POST /admin/cities 空白城市名 → 400", blank_ok,
               f"status={status} code={(body or {}).get('code')!r}")
    else:
        report("POST /admin/cities 创建临时城市", False, "未登录，跳过")
        report("DELETE /admin/cities/{id} 清理临时城市", False, "未登录，跳过")
        report("POST /admin/cities 重复青岛 → 400", False, "未登录，跳过")
        report("POST /admin/cities 空白城市名 → 400", False, "未登录，跳过")

    # ---------- 汇总 ----------
    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"汇总: {passed}/{total} 通过")
    for name, ok in _results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("=" * 60)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
