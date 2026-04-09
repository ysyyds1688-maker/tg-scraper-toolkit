"""
撈名單 託管模式
每週自動撈取所有已加入群組的成員，合併去重
"""

import asyncio
import csv
import glob
import json
import os
import sys
from datetime import datetime, timedelta

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from config import API_ID, API_HASH, SESSION_NAME, TOOLKIT_DIR, DATA_DIR
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import ChatAdminRequiredError


def load_scraper_account():
    accounts_file = os.path.join(TOOLKIT_DIR, "accounts.json")
    if not os.path.exists(accounts_file):
        return None
    with open(accounts_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    for a in data.get("accounts", []):
        if a.get("role") == "scraper" and a.get("enabled", True):
            return a
    return None


async def scrape_all():
    """撈取所有可撈的群組"""
    acc = load_scraper_account()
    if acc:
        client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"])
    else:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    await client.start()
    me = await client.get_me()
    print(f"  ✅ 登入: {me.first_name}")

    dialogs = await client.get_dialogs()
    total = 0
    os.makedirs(DATA_DIR, exist_ok=True)

    for d in dialogs:
        entity = d.entity
        if not getattr(entity, "megagroup", False):
            continue
        try:
            full = await client(GetFullChannelRequest(entity))
            if not getattr(full.full_chat, "can_view_participants", False):
                continue
            test = await client(GetParticipantsRequest(
                channel=entity, filter=ChannelParticipantsSearch(""),
                offset=0, limit=10, hash=0))
            if test.count < 50:
                continue

            members, seen, offset = [], set(), 0
            while True:
                p = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsSearch(""),
                    offset=offset, limit=200, hash=0))
                if not p.users:
                    break
                for u in p.users:
                    if u.id not in seen:
                        seen.add(u.id)
                        members.append({
                            "user_id": u.id, "username": u.username or "",
                            "first_name": u.first_name or "", "last_name": u.last_name or "",
                            "phone": u.phone or "", "is_bot": u.bot or False,
                            "source_group": d.title, "source_group_id": entity.id,
                        })
                offset += len(p.users)
                if offset >= p.count:
                    break

            if members:
                safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in d.title)[:50]
                fp = os.path.join(DATA_DIR, f"{safe}_{datetime.now().strftime('%Y%m%d')}.csv")
                with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=members[0].keys())
                    w.writeheader()
                    w.writerows(members)
                total += len(members)
                print(f"  ✅ {d.title}: {len(members)} 位")

        except (ChatAdminRequiredError, Exception):
            continue
        await asyncio.sleep(1)

    await client.disconnect()
    return total


def merge_dedup():
    """合併去重"""
    exclude = ["search_report", "msg_", "dm_sent_log", "all_members", "members_with", "members_no"]
    files = [f for f in glob.glob(os.path.join(DATA_DIR, "*.csv"))
             if not any(ex in os.path.basename(f) for ex in exclude)]

    if not files:
        return 0

    all_members = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if "user_id" in (reader.fieldnames or []):
                    all_members.extend(list(reader))
        except Exception:
            continue

    unique = {}
    for m in all_members:
        uid = m.get("user_id", "")
        if not uid:
            continue
        if uid in unique:
            existing = unique[uid].get("source_group", "")
            new_src = m.get("source_group", "")
            if new_src and new_src not in existing:
                unique[uid]["source_group"] = f"{existing}; {new_src}" if existing else new_src
        else:
            unique[uid] = dict(m)

    members = list(unique.values())
    fieldnames = ["user_id", "username", "first_name", "last_name",
                  "phone", "is_bot", "source_group", "source_group_id"]

    for path, data in [
        (os.path.join(TOOLKIT_DIR, "all_members.csv"), members),
        (os.path.join(TOOLKIT_DIR, "members_with_username.csv"), [m for m in members if m.get("username")]),
        (os.path.join(TOOLKIT_DIR, "members_no_username.csv"), [m for m in members if not m.get("username")]),
    ]:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    return len(members)


async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       撈名單 託管模式                          ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print("  每週自動撈取一次所有群組成員")
    print("  按 Ctrl+C 停止\n")

    confirm = input("  啟動？(y/n): ").strip().lower()
    if confirm != "y":
        return

    try:
        while True:
            print(f"\n{'='*50}")
            print(f"  📋 {datetime.now().strftime('%Y-%m-%d %H:%M')} 開始撈名單")

            total = await scrape_all()
            count = merge_dedup()
            print(f"\n  📊 撈取: {total} 位，合併去重後: {count} 位")

            # 等一週
            next_run = datetime.now() + timedelta(weeks=1)
            wait = (next_run - datetime.now()).total_seconds()
            print(f"  下次: {next_run.strftime('%Y-%m-%d %H:%M')}（{wait/3600/24:.1f} 天後）")
            await asyncio.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n  ⚠️ 中斷")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
