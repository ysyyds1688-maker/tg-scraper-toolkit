"""
撈名單 託管模式
自動執行：撈成員列表 + 撈訊息發言者 + 合併去重 + 清洗
每週自動跑一次
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
from telethon.tl.types import ChannelParticipantsSearch, ChannelParticipantsAdmins
from telethon.errors import ChatAdminRequiredError

# 清洗關鍵字
STAFF_KEYWORDS = [
    '客服', '經紀', '報班', '預約', '訂位', '接單', '小幫手', '助理', '管理',
    '官方', 'service', 'support', 'admin', 'boss', '老闆', '茶莊', '茶行',
    '外送', 'line', '娜娜', '步兵', '輔導', '幹部', '主管', '營運',
    '小編', '頻道', 'channel', 'bot', '機器人', '中心', '安全中心',
    '外送茶', '賴', '密我', '喝茶', '約妹', '茶糖', '外約', '舒壓',
    '品茶', 'robot', 'leak', '蘋果客服', '貝兒客服', '猴弟',
    '廣告', '代發', '解禁', '禁言',
]


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
    """Phase 1: 撈成員列表 + Phase 2: 撈訊息發言者"""
    acc = load_scraper_account()
    if acc:
        client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"])
    else:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    await client.start()
    me = await client.get_me()
    print(f"  ✅ 登入: {me.first_name}")

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or d.is_channel]
    megagroups = [d for d in groups if getattr(d.entity, "megagroup", False)]

    total_members = 0
    total_senders = 0
    os.makedirs(DATA_DIR, exist_ok=True)

    for d in megagroups:
        entity = d.entity
        title = d.title

        # === Phase 1: 撈成員列表 ===
        try:
            full = await client(GetFullChannelRequest(entity))
            if not getattr(full.full_chat, "can_view_participants", False):
                pass  # 不能撈成員，跳到 Phase 2
            else:
                test = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsSearch(""),
                    offset=0, limit=10, hash=0))
                if test.count >= 50:
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
                                    "source_group": title, "source_group_id": entity.id,
                                })
                        offset += len(p.users)
                        if offset >= p.count:
                            break

                    if members:
                        safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)[:50]
                        fp = os.path.join(DATA_DIR, f"{safe}_{datetime.now().strftime('%Y%m%d')}.csv")
                        with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                            w = csv.DictWriter(f, fieldnames=members[0].keys())
                            w.writeheader()
                            w.writerows(members)
                        total_members += len(members)
                        print(f"  ✅ {title}: 成員 {len(members)} 位")

        except (ChatAdminRequiredError, Exception):
            pass

        # === Phase 2: 撈訊息發言者 ===
        try:
            # 先取管理員列表
            admin_ids = set()
            try:
                admins = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsAdmins(),
                    offset=0, limit=100, hash=0))
                for u in admins.users:
                    admin_ids.add(u.id)
            except Exception:
                pass

            seen_ids = set()
            senders = []
            msg_count = 0

            async for msg in client.iter_messages(entity, limit=500):
                msg_count += 1
                if not msg.sender:
                    continue
                sender = msg.sender
                sid = msg.sender_id
                if not sid or sid in seen_ids:
                    continue

                # 跳過 bot
                if getattr(sender, "bot", False):
                    seen_ids.add(sid)
                    continue

                # 跳過管理員
                if sid in admin_ids:
                    seen_ids.add(sid)
                    continue

                # 跳過工作人員
                name_check = (
                    (getattr(sender, "first_name", "") or "")
                    + (getattr(sender, "last_name", "") or "")
                    + (getattr(sender, "username", "") or "")
                ).lower()
                if any(kw in name_check for kw in STAFF_KEYWORDS):
                    seen_ids.add(sid)
                    continue

                seen_ids.add(sid)
                senders.append({
                    "user_id": sid,
                    "username": getattr(sender, "username", "") or "",
                    "first_name": getattr(sender, "first_name", "") or "",
                    "last_name": getattr(sender, "last_name", "") or "",
                    "phone": getattr(sender, "phone", "") or "",
                    "is_bot": False,
                    "source_group": title,
                    "source_group_id": entity.id,
                })

            if senders:
                safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)[:50]
                fp = os.path.join(DATA_DIR, f"senders_{safe}_{datetime.now().strftime('%Y%m%d')}.csv")
                with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.DictWriter(f, fieldnames=senders[0].keys())
                    w.writeheader()
                    w.writerows(senders)
                total_senders += len(senders)
                print(f"  ✅ {title}: 發言者 {len(senders)} 位（掃 {msg_count} 則訊息）")

        except Exception:
            pass

        await asyncio.sleep(1)

    await client.disconnect()
    return total_members, total_senders


def merge_dedup_and_clean():
    """合併去重 + 清洗"""
    exclude = ["search_report", "msg_", "dm_sent_log", "all_members", "members_with", "members_no"]
    files = [f for f in glob.glob(os.path.join(DATA_DIR, "*.csv"))
             if not any(ex in os.path.basename(f) for ex in exclude)]

    # 也掃子資料夾
    for subdir in ["原始撈取", "訊息發言者"]:
        subpath = os.path.join(DATA_DIR, subdir, "*.csv")
        files.extend(glob.glob(subpath))

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

    # 去重
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

    # 清洗
    clean = []
    removed = 0
    for m in unique.values():
        name = (m.get("first_name", "") + m.get("last_name", "") + m.get("username", "")).lower()
        is_bot = m.get("is_bot", "").strip().lower() == "true" if isinstance(m.get("is_bot"), str) else m.get("is_bot", False)

        if is_bot or any(kw in name for kw in STAFF_KEYWORDS):
            removed += 1
            continue
        clean.append(m)

    # 寫入
    fieldnames = ["user_id", "username", "first_name", "last_name",
                  "phone", "is_bot", "source_group", "source_group_id"]

    for path, data in [
        (os.path.join(TOOLKIT_DIR, "all_members.csv"), clean),
        (os.path.join(TOOLKIT_DIR, "members_with_username.csv"), [m for m in clean if m.get("username")]),
        (os.path.join(TOOLKIT_DIR, "members_no_username.csv"), [m for m in clean if not m.get("username")]),
    ]:
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)

    # 更新名單輸出/
    output_dir = os.path.join(TOOLKIT_DIR, "名單輸出")
    if os.path.isdir(output_dir):
        import shutil
        for fn in ["all_members.csv", "members_with_username.csv", "members_no_username.csv"]:
            shutil.copy2(os.path.join(TOOLKIT_DIR, fn), os.path.join(output_dir, fn))

    has_un = len([m for m in clean if m.get("username")])
    has_id = len(clean) - has_un

    print(f"\n  📊 合併去重+清洗完成:")
    print(f"     去重前: {len(unique)} 位")
    print(f"     已清洗: {removed} 位（管理員/Bot/工作人員）")
    print(f"     清洗後: {len(clean)} 位")
    print(f"     可發送: {len(clean)} 位（username {has_un} + user_id {has_id}）")

    return len(clean)


async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       撈名單 託管模式                          ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print("  自動執行：撈成員 + 撈發言者 + 合併去重 + 清洗")
    print("  每週自動跑一次")
    print("  按 Ctrl+C 停止\n")

    confirm = input("  啟動？(y/n): ").strip().lower()
    if confirm != "y":
        return

    try:
        while True:
            print(f"\n{'='*50}")
            print(f"  📋 {datetime.now().strftime('%Y-%m-%d %H:%M')} 開始撈名單")

            members, senders = await scrape_all()
            print(f"\n  撈取結果: 成員 {members} 位 + 發言者 {senders} 位")

            total = merge_dedup_and_clean()

            next_run = datetime.now() + timedelta(weeks=1)
            wait = (next_run - datetime.now()).total_seconds()
            print(f"\n  下次: {next_run.strftime('%Y-%m-%d %H:%M')}（{wait/3600/24:.1f} 天後）")
            await asyncio.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n  ⚠️ 中斷")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
