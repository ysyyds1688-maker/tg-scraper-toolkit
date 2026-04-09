"""
帳號管理工具 — 互動式介面
不需要編輯任何檔案，全部透過選單操作
"""

import asyncio
import json
import os
import sys

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SESSIONS_DIR = os.path.join(TOOLKIT_DIR, "sessions")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("accounts", [])


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump({"accounts": accounts}, f, ensure_ascii=False, indent=2)


def header():
    clear()
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║           帳號管理                            ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")


# ============================================================
# 查看帳號
# ============================================================

def show_accounts():
    header()
    accounts = load_accounts()
    if not accounts:
        print("  目前沒有任何帳號\n")
        return

    print(f"  共 {len(accounts)} 個帳號:\n")
    print(f"  {'#':<4} {'名稱':<10} {'電話':<18} {'API ID':<12} {'上限':<6} {'延遲':<12} {'代理':<15} {'狀態':<6}")
    print(f"  {'─'*85}")

    for i, acc in enumerate(accounts, 1):
        proxy = acc.get("proxy")
        proxy_str = f"{proxy['host']}:{proxy['port']}" if proxy else "直連"
        enabled = "\033[32m啟用\033[0m" if acc.get("enabled", True) else "\033[31m停用\033[0m"
        delay_str = f"{acc.get('delay_min', 60)}-{acc.get('delay_max', 180)}s"
        session_exists = os.path.exists(acc["session_name"] + ".session")
        login_str = "\033[32m已登入\033[0m" if session_exists else "\033[33m未登入\033[0m"

        print(f"  {i:<4} {acc['name']:<10} {acc['phone']:<18} {acc['api_id']:<12} "
              f"{acc.get('daily_limit', 30):<6} {delay_str:<12} {proxy_str:<15} {enabled} {login_str}")

    print()


# ============================================================
# 新增帳號
# ============================================================

