"""
安全連線模組 — Proxy 熔斷機制
核心原則：設定了 Proxy 就必須走 Proxy，連不上就閃退，絕不用本機 IP
"""

import os
import sys
import socks
from telethon import TelegramClient


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


async def safe_connect(account, max_retries=3):
    """
    安全連線：Proxy 連不上就閃退，絕不用本機 IP

    規則：
    1. 帳號有設定 Proxy → 必須透過 Proxy 連線，失敗就閃退
    2. 帳號沒設定 Proxy → 直連（適用於測試或主帳號）

    回傳: TelegramClient（已連線）或 None（失敗）
    """
    proxy_conf = account.get("proxy")
    proxy = make_proxy(proxy_conf)
    acc_name = account.get("name", "未知帳號")

    if proxy_conf:
        print(f"  [{acc_name}] 透過 Proxy {proxy_conf['host']}:{proxy_conf['port']} 連線...")
    else:
        print(f"  [{acc_name}] 直連（未設定 Proxy）")

    client = TelegramClient(
        account["session_name"],
        account["api_id"],
        account["api_hash"],
        proxy=proxy,
    )

    for attempt in range(1, max_retries + 1):
        try:
            await client.connect()

            if not await client.is_user_authorized():
                await client.start(phone=account.get("phone", ""))

            me = await client.get_me()
            print(f"  [{acc_name}] ✅ 登入成功: {me.first_name}")
            return client

        except (ConnectionError, OSError, TimeoutError) as e:
            print(f"  [{acc_name}] ❌ 連線失敗（第 {attempt}/{max_retries} 次）: {e}")

            if proxy_conf:
                # === 熔斷機制 ===
                # 有設定 Proxy 但連不上，絕對不允許直連
                if attempt >= max_retries:
                    print(f"\n  🚨 熔斷！{acc_name} Proxy 連線失敗 {max_retries} 次")
                    print(f"  🚨 為保護安全，拒絕使用本機 IP 連線")
                    print(f"  🚨 請檢查 Proxy 設定後重試")
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    return None
            else:
                # 沒設定 Proxy，直連失敗可能是網路問題
                if attempt >= max_retries:
                    print(f"  [{acc_name}] 連線失敗，請檢查網路")
                    try:
                        await client.disconnect()
                    except Exception:
                        pass
                    return None

        except Exception as e:
            print(f"  [{acc_name}] ❌ 錯誤: {e}")
            try:
                await client.disconnect()
            except Exception:
                pass
            return None

    return None


def verify_proxy_ip(proxy_conf):
    """
    驗證 Proxy 是否正常（非同步前的快速檢查）
    回傳 True/False
    """
    if not proxy_conf:
        return True  # 沒設定 Proxy 跳過檢查

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((proxy_conf["host"], proxy_conf["port"]))
        s.close()
        return True
    except Exception:
        return False
