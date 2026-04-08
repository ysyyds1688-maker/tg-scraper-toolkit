"""
多帳號輪流自動私訊
- 支援多個 Telegram 帳號，各自獨立 session
- 自動輪流切換帳號
- 每帳號獨立限額、獨立發送記錄
- 支援排程模式（持續運行，每天重設額度）
"""

import asyncio
import csv
import os
import random
import sys
import json
from datetime import datetime, timedelta

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    PeerFloodError,
    UserBannedInChannelError,
    InputUserDeactivatedError,
    UserNotMutualContactError,
    AuthKeyUnregisteredError,
)

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 帳號設定
# ============================================================
ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")

# 如果 accounts.json 不存在，自動建立範例
if not os.path.exists(ACCOUNTS_FILE):
    example = {
        "accounts": [
            {
                "name": "帳號1",
                "api_id": 0,
                "api_hash": "",
                "session_name": "session_account1",
                "daily_limit": 30,
                "enabled": True,
            },
            {
                "name": "帳號2",
                "api_id": 0,
                "api_hash": "",
                "session_name": "session_account2",
                "daily_limit": 30,
                "enabled": True,
            },
        ],
        "messages": [
            "哈囉 {first_name}，你好！",
        ],
        "min_delay": 30,
        "max_delay": 60,
        "skip_no_username": True,
        "source_filter": [],
    }
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
    print(f"已建立 accounts.json 範例檔，請先編輯設定帳號資訊！")
    print(f"路徑: {ACCOUNTS_FILE}")
    sys.exit(0)

# ============================================================
# 載入設定
# ============================================================
with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

ACCOUNTS = [a for a in CONFIG["accounts"] if a.get("enabled", True)]
MESSAGES = CONFIG.get("messages", [])
MIN_DELAY = CONFIG.get("min_delay", 30)
MAX_DELAY = CONFIG.get("max_delay", 60)
SKIP_NO_USERNAME = CONFIG.get("skip_no_username", True)
SOURCE_FILTER = CONFIG.get("source_filter", [])

# 發送記錄
SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
STATE_FILE = os.path.join(TOOLKIT_DIR, "dm_state.json")


def load_sent_log():
    """載入已發送記錄"""
    sent = set()
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if row:
                    sent.add(row[0])
    return sent


