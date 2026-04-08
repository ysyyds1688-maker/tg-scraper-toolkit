"""
Telegram 擬人化私訊工具
功能：
  - 讀取 CSV 名單（支援多檔案合併）
  - 擬人化私訊（模擬打字、隨機延遲、模板輪換）
  - 斷點續傳（記錄已發送，重跑自動跳過）
  - 每日上限控制
  - 發送報告
"""

import asyncio
import csv
import os
import random
from datetime import datetime

from config import (
    API_ID, API_HASH, SESSION_NAME, PHONE,
    GROUP_INVITE_LINK, TOOLKIT_DIR,
    DM_MIN_DELAY, DM_MAX_DELAY, DM_TYPING_DELAY,
    DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX,
    DM_DAILY_LIMIT, DM_SENT_LOG, DM_CONTACT_FILES,
)
from messages import get_personalized_messages
from telethon import TelegramClient, functions, errors


# ============================================================
# 名單讀取
# ============================================================

def load_contacts(file_paths):
    """讀取多個 CSV 名單並合併去重"""
    all_contacts = []
    seen_ids = set()

    for fp in file_paths:
        if not os.path.exists(fp):
            print(f"  ⚠️  找不到: {fp}")
            continue
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # 過濾 bot
                    if row.get("is_bot", "").strip().lower() == "true":
                        continue

                    user_id = row.get("user_id", "").strip()
                    username = row.get("username", "").strip()
                    if username.startswith("@"):
                        username = username[1:]
                    phone = row.get("phone", "").strip()

                    if not user_id and not username and not phone:
                        continue

                    # 去重
                    ident = username or user_id or phone
                    if ident in seen_ids:
                        continue
                    seen_ids.add(ident)

                    # 組合名稱
                    first = row.get("first_name", "").strip()
                    last = row.get("last_name", "").strip()
                    name = f"{first} {last}".strip() or username or "朋友"

                    all_contacts.append({
                        "user_id": int(user_id) if user_id.isdigit() else None,
                        "username": username or None,
                        "phone": phone or None,
                        "name": name,
                    })
            print(f"  ✅ {os.path.basename(fp)}: {len(all_contacts)} 人（累計）")
        except Exception as e:
            print(f"  ❌ 讀取失敗 {fp}: {e}")

    return all_contacts


def load_sent_log():
    """讀取已發送記錄"""
    sent = set()
    if not os.path.exists(DM_SENT_LOG):
        return sent
    with open(DM_SENT_LOG, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ident = row.get("identifier", "")
            if ident:
                sent.add(ident)
    return sent


def get_identifier(contact):
    """取得唯一識別"""
    if contact["username"]:
        return f"username:{contact['username']}"
    if contact["user_id"]:
        return f"id:{contact['user_id']}"
    if contact["phone"]:
        return f"phone:{contact['phone']}"
    return None


def log_send(identifier, name, status, note=""):
    """記錄發送結果"""
    exists = os.path.exists(DM_SENT_LOG)
    with open(DM_SENT_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "identifier", "name", "status", "note"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            identifier, name, status, note,
        ])


# ============================================================
# 發送引擎
# ============================================================

async def resolve_user(client, contact):
    """解析用戶實體"""
    try:
        if contact["username"]:
            return await client.get_entity(contact["username"])
        if contact["user_id"]:
            return await client.get_entity(contact["user_id"])
        if contact["phone"]:
            result = await client(
                functions.contacts.ImportContactsRequest(
                    contacts=[functions.contacts.types.InputPhoneContact(
                        client_id=random.randint(0, 2**31),
                        phone=contact["phone"],
                        first_name=contact["name"], last_name="",
                    )]
                )
            )
            if result.users:
                return result.users[0]
    except errors.UsernameNotOccupiedError:
        print(f"    ❌ 用戶不存在: {contact.get('username')}")
    except errors.UsernameInvalidError:
        print(f"    ❌ 無效用戶名: {contact.get('username')}")
    except Exception as e:
        print(f"    ❌ 無法解析: {e}")
    return None


