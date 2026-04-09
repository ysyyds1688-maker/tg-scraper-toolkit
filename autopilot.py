"""
全自動模式 — 一鍵啟動所有功能
不需要手動操作，設定一次後自動運行：
  1. Bot 客服（背景持續運行）
  2. 內容轉發（即時監聽，24 小時）
  3. 多帳號私訊（每天自動跑）
  4. 撈名單（每週自動跑）
"""

import asyncio
import csv
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)
os.environ["PYTHONPATH"] = TOOLKIT_DIR

from config import (
    API_ID, API_HASH, SESSION_NAME, TOOLKIT_DIR, DATA_DIR,
    GROUP_INVITE_LINK, DM_TYPING_DELAY, DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX,
)
from telethon import TelegramClient, events, errors
from messages import get_personalized_messages
import socks


ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
STATE_FILE = os.path.join(TOOLKIT_DIR, "dm_state.json")
AUTOPILOT_LOG = os.path.join(TOOLKIT_DIR, "autopilot.log")


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(AUTOPILOT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# 帳號/名單/狀態 載入
# ============================================================

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [a for a in data.get("accounts", []) if a.get("enabled", True)]


def make_proxy(proxy_conf):
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


def load_contacts():
    from config import DM_CONTACT_FILES
    contacts = []
    seen = set()
    for fp in DM_CONTACT_FILES:
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("is_bot", "").strip().lower() == "true":
                        continue
                    uid = row.get("user_id", "").strip()
                    username = row.get("username", "").strip().lstrip("@")
                    if not uid and not username:
                        continue
                    ident = username or uid
                    if ident in seen:
                        continue
                    seen.add(ident)
                    first = row.get("first_name", "").strip()
                    last = row.get("last_name", "").strip()
                    name = f"{first} {last}".strip() or username or "朋友"
                    contacts.append({
                        "user_id": int(uid) if uid.isdigit() else None,
                        "username": username or None,
                        "name": name,
                    })
        except Exception:
            continue
    return contacts


def load_sent_log():
    sent = set()
    if not os.path.exists(SENT_LOG):
        return sent
    with open(SENT_LOG, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ident = row.get("identifier", "")
            if ident:
                sent.add(ident)
    return sent


def get_identifier(contact):
    if contact["username"]:
        return f"username:{contact['username']}"
    if contact["user_id"]:
        return f"id:{contact['user_id']}"
    return None


def log_send(account_name, identifier, name, status, note=""):
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "account", "identifier", "name", "status", "note"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            account_name, identifier, name, status, note,
        ])


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": datetime.now().strftime("%Y-%m-%d")}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("date") != today:
        return {"date": today}
    return state


