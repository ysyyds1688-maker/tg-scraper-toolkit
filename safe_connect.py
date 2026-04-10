"""
安全連線模組 — 完整隱身機制（審計修正版）

安全機制：
1. Proxy 熔斷：連不上就 os._exit(1)，絕不用本機 IP
2. DNS 防洩漏：強制所有 DNS 走 SOCKS5 代理（真正攔截）
3. 設備偽裝：每帳號獨立 device_model/system_version/lang_code
4. 環境偽裝：時區/語系設定為 Proxy 所在地
5. 禁止自動重連：Telethon 斷線不允許自動恢復（走熔斷）
6. Session 隔離：每帳號獨立 session 路徑
"""

import os
import sys
import random
import time
import socks
import socket
from telethon import TelegramClient
from telethon.errors import ConnectionError as TelethonConnectionError


# ============================================================
# 1. DNS 防洩漏：強制 DNS 走 SOCKS5
# ============================================================

_dns_patched = False


def enforce_dns_over_socks(proxy_conf):
    """
    強制所有 DNS 解析走 SOCKS5 代理
    設定 PySocks 的預設代理，讓 socket 層級的所有連線都走代理
    """
    global _dns_patched
    if not proxy_conf or _dns_patched:
        return

    proxy_type = proxy_conf.get("type", "socks5").lower()
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}

    # 設定全域預設代理（含 DNS）
    socks.set_default_proxy(
        proxy_type=type_map.get(proxy_type, socks.SOCKS5),
        addr=proxy_conf["host"],
        port=proxy_conf["port"],
        rdns=True,  # 關鍵：Remote DNS，DNS 解析由代理伺服器執行
        username=proxy_conf.get("username") or None,
        password=proxy_conf.get("password") or None,
    )

    # Monkey-patch socket，讓所有新的 socket 連線都走代理
    socket.socket = socks.socksocket

    _dns_patched = True
    print(f"    DNS 防洩漏: ✅ 所有 DNS 走 SOCKS5 (rdns=True)")


def restore_socket():
    """還原 socket（程式結束時呼叫）"""
    global _dns_patched
    if _dns_patched:
        socks.set_default_proxy()
        socket.socket = socks.socksocket.__bases__[0]
        _dns_patched = False


# ============================================================
# 2. 環境偽裝：時區 + 語系
# ============================================================

TIMEZONE_MAP = {
    "ja": {"tz": "Asia/Tokyo", "lang": "ja_JP.UTF-8"},
    "en": {"tz": "America/Los_Angeles", "lang": "en_US.UTF-8"},
    "ko": {"tz": "Asia/Seoul", "lang": "ko_KR.UTF-8"},
    "sg": {"tz": "Asia/Singapore", "lang": "en_SG.UTF-8"},
}


def set_environment(lang_code="en"):
    """設定環境變數偽裝時區和語系"""
    env = TIMEZONE_MAP.get(lang_code, TIMEZONE_MAP["en"])
    os.environ["TZ"] = env["tz"]
    os.environ["LANG"] = env["lang"]
    os.environ["LC_ALL"] = env["lang"]
    try:
        time.tzset()
    except AttributeError:
        pass  # Windows 沒有 tzset
    print(f"    環境偽裝: ✅ TZ={env['tz']} LANG={env['lang']}")


# ============================================================
# 3. 設備偽裝：每帳號獨立裝置資訊
# ============================================================