def add_account():
    header()
    accounts = load_accounts()
    num = len(accounts) + 1

    print("  ── 新增帳號 ──\n")
    print("  請依序輸入以下資訊（留空使用預設值）:\n")

    # 名稱
    default_name = f"帳號{num}"
    name = input(f"  帳號名稱 [{default_name}]: ").strip() or default_name

    # 電話
    while True:
        phone = input("  手機號碼（含國碼，如 +886912345678）: ").strip()
        if phone.startswith("+") and len(phone) > 8:
            break
        if phone and not phone.startswith("+"):
            phone = "+886" + phone.lstrip("0")
            confirm = input(f"  自動加國碼: {phone}，正確嗎？(y/n): ").strip().lower()
            if confirm == "y":
                break
        print("  \033[31m請輸入正確的手機號碼\033[0m")

    # API ID
    while True:
        api_id_str = input("  API ID（數字）: ").strip()
        if api_id_str.isdigit():
            api_id = int(api_id_str)
            break
        print("  \033[31m請輸入數字\033[0m")

    # API Hash
    while True:
        api_hash = input("  API Hash（字串）: ").strip()
        if len(api_hash) > 10:
            break
        print("  \033[31m請輸入正確的 API Hash\033[0m")

    # 每日上限
    limit_str = input("  每日發送上限 [25]: ").strip()
    daily_limit = int(limit_str) if limit_str.isdigit() else 25

    # 延遲
    delay_min_str = input("  最短延遲秒數 [60]: ").strip()
    delay_min = int(delay_min_str) if delay_min_str.isdigit() else 60

    delay_max_str = input("  最長延遲秒數 [180]: ").strip()
    delay_max = int(delay_max_str) if delay_max_str.isdigit() else 180

    # 代理
    print("\n  代理設定:")
    print("    [1] 不使用代理（直連）")
    print("    [2] 設定 SOCKS5 代理")
    proxy_choice = input("  選擇 [1]: ").strip() or "1"

    proxy = None
    if proxy_choice == "2":
        proxy_host = input("  代理 IP: ").strip()
        proxy_port = input("  代理 Port: ").strip()
        proxy_user = input("  帳號（沒有按 Enter 跳過）: ").strip()
        proxy_pwd = input("  密碼（沒有按 Enter 跳過）: ").strip()
        proxy = {
            "type": "socks5",
            "host": proxy_host,
            "port": int(proxy_port) if proxy_port.isdigit() else 1080,
            "username": proxy_user,
            "password": proxy_pwd,
        }

    # Session name
    session_name = f"sessions/session_{num:02d}"

    # 確認
    print(f"\n  ── 確認資訊 ──")
    print(f"  名稱:     {name}")
    print(f"  電話:     {phone}")
    print(f"  API ID:   {api_id}")
    print(f"  API Hash: {api_hash[:6]}...{api_hash[-4:]}")
    print(f"  每日上限: {daily_limit}")
    print(f"  延遲:     {delay_min}-{delay_max}s")
    print(f"  代理:     {proxy['host']+':'+str(proxy['port']) if proxy else '直連'}")

    confirm = input(f"\n  確認新增？(y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return

    account = {
        "name": name,
        "phone": phone,
        "api_id": api_id,
        "api_hash": api_hash,
        "session_name": session_name,
        "proxy": proxy,
        "daily_limit": daily_limit,
        "delay_min": delay_min,
        "delay_max": delay_max,
        "enabled": True,
    }

    accounts.append(account)
    save_accounts(accounts)
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    print(f"\n  \033[32m已新增帳號: {name}\033[0m")

    # 是否立刻登入
    login_now = input("  要立刻登入這個帳號嗎？(y/n): ").strip().lower()
    if login_now == "y":
        asyncio.run(login_single(account))


# ============================================================
# 刪除帳號
# ============================================================

def delete_account():
    from menu_ui import select_menu
    accounts = load_accounts()
    if not accounts:
        print("  目前沒有帳號\n")
        return

    options = [f"{a['name']} ({a['phone']})" for a in accounts] + ["取消"]
    idx = select_menu("選擇要刪除的帳號", options)

    if idx == -1 or idx == len(accounts):
        print("  已取消")
        return

    acc = accounts[idx]
    confirm = input(f"  確認刪除 {acc['name']} ({acc['phone']})？(y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return

    session_file = acc["session_name"] + ".session"
    if os.path.exists(session_file):
        os.remove(session_file)

    accounts.pop(idx)
    save_accounts(accounts)
    print(f"\n  \033[32m已刪除: {acc['name']}\033[0m")


# ============================================================
# 啟用/停用帳號
# ============================================================

def toggle_account():
    from menu_ui import select_menu
    accounts = load_accounts()
    if not accounts:
        print("  目前沒有帳號\n")
        return

    options = []
    for a in accounts:
        status = "啟用中" if a.get("enabled", True) else "已停用"
        options.append(f"{a['name']} [{status}]")
    options.append("取消")

    idx = select_menu("選擇要切換狀態的帳號", options)

    if idx == -1 or idx == len(accounts):
        return

    acc = accounts[idx]
    acc["enabled"] = not acc.get("enabled", True)
    save_accounts(accounts)
    status = "啟用" if acc["enabled"] else "停用"
    print(f"\n  \033[32m{acc['name']} 已設為: {status}\033[0m")


# ============================================================
# 登入帳號
# ============================================================

def make_proxy(proxy_conf):
    if not proxy_conf:
        return None
    import socks
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy_type = proxy_conf.get("type", "socks5").lower()
    proxy = (type_map.get(proxy_type, socks.SOCKS5), proxy_conf["host"], proxy_conf["port"])
    user = proxy_conf.get("username", "")
    pwd = proxy_conf.get("password", "")
    if user:
        proxy = proxy + (True, user, pwd)
    return proxy


async def login_single(account):
    from telethon import TelegramClient

    name = account["name"]
    proxy = make_proxy(account.get("proxy"))

    print(f"\n  登入 {name} ({account['phone']})...")
    try:
        client = TelegramClient(account["session_name"], account["api_id"], account["api_hash"], proxy=proxy)
        await client.start(phone=account["phone"])
        me = await client.get_me()
        print(f"  \033[32m登入成功: {me.first_name} (@{me.username}) [ID: {me.id}]\033[0m")
        await client.disconnect()
        return True
    except Exception as e:
        print(f"  \033[31m登入失敗: {e}\033[0m")
        return False


def login_menu():
    from menu_ui import select_menu
    accounts = load_accounts()
    if not accounts:
        print("  目前沒有帳號，請先新增\n")
        return

    choice = select_menu("登入帳號", [
        "登入所有未登入的帳號",
        "選擇特定帳號登入",
        "驗證所有帳號狀態",
    ])
    if choice == -1:
        return
    choice = str(choice + 1)

    os.makedirs(SESSIONS_DIR, exist_ok=True)

    if choice == "1":
        need_login = [a for a in accounts if not os.path.exists(a["session_name"] + ".session")]
        if not need_login:
            print("\n  所有帳號都已登入!")
            return
        print(f"\n  需要登入 {len(need_login)} 個帳號\n")
        for acc in need_login:
            asyncio.run(login_single(acc))

    elif choice == "2":
        show_accounts()
        num = input("  輸入帳號編號: ").strip()
        try:
            idx = int(num) - 1
            asyncio.run(login_single(accounts[idx]))
        except (ValueError, IndexError):
            print("  無效編號")

    elif choice == "3":
        print("\n  驗證所有帳號...\n")
        for acc in accounts:
            session_file = acc["session_name"] + ".session"
            if not os.path.exists(session_file):
                print(f"  ⚠ {acc['name']}: 未登入")
                continue
            asyncio.run(login_single(acc))


# ============================================================
# 快速批量新增
# ============================================================

def batch_add():
    header()
    print("  ── 快速批量新增帳號 ──\n")
    print("  每行輸入一組帳號資訊，格式:\n")
    print("  \033[33m電話號碼 API_ID API_HASH\033[0m\n")
    print("  範例:")
    print("  +886912345678 12345678 abcdef1234567890abcdef1234567890ab")
    print("  +886923456789 87654321 fedcba0987654321fedcba0987654321fe\n")
    print("  輸入完畢後輸入空行結束\n")

    accounts = load_accounts()
    new_accounts = []
    num = len(accounts) + 1

    while True:
        line = input(f"  帳號{num}: ").strip()
        if not line:
            break

        parts = line.split()
        if len(parts) < 3:
            print("    \033[31m格式錯誤，需要: 電話 API_ID API_HASH\033[0m")
            continue

        phone = parts[0]
        if not phone.startswith("+"):
            phone = "+886" + phone.lstrip("0")

        try:
            api_id = int(parts[1])
        except ValueError:
            print("    \033[31mAPI ID 必須是數字\033[0m")
            continue

        api_hash = parts[2]

        acc = {
            "name": f"帳號{num}",
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "session_name": f"sessions/session_{num:02d}",
            "proxy": None,
            "daily_limit": 25,
            "delay_min": 55 + num * 5,  # 每帳號不同延遲
            "delay_max": 150 + num * 10,
            "enabled": True,
        }
        new_accounts.append(acc)
        print(f"    \033[32m+ {acc['name']} {phone} API:{api_id}\033[0m")
        num += 1

    if not new_accounts:
        print("\n  未新增任何帳號")
        return

    print(f"\n  共 {len(new_accounts)} 個新帳號")
    confirm = input("  確認新增？(y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return

    accounts.extend(new_accounts)
    save_accounts(accounts)
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    print(f"\n  \033[32m已新增 {len(new_accounts)} 個帳號!\033[0m")

    login_now = input("  要立刻登入所有新帳號嗎？(y/n): ").strip().lower()
    if login_now == "y":
        for acc in new_accounts:
            asyncio.run(login_single(acc))


# ============================================================
# 主選單
# ============================================================

def main():
    from menu_ui import select_menu

    OPTIONS = [
        "查看所有帳號",
        "新增帳號（逐一填寫）",
        "快速批量新增（一次貼多個）",
        "刪除帳號",
        "啟用/停用帳號",
        "登入帳號",
        "返回主選單",
    ]
    ACTIONS = [
        lambda: (show_accounts(), input("  按 Enter 繼續...")),
        lambda: (add_account(), input("  按 Enter 繼續...")),
        lambda: (batch_add(), input("  按 Enter 繼續...")),
        lambda: (delete_account(), input("  按 Enter 繼續...")),
        lambda: (toggle_account(), input("  按 Enter 繼續...")),
        lambda: (login_menu(), input("  按 Enter 繼續...")),
        None,
    ]

    while True:
        idx = select_menu("帳號管理", OPTIONS)
        if idx == -1 or idx == len(OPTIONS) - 1:
            break
        if ACTIONS[idx]:
            ACTIONS[idx]()


if __name__ == "__main__":
    main()