def save_state(state):
    state["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# 私訊發送
# ============================================================

async def send_to_contact(client, contact, account_name):
    identifier = get_identifier(contact)
    name = contact["name"]

    try:
        if contact["username"]:
            user = await client.get_entity(contact["username"])
        elif contact["user_id"]:
            user = await client.get_entity(contact["user_id"])
        else:
            return "skip"
    except Exception:
        log_send(account_name, identifier, name, "resolve_error")
        return "skip"

    messages = get_personalized_messages(name, GROUP_INVITE_LINK)

    try:
        for i, msg in enumerate(messages):
            async with client.action(user, "typing"):
                await asyncio.sleep(max(DM_TYPING_DELAY, len(msg) * 0.05))
            await client.send_message(user, msg)
            if i < len(messages) - 1:
                await asyncio.sleep(random.uniform(DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX))

        log_send(account_name, identifier, name, "success", f"{len(messages)} 段")
        return "success"

    except errors.FloodWaitError as e:
        log_send(account_name, identifier, name, "flood_wait", f"{e.seconds}s")
        return f"flood:{e.seconds}"
    except errors.UserPrivacyRestrictedError:
        log_send(account_name, identifier, name, "privacy")
        return "skip"
    except errors.PeerFloodError:
        log_send(account_name, identifier, name, "peer_flood")
        return "peer_flood"
    except Exception as e:
        log_send(account_name, identifier, name, "error", str(e))
        return "skip"


async def run_dm_for_account(acc, contacts_batch, sent_set):
    """用一個帳號發送一批人"""
    acc_name = acc["name"]
    proxy = make_proxy(acc.get("proxy"))

    try:
        client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
        await client.start()
        me = await client.get_me()
        log(f"  [{acc_name}] 登入: {me.first_name}")
    except Exception as e:
        log(f"  [{acc_name}] 登入失敗: {e}")
        return 0

    success = 0
    processed = 0

    try:
        for contact in contacts_batch:
            identifier = get_identifier(contact)
            if identifier in sent_set:
                continue

            log(f"  [{acc_name}] #{processed+1}/{len(contacts_batch)} → {contact['name']}")

            result = await send_to_contact(client, contact, acc_name)

            if result == "success":
                success += 1
                sent_set.add(identifier)
                log(f"    ✅ 成功")
            elif result == "peer_flood":
                log(f"    🚫 帳號被限制，停止")
                break
            elif isinstance(result, str) and result.startswith("flood:"):
                wait = int(result.split(":")[1])
                if wait > 300:
                    log(f"    ⚠️ 限流 {wait}s，停止")
                    break
                log(f"    ⚠️ 限流 {wait}s，等待...")
                await asyncio.sleep(wait + 10)
            else:
                log(f"    ⏭ 跳過")

            processed += 1
            delay = random.uniform(acc["delay_min"], acc["delay_max"])
            await asyncio.sleep(delay)

    except Exception as e:
        log(f"  [{acc_name}] 錯誤: {e}")

    await client.disconnect()
    log(f"  [{acc_name}] 完成: 成功 {success}/{processed}")
    return success


# ============================================================
# 自動化任務
# ============================================================

async def task_dm():
    """多帳號私訊任務"""
    log("=" * 50)
    log("📨 開始多帳號私訊")

    accounts = load_accounts()
    if not accounts:
        log("  沒有帳號，跳過")
        return

    contacts = load_contacts()
    sent_set = load_sent_log()
    pending = [c for c in contacts if get_identifier(c) not in sent_set]

    log(f"  名單: {len(contacts)} 人, 已發: {len(sent_set)}, 待發: {len(pending)}")

    if not pending:
        log("  沒有待發名單")
        return

    state = load_state()
    total_success = 0

    # 預分配名單
    idx = 0
    for acc in accounts:
        sent_today = state.get(acc["name"], 0)
        remaining = max(0, acc["daily_limit"] - sent_today)
        if remaining == 0:
            continue

        batch = pending[idx:idx + remaining]
        if not batch:
            break
        idx += len(batch)

        log(f"\n  啟動 {acc['name']}（分配 {len(batch)} 人）")
        success = await run_dm_for_account(acc, batch, sent_set)
        total_success += success

        # 更新狀態
        state[acc["name"]] = state.get(acc["name"], 0) + success
        save_state(state)

        # 帳號間休息
        rest = 30  # 分鐘
        if idx < len(pending):
            log(f"  😴 休息 {rest} 分鐘...")
            await asyncio.sleep(rest * 60)

    log(f"\n📊 私訊完成: 成功 {total_success} 人")


async def task_scrape():
    """自動撈名單"""
    log("=" * 50)
    log("📋 開始自動撈名單")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
    from telethon.tl.types import ChannelParticipantsSearch
    from telethon.errors import ChatAdminRequiredError

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or d.is_channel]

    total_members = 0
    os.makedirs(DATA_DIR, exist_ok=True)

    for d in groups:
        entity = d.entity
        if not getattr(entity, "megagroup", False):
            continue

        try:
            full = await client(GetFullChannelRequest(entity))
            if not getattr(full.full_chat, "can_view_participants", False):
                continue

            test = await client(GetParticipantsRequest(
                channel=entity, filter=ChannelParticipantsSearch(""),
                offset=0, limit=10, hash=0,
            ))
            if test.count < 50:
                continue

            # 撈取
            members = []
            seen = set()
            offset = 0
            while True:
                participants = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsSearch(""),
                    offset=offset, limit=200, hash=0,
                ))
                if not participants.users:
                    break
                for user in participants.users:
                    if user.id not in seen:
                        seen.add(user.id)
                        members.append({
                            "user_id": user.id,
                            "username": user.username or "",
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "phone": user.phone or "",
                            "is_bot": user.bot or False,
                            "source_group": d.title,
                            "source_group_id": entity.id,
                        })
                offset += len(participants.users)
                if offset >= participants.count:
                    break

            if members:
                safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in d.title)[:50]
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = os.path.join(DATA_DIR, f"{safe_name}_{ts}.csv")
                with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.DictWriter(f, fieldnames=members[0].keys())
                    writer.writeheader()
                    writer.writerows(members)
                total_members += len(members)
                log(f"  ✅ {d.title}: {len(members)} 位")

        except ChatAdminRequiredError:
            continue
        except Exception:
            continue

        await asyncio.sleep(1)

    await client.disconnect()
    log(f"📊 撈名單完成: {total_members} 位")


# ============================================================
# 主程式
# ============================================================

async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       全自動模式 (Autopilot)                  ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")

    accounts = load_accounts()
    contacts = load_contacts()
    sent_set = load_sent_log()

    print(f"  帳號: {len(accounts)} 個")
    print(f"  名單: {len(contacts)} 人（待發: {len(contacts) - len(sent_set)}）")
    print()
    print("  自動化任務：")
    print("    1. 多帳號私訊 — 現在開始")
    print("    2. 撈名單     — 每週一次")
    print()
    print("  Bot 和內容轉發請另外啟動：")
    print("    主選單 [11] 背景啟動 Bot")
    print("    主選單 [6]  啟動即時監聽轉發")
    print()

    confirm = input("  啟動全自動模式？(y/n): ").strip().lower()
    if confirm != "y":
        return

    log("🚀 全自動模式啟動")

    last_scrape = None

    while True:
        now = datetime.now()

        # 每天跑一次私訊
        log(f"\n{'='*55}")
        log(f"📅 {now.strftime('%Y-%m-%d %H:%M')} 開始今日任務")

        await task_dm()

        # 每週一撈一次名單
        if now.weekday() == 0 and last_scrape != now.date():
            await task_scrape()
            last_scrape = now.date()

        # 等到明天早上 8 點
        tomorrow_8am = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0)
        wait_seconds = (tomorrow_8am - datetime.now()).total_seconds()
        log(f"\n✅ 今日任務完成，下次執行: {tomorrow_8am.strftime('%Y-%m-%d %H:%M')}")
        log(f"   等待 {wait_seconds/3600:.1f} 小時...\n")

        await asyncio.sleep(wait_seconds)


if __name__ == "__main__":
    asyncio.run(main())