DEVICE_PROFILES = [
    {"device_model": "iPhone 15 Pro", "system_version": "iOS 17.4", "app_version": "10.9.3", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 14", "system_version": "iOS 17.2", "app_version": "10.8.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "iPhone 13", "system_version": "iOS 16.7", "app_version": "10.7.2", "lang_code": "ja", "system_lang_code": "ja-JP"},
    {"device_model": "Samsung Galaxy S24", "system_version": "Android 14", "app_version": "10.9.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Samsung Galaxy S23", "system_version": "Android 13", "app_version": "10.8.5", "lang_code": "ja", "system_lang_code": "ja-JP"},
    {"device_model": "Google Pixel 8", "system_version": "Android 14", "app_version": "10.9.1", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Google Pixel 7", "system_version": "Android 13", "app_version": "10.8.0", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "OnePlus 12", "system_version": "Android 14", "app_version": "10.9.2", "lang_code": "ja", "system_lang_code": "ja-JP"},
    {"device_model": "Desktop", "system_version": "Windows 11", "app_version": "4.16.8", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Desktop", "system_version": "Windows 10", "app_version": "4.15.2", "lang_code": "ja", "system_lang_code": "ja-JP"},
    {"device_model": "Desktop", "system_version": "macOS 14.4", "app_version": "10.9.3", "lang_code": "en", "system_lang_code": "en-US"},
    {"device_model": "Desktop", "system_version": "macOS 13.6", "app_version": "10.8.4", "lang_code": "ja", "system_lang_code": "ja-JP"},
]

_assigned_profiles = {}


def get_device_profile(api_id):
    """根據 api_id 固定分配裝置偽裝（每次一樣）"""
    if api_id not in _assigned_profiles:
        rng = random.Random(api_id)  # 獨立的 Random 實例，不影響全域
        _assigned_profiles[api_id] = rng.choice(DEVICE_PROFILES)
    return _assigned_profiles[api_id]


# ============================================================
# 4. Proxy 工具
# ============================================================

def make_proxy(proxy_conf):
    """轉換 proxy 設定為 Telethon 格式"""
    if not proxy_conf:
        return None
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy_type = proxy_conf.get("type", "socks5").lower()
    proxy = (
        type_map.get(proxy_type, socks.SOCKS5),
        proxy_conf["host"],
        proxy_conf["port"],
        True,   # rdns: Remote DNS
        proxy_conf.get("username") or None,
        proxy_conf.get("password") or None,
    )
    return proxy


# ============================================================
# 5. 安全連線（熔斷機制）
# ============================================================

async def safe_connect(account, max_retries=3):
    """
    安全連線 — 完整隱身

    規則：
    1. 帳號有 Proxy → 強制走 Proxy + DNS 防洩漏 + 環境偽裝
    2. Proxy 連不上 → os._exit(1) 強制閃退
    3. 帳號沒 Proxy → 直連（僅限測試/主帳號）
    4. 禁止 Telethon 自動重連（斷線走熔斷）
    5. 每帳號獨立設備偽裝
    """
    proxy_conf = account.get("proxy")
    proxy = make_proxy(proxy_conf)
    acc_name = account.get("name", "未知帳號")
    api_id = account.get("api_id")

    # 裝置偽裝
    profile = get_device_profile(api_id)

    if proxy_conf:
        print(f"  [{acc_name}] === 安全連線 ===")
        print(f"    Proxy: {proxy_conf['host']}:{proxy_conf['port']}")
        print(f"    裝置: {profile['device_model']} ({profile['system_version']})")
        print(f"    語系: {profile['system_lang_code']}")

        # 啟用 DNS 防洩漏
        enforce_dns_over_socks(proxy_conf)

        # 環境偽裝（時區+語系）
        set_environment(profile["lang_code"])

    else:
        print(f"  [{acc_name}] 直連模式（未設定 Proxy）")

    # 建立 Client
    client = TelegramClient(
        account["session_name"],
        api_id,
        account["api_hash"],
        proxy=proxy,
        device_model=profile["device_model"],
        system_version=profile["system_version"],
        app_version=profile["app_version"],
        lang_code=profile["lang_code"],
        system_lang_code=profile["system_lang_code"],
        connection_retries=0,     # 禁止自動重連
        retry_delay=0,            # 不等待重試
        auto_reconnect=False,     # 禁止自動重連（斷線走熔斷）
    )

    for attempt in range(1, max_retries + 1):
        try:
            await client.connect()

            if not await client.is_user_authorized():
                await client.start(phone=account.get("phone", ""))

            me = await client.get_me()
            print(f"  [{acc_name}] ✅ 登入成功: {me.first_name}")

            # 設定斷線回調（熔斷）
            if proxy_conf:
                @client.on_disconnect
                def on_disconnect():
                    print(f"\n  🚨 [{acc_name}] 連線中斷！啟動熔斷")
                    print(f"  🚨 強制終止，不允許重連")
                    os._exit(1)

            return client

        except (ConnectionError, OSError, TimeoutError, TelethonConnectionError) as e:
            print(f"  [{acc_name}] ❌ 連線失敗（{attempt}/{max_retries}）: {e}")

            if proxy_conf and attempt >= max_retries:
                print(f"\n  🚨🚨🚨 熔斷！{acc_name} Proxy 連線失敗 {max_retries} 次")
                print(f"  🚨 絕對不允許使用本機 IP")
                print(f"  🚨 強制終止進程")
                os._exit(1)

            if not proxy_conf and attempt >= max_retries:
                print(f"  [{acc_name}] 直連失敗")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                return None

        except Exception as e:
            print(f"  [{acc_name}] ❌ 未知錯誤: {e}")
            if proxy_conf:
                print(f"  🚨 熔斷！強制終止")
                os._exit(1)
            try:
                await client.disconnect()
            except Exception:
                pass
            return None

    return None