async def send_to_contact(client, contact):
    """對一個聯絡人發送擬人化訊息"""
    identifier = get_identifier(contact)
    name = contact["name"]
    print(f"\n  📨 {name} ({identifier})")

    user = await resolve_user(client, contact)
    if not user:
        log_send(identifier, name, "failed", "無法解析用戶")
        return False

    messages = get_personalized_messages(name, GROUP_INVITE_LINK)

    try:
        for i, msg in enumerate(messages):
            # 模擬打字
            async with client.action(user, "typing"):
                typing_time = max(DM_TYPING_DELAY, len(msg) * 0.05)
                await asyncio.sleep(typing_time)

            await client.send_message(user, msg)
            print(f"    ✉️  第 {i+1}/{len(messages)} 段")

            if i < len(messages) - 1:
                delay = random.uniform(DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX)
                await asyncio.sleep(delay)

        log_send(identifier, name, "success", f"{len(messages)} 段")
        print(f"    ✅ 成功!")
        return True

    except errors.FloodWaitError as e:
        print(f"    ⚠️  限流 {e.seconds}s...")
        log_send(identifier, name, "flood_wait", f"{e.seconds}s")
        await asyncio.sleep(e.seconds + 10)
        return False

    except errors.UserPrivacyRestrictedError:
        print(f"    🔒 隱私限制")
        log_send(identifier, name, "privacy_blocked")
        return False

    except errors.PeerFloodError:
        print(f"    🚫 帳號被限制，建議暫停")
        log_send(identifier, name, "peer_flood")
        return False

    except Exception as e:
        print(f"    ❌ 失敗: {e}")
        log_send(identifier, name, "error", str(e))
        return False


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  Telegram 擬人化私訊工具")
    print("=" * 55)

    # 讀取名單
    print(f"\n📋 讀取名單...")
    contacts = load_contacts(DM_CONTACT_FILES)
    if not contacts:
        print("❌ 名單為空")
        return

    # 統計
    with_un = len([c for c in contacts if c["username"]])
    only_id = len([c for c in contacts if not c["username"] and c["user_id"]])
    print(f"\n  共 {len(contacts)} 人 (有username: {with_un}, 只有ID: {only_id})")

    # 讀取已發送
    sent_set = load_sent_log()
    if sent_set:
        print(f"  已發送: {len(sent_set)} 人（跳過）")

    to_send = len(contacts) - len(sent_set)
    actual = min(max(to_send, 0), DM_DAILY_LIMIT)

    print(f"\n📊 本次發送: {actual} 人")
    print(f"   每日上限: {DM_DAILY_LIMIT}")
    print(f"   間隔: {DM_MIN_DELAY}-{DM_MAX_DELAY}s")
    print(f"   群組連結: {GROUP_INVITE_LINK}")

    confirm = input("\n確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return

    # 登入
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start(phone=PHONE)
    me = await client.get_me()
    print(f"\n✅ 登入: {me.first_name} (@{me.username})\n")

    sent_count = 0
    success = 0
    fail = 0

    try:
        for contact in contacts:
            if sent_count >= DM_DAILY_LIMIT:
                print(f"\n🛑 達到每日上限 {DM_DAILY_LIMIT}")
                break

            ident = get_identifier(contact)
            if ident in sent_set:
                continue

            sent_count += 1
            print(f"\n--- [{sent_count}/{actual}] ---")
            ok = await send_to_contact(client, contact)
            if ok:
                success += 1
            else:
                fail += 1

            if sent_count < DM_DAILY_LIMIT:
                delay = random.uniform(DM_MIN_DELAY, DM_MAX_DELAY)
                print(f"    ⏳ 等待 {delay:.0f}s...")
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        print("\n\n⚠️  中斷，進度已保存")
    finally:
        await client.disconnect()

    print(f"\n{'='*50}")
    print(f"📊 統計:")
    print(f"   處理: {sent_count}")
    print(f"   成功: {success}")
    print(f"   失敗: {fail}")
    print(f"   記錄: {DM_SENT_LOG}")
    print("完成!")


if __name__ == "__main__":
    asyncio.run(main())