def save_sent_record(user_id, username, first_name, status, message, account_name):
    """記錄發送結果"""
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["user_id", "username", "first_name", "status", "message", "account", "time"])
        writer.writerow([
            user_id, username, first_name, status, message, account_name,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


def load_state():
    """載入每帳號的今日發送狀態"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
        # 檢查是否過了一天，重設計數
        today = datetime.now().strftime("%Y-%m-%d")
        if state.get("date") != today:
            state = {"date": today, "accounts": {}}
        return state
    return {"date": datetime.now().strftime("%Y-%m-%d"), "accounts": {}}


def save_state(state):
    """儲存狀態"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_targets(csv_path, source_filter=None):
    """載入目標用戶"""
    targets = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if source_filter:
                source = row.get("source_group", "")
                if not any(kw in source for kw in source_filter):
                    continue
            targets.append({
                "user_id": row.get("user_id", ""),
                "username": row.get("username", ""),
                "first_name": row.get("first_name", ""),
            })
    return targets


def pick_message(first_name):
    """隨機選訊息"""
    msg = random.choice(MESSAGES)
    name = first_name if first_name else "你好"
    return msg.replace("{first_name}", name)


async def send_with_account(account, targets, sent_log, state):
    """用一個帳號發送私訊"""
    name = account["name"]
    api_id = account["api_id"]
    api_hash = account["api_hash"]
    session = account["session_name"]
    daily_limit = account.get("daily_limit", 30)

    # 今日已發送數
    today_sent = state["accounts"].get(name, 0)
    remaining = daily_limit - today_sent

    if remaining <= 0:
        print(f"  [{name}] 今日已達上限 ({daily_limit})")
        return 0, False

    print(f"\n  [{name}] 連線中...")
    try:
        client = TelegramClient(
            os.path.join(TOOLKIT_DIR, session),
            api_id, api_hash
        )
        await client.start()
    except AuthKeyUnregisteredError:
        print(f"  [{name}] Session 失效，需要重新登入")
        return 0, False
    except Exception as e:
        print(f"  [{name}] 連線失敗: {type(e).__name__}")
        return 0, False

    me = await client.get_me()
    print(f"  [{name}] 登入成功: {me.first_name} ({me.phone})")
    print(f"  [{name}] 今日已發 {today_sent}/{daily_limit}，剩餘 {remaining}")

    sent_count = 0
    flood_hit = False

    for target in targets:
        if remaining <= 0:
            print(f"  [{name}] 達到今日上限")
            break

        uid = target["user_id"]
        username = target["username"]
        first_name = target["first_name"]

        if uid in sent_log:
            continue
        if SKIP_NO_USERNAME and not username:
            continue

        # 發送
        message = pick_message(first_name)
        try:
            if username:
                user = await client.get_entity(username)
            else:
                user = await client.get_entity(int(uid))

            await client.send_message(user, message)
            print(f"  [{name}] ✓ @{username or uid} — {message[:30]}...")
            save_sent_record(uid, username, first_name, "sent", message, name)
            sent_log.add(uid)
            sent_count += 1
            remaining -= 1
            state["accounts"][name] = today_sent + sent_count
            save_state(state)

        except FloodWaitError as e:
            print(f"  [{name}] ⚠ 限速 {e.seconds} 秒！停止此帳號")
            flood_hit = True
            break
        except PeerFloodError:
            print(f"  [{name}] ⚠ PeerFlood！停止此帳號")
            flood_hit = True
            break
        except UserPrivacyRestrictedError:
            print(f"  [{name}] ✗ @{username} 隱私限制，跳過")
            save_sent_record(uid, username, first_name, "privacy", "", name)
            sent_log.add(uid)
        except InputUserDeactivatedError:
            print(f"  [{name}] ✗ @{username} 帳號已停用")
            save_sent_record(uid, username, first_name, "deactivated", "", name)
            sent_log.add(uid)
        except UserNotMutualContactError:
            print(f"  [{name}] ✗ @{username} 非互相聯絡人")
            save_sent_record(uid, username, first_name, "not_mutual", "", name)
            sent_log.add(uid)
        except Exception as e:
            print(f"  [{name}] ✗ @{username} 失敗: {type(e).__name__}")
            save_sent_record(uid, username, first_name, f"error:{type(e).__name__}", "", name)

        # 隨機延遲
        delay = random.randint(MIN_DELAY, MAX_DELAY)
        await asyncio.sleep(delay)

    await client.disconnect()
    print(f"  [{name}] 本輪發送 {sent_count} 則")
    return sent_count, flood_hit


async def main():
    print("=" * 55)
    print("  多帳號輪流自動私訊")
    print("=" * 55)

    if not MESSAGES or MESSAGES[0].strip() == "" or MESSAGES[0] == "哈囉 {first_name}，你好！":
        print("\n⚠ 請先編輯 accounts.json 設定正式的訊息內容！")
        print(f"  路徑: {ACCOUNTS_FILE}")
        return

    if not ACCOUNTS:
        print("\n⚠ 沒有啟用的帳號！請編輯 accounts.json")
        return

    # 載入名單
    csv_path = os.path.join(TOOLKIT_DIR, "members_with_username.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join(TOOLKIT_DIR, "all_members.csv")
    if not os.path.exists(csv_path):
        print("找不到成員名單！請先執行 [7] 合併去重")
        return

    targets = load_targets(csv_path, SOURCE_FILTER if SOURCE_FILTER else None)
    sent_log = load_sent_log()
    state = load_state()

    # 過濾已發送
    pending = [t for t in targets if t["user_id"] not in sent_log]
    if SKIP_NO_USERNAME:
        pending = [t for t in pending if t["username"]]

    print(f"\n設定：")
    print(f"  帳號數: {len(ACCOUNTS)}")
    print(f"  訊息版本: {len(MESSAGES)} 個")
    print(f"  間隔: {MIN_DELAY}-{MAX_DELAY} 秒")
    if SOURCE_FILTER:
        print(f"  篩選: {', '.join(SOURCE_FILTER)}")
    print(f"\n名單：")
    print(f"  總目標: {len(targets)} 位")
    print(f"  已發送: {len(sent_log)} 位")
    print(f"  待發送: {len(pending)} 位")

    print(f"\n帳號狀態：")
    for acc in ACCOUNTS:
        today_sent = state["accounts"].get(acc["name"], 0)
        limit = acc.get("daily_limit", 30)
        remaining = limit - today_sent
        status = f"剩 {remaining}" if remaining > 0 else "已滿"
        print(f"  {acc['name']}: 今日 {today_sent}/{limit} ({status})")

    # 模式選擇
    print(f"\n模式：")
    print(f"  [1] 跑一輪（每帳號發到上限為止）")
    print(f"  [2] 持續模式（每天自動重設，持續發送）")
    mode = input("\n選擇 (1/2): ").strip()

    if mode == "2":
        print("\n持續模式啟動！按 Ctrl+C 停止")
        print("每天 0:00 自動重設額度\n")

        while True:
            state = load_state()
            total_sent = 0

            # 打亂帳號順序
            accounts_shuffled = ACCOUNTS.copy()
            random.shuffle(accounts_shuffled)

            for acc in accounts_shuffled:
                random.shuffle(pending)
                count, flood = await send_with_account(acc, pending, sent_log, state)
                total_sent += count

                if flood:
                    # 被限速的帳號，等一下再繼續下一個
                    await asyncio.sleep(60)

                # 帳號之間休息
                await asyncio.sleep(random.randint(30, 60))

            # 檢查是否所有帳號都用完今日額度
            all_done = True
            for acc in ACCOUNTS:
                today_sent = state["accounts"].get(acc["name"], 0)
                if today_sent < acc.get("daily_limit", 30):
                    all_done = False

            if all_done:
                # 計算到明天 0:00 的等待時間
                now = datetime.now()
                tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0)
                wait_seconds = (tomorrow - now).total_seconds()
                print(f"\n所有帳號今日額度用完！")
                print(f"等待到明天 0:05 重新開始... ({int(wait_seconds/3600)} 小時)")
                await asyncio.sleep(wait_seconds)
                # 重新載入
                pending = [t for t in targets if t["user_id"] not in sent_log]
                if SKIP_NO_USERNAME:
                    pending = [t for t in pending if t["username"]]
            else:
                # 還有額度但所有帳號都被限速，等一下再試
                await asyncio.sleep(300)

    else:
        # 單輪模式
        confirm = input(f"\n開始發送？(y/n): ").strip().lower()
        if confirm != "y":
            return

        total_sent = 0
        accounts_shuffled = ACCOUNTS.copy()
        random.shuffle(accounts_shuffled)

        for acc in accounts_shuffled:
            random.shuffle(pending)
            count, flood = await send_with_account(acc, pending, sent_log, state)
            total_sent += count

            if flood:
                await asyncio.sleep(60)
            await asyncio.sleep(random.randint(30, 60))

        print(f"\n{'='*55}")
        print(f"完成！本輪共發送 {total_sent} 則")
        print(f"發送記錄: {SENT_LOG}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n已停止")
