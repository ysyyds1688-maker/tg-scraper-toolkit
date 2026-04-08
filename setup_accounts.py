"""
帳號批量登入工具
逐一登入 accounts.json 中的所有帳號，產生 session 檔案
每個帳號使用獨立的 API_ID/HASH 和代理 IP
"""

import asyncio
import json
import os
import sys

from telethon import TelegramClient
import socks

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SESSIONS_DIR = os.path.join(TOOLKIT_DIR, "sessions")


def load_accounts():
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["accounts"]


def make_proxy(proxy_conf):
    """轉換 proxy 設定為 Telethon 格式"""
    if not proxy_conf:
        return None

    proxy_type = proxy_conf.get("type", "socks5").lower()
    type_map = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }

    proxy = (
        type_map.get(proxy_type, socks.SOCKS5),
        proxy_conf["host"],
        proxy_conf["port"],
    )

    # 如果有帳密
    user = proxy_conf.get("username", "")
    pwd = proxy_conf.get("password", "")
    if user:
        proxy = proxy + (True, user, pwd)

    return proxy


async def login_account(account):
    """登入單一帳號"""
    name = account["name"]
    phone = account["phone"]
    api_id = account["api_id"]
    api_hash = account["api_hash"]
    session_name = account["session_name"]
    proxy = make_proxy(account.get("proxy"))

    print(f"\n{'='*50}")
    print(f"登入: {name} ({phone})")
    if proxy:
        print(f"代理: {account['proxy']['host']}:{account['proxy']['port']}")
    else:
        print(f"代理: 無（直連）")

    try:
        client = TelegramClient(session_name, api_id, api_hash, proxy=proxy)
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"✅ 成功: {me.first_name} (@{me.username}) [ID: {me.id}]")
        await client.disconnect()
        return True
    except Exception as e:
        print(f"❌ 失敗: {e}")
        return False


async def main():
    print("=" * 55)
    print("  帳號批量登入工具")
    print("=" * 55)

    if not os.path.exists(ACCOUNTS_FILE):
        print(f"\n❌ 找不到 {ACCOUNTS_FILE}")
        print("   請先填寫帳號資訊")
        return

    accounts = load_accounts()
    print(f"\n共 {len(accounts)} 個帳號")

    # 建立 sessions 資料夾
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    # 檢查哪些已登入
    already = []
    need_login = []
    for acc in accounts:
        if not acc.get("enabled", True):
            print(f"  ⏭ {acc['name']} - 已停用")
            continue
        session_file = acc["session_name"] + ".session"
        if os.path.exists(session_file):
            already.append(acc)
        else:
            need_login.append(acc)

    if already:
        print(f"\n已登入: {len(already)} 個")
        for a in already:
            print(f"  ✅ {a['name']}")

    if not need_login:
        print("\n所有帳號都已登入!")

        # 驗證所有帳號
        verify = input("\n要驗證所有帳號是否正常？(y/n): ").strip().lower()
        if verify == "y":
            for acc in already:
                proxy = make_proxy(acc.get("proxy"))
                try:
                    client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
                    await client.start()
                    me = await client.get_me()
                    print(f"  ✅ {acc['name']}: {me.first_name} [ID: {me.id}]")
                    await client.disconnect()
                except Exception as e:
                    print(f"  ❌ {acc['name']}: {e}")
        return

    print(f"\n需要登入: {len(need_login)} 個")
    for a in need_login:
        print(f"  🔑 {a['name']} ({a['phone']})")

    confirm = input(f"\n開始逐一登入？(y/n): ").strip().lower()
    if confirm != "y":
        return

    success = 0
    fail = 0
    for acc in need_login:
        ok = await login_account(acc)
        if ok:
            success += 1
        else:
            fail += 1

    print(f"\n{'='*50}")
    print(f"登入結果:")
    print(f"  成功: {success}")
    print(f"  失敗: {fail}")
    print(f"  Session 位置: {SESSIONS_DIR}/")


if __name__ == "__main__":
    asyncio.run(main())
