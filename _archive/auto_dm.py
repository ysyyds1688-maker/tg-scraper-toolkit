"""
自動私訊腳本 - 讀取 CSV 中的用戶，逐一發送私訊
"""

import asyncio
import csv
import os
import random
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    PeerFloodError,
    UserBannedInChannelError,
    InputUserDeactivatedError,
    UserNotMutualContactError,
)

# ============================================================
# 設定區 - 修改這裡
# ============================================================

# 訊息內容（多個版本，隨機選一個發送，降低被偵測風險）
# 支援 {first_name} 變數，會自動替換成對方名字
MESSAGES = [
    "哈囉 {first_name}，你好！",
    # 加更多版本：
    # "嗨 {first_name}，想認識一下～",
    # "Hi {first_name}，交個朋友吧！",
]

# 每則訊息間隔（秒）- 隨機範圍，建議不要太短
MIN_DELAY = 30   # 最短間隔
MAX_DELAY = 60   # 最長間隔

# 每日發送上限（超過就停止，保護帳號）
DAILY_LIMIT = 30

# 是否跳過沒有 username 的用戶
SKIP_NO_USERNAME = True

# 發送記錄檔（避免重複發送）
SENT_LOG = "dm_sent_log.csv"

# ============================================================


def load_sent_log():
    """載入已發送記錄"""
    sent = set()
    if os.path.exists(SENT_LOG):
        with open(SENT_LOG, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if row:
                    sent.add(row[0])  # user_id
    return sent


def save_sent_record(user_id, username, first_name, status, message):
    """記錄發送結果"""
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["user_id", "username", "first_name", "status", "message", "time"])
        writer.writerow([
            user_id, username, first_name, status, message,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


def load_targets(csv_path, source_filter=None):
    """從 CSV 載入目標用戶，可選按來源群組篩選"""
    targets = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 來源群組篩選
            if source_filter:
                source = row.get("source_group", "")
                if not any(kw in source for kw in source_filter):
                    continue
            targets.append({
                "user_id": row.get("user_id", ""),
                "username": row.get("username", ""),
                "first_name": row.get("first_name", ""),
                "last_name": row.get("last_name", ""),
                "source_group": row.get("source_group", ""),
            })
    return targets


def pick_message(first_name):
    """隨機選一則訊息並填入名字"""
    msg = random.choice(MESSAGES)
    name = first_name if first_name else "你好"
    return msg.replace("{first_name}", name)


async def main():
    if len(MESSAGES) == 0 or MESSAGES[0].strip() == "":
        print("請先在腳本中設定 MESSAGES 訊息內容！")
        return

    # 預設讀取 all_members.csv
    default_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "all_members.csv")

    if os.path.exists(default_csv):
        csv_path = default_csv
        print(f"使用名單: all_members.csv")
    else:
        # 找不到預設檔案，手動選擇
        csv_files = [f for f in os.listdir(".") if f.endswith(".csv") and f != SENT_LOG]
        if not csv_files:
            print("找不到任何 CSV 檔案！請先執行 [7] 合併去重")
            return
        print("可用的 CSV 檔案：")
        for i, f in enumerate(csv_files, 1):
            print(f"  [{i}] {f}")
        print()
        choice = input("選擇 CSV 檔案編號: ").strip()
        try:
            csv_path = csv_files[int(choice) - 1]
        except (ValueError, IndexError):
            print("無效選擇")
        return

    # 來源群組篩選
    print(f"\n篩選目標用戶：")
    print(f"  [1] 全部用戶")
    print(f"  [2] 只發成人/外送茶相關群組的用戶")
    print(f"  [3] 自訂關鍵字篩選")
    filter_mode = input("\n選擇 (1/2/3): ").strip()

    source_filter = None
    if filter_mode == "2":
        source_filter = [
            "大神", "極樂", "貝兒", "娜娜", "亞曼尼", "18禁",
            "免費影片", "福利", "深夜", "外送", "茶", "約",
            "步兵", "成人", "交友", "含碧樓",
        ]
        print(f"  篩選關鍵字: {', '.join(source_filter)}")
    elif filter_mode == "3":
        kw_input = input("  輸入關鍵字（逗號分隔）: ").strip()
        if kw_input:
            source_filter = [k.strip() for k in kw_input.split(",")]
            print(f"  篩選關鍵字: {', '.join(source_filter)}")

    # 載入目標
    targets = load_targets(csv_path, source_filter=source_filter)
    sent_log = load_sent_log()

    # 過濾
    filtered = []
    for t in targets:
        uid = t["user_id"]
        if uid in sent_log:
            continue
        if SKIP_NO_USERNAME and not t["username"]:
            continue
        filtered.append(t)

    print(f"\nCSV 共 {len(targets)} 位用戶")
    print(f"已發送過: {len(sent_log)} 位")
    print(f"無 username 跳過: {len([t for t in targets if not t['username'] and t['user_id'] not in sent_log])} 位")
    print(f"待發送: {len(filtered)} 位")
    print(f"今日上限: {DAILY_LIMIT} 位")
    print(f"訊息版本: {len(MESSAGES)} 個")
    print(f"間隔: {MIN_DELAY}-{MAX_DELAY} 秒")
    print()

    if not filtered:
        print("沒有需要發送的目標")
        return

    actual = min(len(filtered), DAILY_LIMIT)
    confirm = input(f"確認要發送給 {actual} 位用戶？(y/n): ").strip().lower()
    if confirm != "y":
        print("取消")
        return

    # 開始發送
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    success = 0
    fail = 0
    skip = 0

    for i, target in enumerate(filtered[:DAILY_LIMIT]):
        username = target["username"]
        first_name = target["first_name"]
        user_id = target["user_id"]
        msg = pick_message(first_name)

        print(f"\n  [{i+1}/{actual}] @{username} ({first_name})")
        print(f"    訊息: {msg[:50]}...")

        try:
            # 優先用 username 發送，沒有就用 user_id
            recipient = username if username else int(user_id)
            await client.send_message(recipient, msg)
            print(f"    ✓ 發送成功")
            save_sent_record(user_id, username, first_name, "success", msg)
            success += 1

        except PeerFloodError:
            print(f"    ✗ 被限速 (PeerFloodError)！建議停止，明天再繼續")
            save_sent_record(user_id, username, first_name, "flood", msg)
            print("\n⚠️  帳號被限速，自動停止以保護帳號")
            break

        except FloodWaitError as e:
            wait = e.seconds
            print(f"    ⏳ FloodWait，等待 {wait} 秒...")
            save_sent_record(user_id, username, first_name, "flood_wait", msg)
            if wait > 300:
                print("    等待時間太長，建議明天再繼續")
                break
            await asyncio.sleep(wait)
            # 重試一次
            try:
                recipient = username if username else int(user_id)
                await client.send_message(recipient, msg)
                print(f"    ✓ 重試成功")
                save_sent_record(user_id, username, first_name, "success_retry", msg)
                success += 1
            except Exception as e2:
                print(f"    ✗ 重試失敗: {e2}")
                fail += 1

        except UserPrivacyRestrictedError:
            print(f"    ✗ 對方隱私設定不允許")
            save_sent_record(user_id, username, first_name, "privacy", msg)
            skip += 1

        except InputUserDeactivatedError:
            print(f"    ✗ 帳號已停用")
            save_sent_record(user_id, username, first_name, "deactivated", msg)
            skip += 1

        except UserNotMutualContactError:
            print(f"    ✗ 非互相聯絡人，無法發送")
            save_sent_record(user_id, username, first_name, "not_mutual", msg)
            skip += 1

        except Exception as e:
            print(f"    ✗ 失敗: {e}")
            save_sent_record(user_id, username, first_name, f"error: {e}", msg)
            fail += 1

        # 隨機等待
        if i < actual - 1:
            delay = random.randint(MIN_DELAY, MAX_DELAY)
            print(f"    等待 {delay} 秒...")
            await asyncio.sleep(delay)

    await client.disconnect()

    print(f"\n{'='*50}")
    print(f"發送完成！")
    print(f"  成功: {success}")
    print(f"  失敗: {fail}")
    print(f"  跳過: {skip}")
    print(f"  記錄: {SENT_LOG}")


if __name__ == "__main__":
    asyncio.run(main())
