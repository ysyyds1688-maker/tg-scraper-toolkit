"""
私訊輪換 託管模式
每天自動跑多帳號私訊，跑完等明天 8 點再跑
"""

import asyncio
import csv
import json
import os
import random
import sys
from datetime import datetime, timedelta

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from config import (
    GROUP_INVITE_LINK, DM_TYPING_DELAY, DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX,
)
from telethon import TelegramClient, errors
from messages import get_personalized_messages
import socks

ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
STATE_FILE = os.path.join(TOOLKIT_DIR, "dm_state.json")


def load_dm_accounts():
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [a for a in data.get("accounts", [])
            if a.get("enabled", True) and a.get("role") == "dm"]


def make_proxy(p):
    if not p:
        return None
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy = (type_map.get(p.get("type", "socks5").lower(), socks.SOCKS5), p["host"], p["port"])
    if p.get("username"):
        proxy = proxy + (True, p["username"], p.get("password", ""))
    return proxy


def load_contacts():
    from config import DM_CONTACT_FILES
    contacts, seen = [], set()
    for fp in DM_CONTACT_FILES:
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if row.get("is_bot", "").strip().lower() == "true":
                        continue
                    uid = row.get("user_id", "").strip()
                    un = row.get("username", "").strip().lstrip("@")
                    if not uid and not un:
                        continue
                    ident = un or uid
                    if ident in seen:
                        continue
                    seen.add(ident)
                    first = row.get("first_name", "").strip()
                    last = row.get("last_name", "").strip()
                    contacts.append({"user_id": int(uid) if uid.isdigit() else None,
                                     "username": un or None,
                                     "name": f"{first} {last}".strip() or un or "朋友"})
        except Exception:
            continue
    return contacts


def load_sent():
    sent = set()
    if not os.path.exists(SENT_LOG):
        return sent
    with open(SENT_LOG, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("identifier"):
                sent.add(row["identifier"])
    return sent


def get_id(c):
    if c["username"]:
        return f"username:{c['username']}"
    if c["user_id"]:
        return f"id:{c['user_id']}"
    return None


def log_send(acc, ident, name, status, note=""):
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "account", "identifier", "name", "status", "note"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), acc, ident, name, status, note])


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": datetime.now().strftime("%Y-%m-%d")}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        s = json.load(f)
    if s.get("date") != datetime.now().strftime("%Y-%m-%d"):
        return {"date": datetime.now().strftime("%Y-%m-%d")}
    return s


def save_state(s):
    s["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


async def send_one(client, contact, acc_name):
    ident = get_id(contact)
    name = contact["name"]
    try:
        user = await client.get_entity(contact["username"] or contact["user_id"])
    except Exception:
        log_send(acc_name, ident, name, "resolve_error")
        return "skip"

    msgs = get_personalized_messages(name, GROUP_INVITE_LINK)
    try:
        for i, msg in enumerate(msgs):
            async with client.action(user, "typing"):
                await asyncio.sleep(max(DM_TYPING_DELAY, len(msg) * 0.05))
            await client.send_message(user, msg)
            if i < len(msgs) - 1:
                await asyncio.sleep(random.uniform(DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX))
        log_send(acc_name, ident, name, "success", f"{len(msgs)} 段")
        return "success"
    except errors.FloodWaitError as e:
        log_send(acc_name, ident, name, "flood_wait", f"{e.seconds}s")
        return f"flood:{e.seconds}"
    except errors.PeerFloodError:
        log_send(acc_name, ident, name, "peer_flood")
        return "peer_flood"
    except errors.UserPrivacyRestrictedError:
        log_send(acc_name, ident, name, "privacy")
        return "skip"
    except Exception as e:
        log_send(acc_name, ident, name, "error", str(e))
        return "skip"


async def run_daily():
    accounts = load_dm_accounts()
    contacts = load_contacts()
    sent_set = load_sent()
    pending = [c for c in contacts if get_id(c) not in sent_set]
    state = load_state()

    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{ts}] 名單: {len(contacts)}, 已發: {len(sent_set)}, 待發: {len(pending)}")

    if not pending:
        print(f"  [{ts}] 沒有待發名單")
        return

    idx = 0
    total = 0
    random.shuffle(accounts)

    for acc in accounts:
        sent_today = state.get(acc["name"], 0)
        remaining = max(0, acc["daily_limit"] - sent_today)
        if remaining == 0:
            continue
        batch = pending[idx:idx + remaining]
        if not batch:
            break
        idx += len(batch)

        proxy = make_proxy(acc.get("proxy"))
        try:
            client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
            await client.start()
            me = await client.get_me()
            print(f"\n  [{acc['name']}] 登入: {me.first_name}（分配 {len(batch)} 人）")
        except Exception as e:
            print(f"  [{acc['name']}] 登入失敗: {e}")
            continue

        success = 0
        for i, contact in enumerate(batch):
            ident = get_id(contact)
            if ident in sent_set:
                continue
            print(f"    #{i+1}/{len(batch)} → {contact['name']}", end="")
            result = await send_one(client, contact, acc["name"])
            if result == "success":
                success += 1
                sent_set.add(ident)
                print(" ✅")
            elif result == "peer_flood":
                print(" 🚫 停止")
                break
            elif isinstance(result, str) and result.startswith("flood:"):
                w = int(result.split(":")[1])
                if w > 300:
                    print(f" ⚠️ 限流太久，停止")
                    break
                print(f" ⚠️ {w}s")
                await asyncio.sleep(w + 10)
            else:
                print(" ⏭")
            await asyncio.sleep(random.uniform(acc["delay_min"], acc["delay_max"]))

        await client.disconnect()
        total += success
        state[acc["name"]] = state.get(acc["name"], 0) + success
        save_state(state)

        if idx < len(pending):
            print(f"  [{acc['name']}] 完成 {success} 人，休息 30 分鐘...")
            await asyncio.sleep(30 * 60)

    print(f"\n  📊 今日私訊完成: {total} 人")


async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       私訊輪換 託管模式                        ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")

    accounts = load_dm_accounts()
    contacts = load_contacts()
    sent_set = load_sent()
    dm_total = sum(a["daily_limit"] for a in accounts)

    print(f"  私訊帳號: {len(accounts)} 個（每日共 {dm_total} 人）")
    print(f"  名單: {len(contacts)} 人（待發: {len(contacts) - len(sent_set)}）")
    print(f"\n  每天自動跑，跑完等明天 08:00 再跑")
    print(f"  按 Ctrl+C 停止\n")

    confirm = input("  啟動？(y/n): ").strip().lower()
    if confirm != "y":
        return

    try:
        while True:
            print(f"\n{'='*50}")
            print(f"  📅 {datetime.now().strftime('%Y-%m-%d %H:%M')} 開始今日私訊")

            await run_daily()

            tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=8, minute=0, second=0)
            wait = (tomorrow - datetime.now()).total_seconds()
            print(f"\n  ✅ 今日完成，下次: {tomorrow.strftime('%Y-%m-%d %H:%M')}（{wait/3600:.1f}h）")
            await asyncio.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n  ⚠️ 中斷，進度已保存")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
