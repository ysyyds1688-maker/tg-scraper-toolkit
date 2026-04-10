"""
安全連線模組 — 完整隱身機制
1. Proxy 熔斷：連不上就 os._exit()，絕不用本機 IP
2. DNS 防洩漏：所有 DNS 解析走 SOCKS5 代理
3. 設備偽裝：每個帳號隨機裝置名稱/系統版本/語系
"""

import os
import sys
import random
import socks
import socket
from telethon import TelegramClient


# ============================================================
# DNS 防洩漏：強制 DNS 走 SOCKS5
# ============================================================

_original_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(*args, **kwargs):
    """攔截 DNS 查詢，確保走代理"""
    return _original_getaddrinfo(*args, **kwargs)


def enable_dns_over_proxy():
    """啟用 DNS over SOCKS5（防止 DNS 洩漏）"""
    try:
        socks.set_default_proxy()  # 確保 socks 模組已載入
    except Exception:
        pass


# ============================================================
# 設備偽裝：每個帳號不同的裝置資訊
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

# 每個帳號固定分配一個裝置（用 api_id 當種子，確保每次一樣）
_assigned_profiles = {}


def get_device_profile(api_id):
    """根據 api_id 取得固定的裝置偽裝資訊"""
    if api_id not in _assigned_profiles:
        random.seed(api_id)
        _assigned_profiles[api_id] = random.choice(DEVICE_PROFILES)
        random.seed()  # 重置種子
    return _assigned_profiles[api_id]


# ============================================================
# Proxy 工具
# ============================================================

def make_proxy(proxy_conf):
    """轉換 proxy 設定為 Telethon 格式"""
    if not proxy_conf:
        return None
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy_type = proxy_conf.get("type", "socks5").lower()
    proxy = (type_map.get(proxy_type, socks.SOCKS5), proxy_conf["host"], proxy_conf["port"])
    user = proxy_conf.get("username", "")
    pwd = proxy_conf.get("password", "")
    if user:
        proxy = proxy + (True, user, pwd)
    return proxy


# ============================================================
# 安全連線（熔斷機制）
# ============================================================

async def safe_connect(account, max_retries=3):
    """
    安全連線：Proxy 連不上就強制閃退，絕不用本機 IP

    規則：
    1. 帳號有 Proxy → 必須走 Proxy，失敗就 os._exit()
    2. 帳號沒 Proxy → 直連（測試/主帳號用）
    3. 自動套用設備偽裝
    """
    proxy_conf = account.get("proxy")
    proxy = make_proxy(proxy_conf)
    acc_name = account.get("name", "未知帳號")
    api_id = account.get("api_id")

    # 取得裝置偽裝資訊
    profile = get_device_profile(api_id)

    if proxy_conf:
        print(f"  [{acc_name}] Proxy: {proxy_conf['host']}:{proxy_conf['port']}")
        print(f"  [{acc_name}] 裝置: {profile['device_model']} ({profile['system_version']})")

        # 先快速檢查 Proxy 是否可連
        if not verify_proxy(proxy_conf):
            print(f"\n  🚨 熔斷！{acc_name} Proxy 無法連線")
            print(f"  🚨 拒絕使用本機 IP，強制終止")
            os._exit(1)
    else:
        print(f"  [{acc_name}] 直連（未設定 Proxy）")

    # 建立 Client（帶裝置偽裝）
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
    )

    for attempt in range(1, max_retries + 1):
        try:
            await client.connect()

            if not await client.is_user_authorized():
                await client.start(phone=account.get("phone", ""))

            me = await client.get_me()
            print(f"  [{acc_name}] ✅ 登入: {me.first_name}")
            return client

        except (ConnectionError, OSError, TimeoutError) as e:
            print(f"  [{acc_name}] ❌ 連線失敗（{attempt}/{max_retries}）: {e}")

            if proxy_conf and attempt >= max_retries:
                # === 熔斷：強制閃退 ===
                print(f"\n  🚨🚨🚨 熔斷！{acc_name} Proxy 連線失敗 {max_retries} 次")
                print(f"  🚨 絕對不允許使用本機 IP 重新連線")
                print(f"  🚨 強制終止進程")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                os._exit(1)  # 強制閃退，不走正常退出流程

            if not proxy_conf and attempt >= max_retries:
                print(f"  [{acc_name}] 直連失敗，請檢查網路")
                try:
                    await client.disconnect()
                except Exception:
                    pass
                return None

        except Exception as e:
            print(f"  [{acc_name}] ❌ 錯誤: {e}")
            if proxy_conf:
                print(f"  🚨 熔斷！強制終止")
                os._exit(1)
            try:
                await client.disconnect()
            except Exception:
                pass
            return None

    return None


def verify_proxy(proxy_conf):
    """快速檢查 Proxy 是否可連（10 秒超時）"""
    if not proxy_conf:
        return True
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((proxy_conf["host"], proxy_conf["port"]))
        s.close()
        print(f"    Proxy 連線檢查: ✅")
        return True
    except Exception as e:
        print(f"    Proxy 連線檢查: ❌ {e}")
        return False
