"""
撈名單 託管模式（全自動）
1. 搜尋新群組（關鍵字）
2. 跳過已加入/已撈過的
3. 自動加入（帶冷卻）
4. 撈成員列表 + 撈訊息發言者
5. 合併去重 + 清洗
6. 撈完自動退出新加入的群組（避免佔滿 500 上限）
每週自動跑一次
"""

import asyncio
import csv
import glob
import json
import os
import random
import sys
from datetime import datetime, timedelta

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from config import API_ID, API_HASH, SESSION_NAME, TOOLKIT_DIR, DATA_DIR, SEARCH_KEYWORDS
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest, LeaveChannelRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import ChannelParticipantsSearch, ChannelParticipantsAdmins, Channel
from telethon.errors import ChatAdminRequiredError, FloodWaitError, UserAlreadyParticipantError

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

# 加群設定
JOIN_DELAY_MIN = 30      # 每加一個群最短等待（秒）
JOIN_DELAY_MAX = 60      # 每加一個群最長等待（秒）
JOIN_BATCH_SIZE = 8      # 一批最多加幾個
JOIN_BATCH_REST = 120    # 一批加完休息（秒）
MAX_NEW_GROUPS = 20      # 每輪最多加入幾個新群組
DEEP_CRAWL_LIMIT = 200   # 深度搜尋每個群掃幾則訊息找連結

# 已處理群組記錄
SCRAPED_LOG = os.path.join(TOOLKIT_DIR, "scraped_groups.json")


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


def load_scraped_groups():
    """載入已撈過的群組 ID"""
    if not os.path.exists(SCRAPED_LOG):
        return set()
    with open(SCRAPED_LOG, "r", encoding="utf-8") as f:
        data = json.load(f)
    return set(data.get("group_ids", []))


def save_scraped_group(group_id):
    """記錄已撈過的群組"""
    data = {"group_ids": []}
    if os.path.exists(SCRAPED_LOG):
        with open(SCRAPED_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
    if group_id not in data["group_ids"]:
        data["group_ids"].append(group_id)
    with open(SCRAPED_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# ============================================================
# Phase 0: 搜尋新群組
# ============================================================

async def search_new_groups(client, scraped_ids, joined_ids):
    """用關鍵字搜尋新群組（群組優先，頻道另外收集）"""
    print(f"\n  🔍 用 {len(SEARCH_KEYWORDS)} 個關鍵字搜尋...")
    found_groups = {}    # id -> (entity, source)
    found_channels = {}  # id -> (entity, source)

    for i, kw in enumerate(SEARCH_KEYWORDS):
        try:
            result = await client(SearchRequest(q=kw, limit=50))
            for chat in result.chats:
                if not isinstance(chat, Channel):
                    continue
                if chat.id in scraped_ids or chat.id in joined_ids:
                    continue
                if chat.id in found_groups or chat.id in found_channels:
                    continue

                if getattr(chat, "megagroup", False):
                    found_groups[chat.id] = (chat, f"關鍵字:{kw}")
                elif getattr(chat, "broadcast", False):
                    found_channels[chat.id] = (chat, f"關鍵字:{kw}")
        except FloodWaitError as e:
            print(f"    限速 {e.seconds}s，等待...")
            await asyncio.sleep(e.seconds)
        except Exception:
            pass
        await asyncio.sleep(1.5)

    print(f"    找到 {len(found_groups)} 個新群組 + {len(found_channels)} 個新頻道")
    return found_groups, found_channels


async def deep_crawl_links(client, scraped_ids, joined_ids):
    """從已加入群組的訊息中挖掘 t.me 連結，找到新群組"""
    import re
    print(f"\n  🕸️ 深度搜尋：掃描訊息中的 t.me 連結...")

    link_pattern = re.compile(r"(?:https?://)?t\.me/(?:\+|joinchat/)?([\w-]+)")
    found_groups = {}
    found_channels = {}
    scanned = 0

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if getattr(d.entity, "megagroup", False)]

    for d in groups[:15]:  # 最多掃 15 個已加入的群組
        links = set()
        try:
            async for msg in client.iter_messages(d.entity, limit=DEEP_CRAWL_LIMIT):
                if msg.text:
                    for match in link_pattern.findall(msg.text):
                        links.add(match)
            scanned += 1

            for link in links:
                try:
                    # 嘗試解析連結
                    if link.startswith("+") or link.startswith("joinchat"):
                        continue  # 私密連結跳過，風險高
                    entity = await client.get_entity(link)
                    if not isinstance(entity, Channel):
                        continue
                    if entity.id in scraped_ids or entity.id in joined_ids:
                        continue
                    if entity.id in found_groups or entity.id in found_channels:
                        continue

                    if getattr(entity, "megagroup", False):
                        found_groups[entity.id] = (entity, f"連結自:{d.title[:20]}")
                    elif getattr(entity, "broadcast", False):
                        found_channels[entity.id] = (entity, f"連結自:{d.title[:20]}")

                    await asyncio.sleep(1)
                except Exception:
                    continue

        except Exception:
            continue

    print(f"    掃描 {scanned} 個群組的訊息")
    print(f"    找到 {len(found_groups)} 個新群組 + {len(found_channels)} 個新頻道")
    return found_groups, found_channels


# ============================================================
# Phase 1: 自動加入
# ============================================================

async def join_groups(client, groups_dict):
    """自動加入群組，帶冷卻"""
    if not groups_dict:
        return []

    joined = []
    count = 0

    for gid, (entity, kw) in groups_dict.items():
        if count >= JOIN_BATCH_SIZE:
            print(f"    達到單批上限 {JOIN_BATCH_SIZE} 個，休息 {JOIN_BATCH_REST//60} 分鐘...")
            await asyncio.sleep(JOIN_BATCH_REST)
            count = 0

        try:
            username = getattr(entity, "username", None)
            if username:
                await client.get_entity(username)
                # 嘗試加入
                from telethon.tl.functions.channels import JoinChannelRequest
                await client(JoinChannelRequest(entity))
                joined.append(entity)
                count += 1
                print(f"    ✅ 加入: {entity.title} (搜尋: {kw})")
            else:
                print(f"    ⏭ 跳過（私密群組無法自動加入）: {entity.title}")
                continue

        except UserAlreadyParticipantError:
            joined.append(entity)
            print(f"    ⏭ 已在群組中: {entity.title}")
        except FloodWaitError as e:
            print(f"    ⚠️ 限速 {e.seconds}s，等待...")
            await asyncio.sleep(e.seconds + 10)
        except Exception as e:
            print(f"    ❌ 加入失敗: {entity.title} ({e})")

        delay = random.uniform(JOIN_DELAY_MIN, JOIN_DELAY_MAX)
        await asyncio.sleep(delay)

    print(f"    共加入 {len(joined)} 個群組")
    return joined


# ============================================================
# Phase 2: 撈成員 + 發言者
# ============================================================

async def scrape_group(client, entity, title):
    """撈單一群組的成員列表 + 訊息發言者"""
    members_count = 0
    senders_count = 0

    # 取管理員列表
    admin_ids = set()
    try:
        admins = await client(GetParticipantsRequest(
            channel=entity, filter=ChannelParticipantsAdmins(),
            offset=0, limit=100, hash=0))
        for u in admins.users:
            admin_ids.add(u.id)
    except Exception:
        pass

    os.makedirs(DATA_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in title)[:50]
    ts = datetime.now().strftime("%Y%m%d")

    # --- 撈成員列表 ---
    try:
        full = await client(GetFullChannelRequest(entity))
        if getattr(full.full_chat, "can_view_participants", False):
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
                    fp = os.path.join(DATA_DIR, f"{safe}_{ts}.csv")
                    with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                        w = csv.DictWriter(f, fieldnames=members[0].keys())
                        w.writeheader()
                        w.writerows(members)
                    members_count = len(members)
    except Exception:
        pass

    # --- 撈訊息發言者 ---
    try:
        seen_ids = set()
        senders = []
        async for msg in client.iter_messages(entity, limit=500):
            if not msg.sender:
                continue
            sender = msg.sender
            sid = msg.sender_id
            if not sid or sid in seen_ids:
                continue
            if getattr(sender, "bot", False):
                seen_ids.add(sid)
                continue
            if sid in admin_ids:
                seen_ids.add(sid)
                continue
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
                "source_group": title, "source_group_id": entity.id,
            })

        if senders:
            fp = os.path.join(DATA_DIR, f"senders_{safe}_{ts}.csv")
            with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=senders[0].keys())
                w.writeheader()
                w.writerows(senders)
            senders_count = len(senders)
    except Exception:
        pass

    return members_count, senders_count


# ============================================================
# Phase 3: 退出新加入的群組
# ============================================================

async def leave_groups(client, groups_to_leave):
    """退出新加入的群組，釋放名額"""
    if not groups_to_leave:
        return
    print(f"\n  🚪 退出 {len(groups_to_leave)} 個新加入的群組...")
    for entity in groups_to_leave:
        try:
            await client(LeaveChannelRequest(entity))
            print(f"    退出: {entity.title}")
            await asyncio.sleep(2)
        except Exception:
            pass


# ============================================================
# Phase 4: 合併去重 + 清洗
# ============================================================

def merge_dedup_and_clean():
    exclude = ["search_report", "msg_", "dm_sent_log", "all_members", "members_with", "members_no"]
    files = [f for f in glob.glob(os.path.join(DATA_DIR, "*.csv"))
             if not any(ex in os.path.basename(f) for ex in exclude)]
    for subdir in ["原始撈取", "訊息發言者"]:
        files.extend(glob.glob(os.path.join(DATA_DIR, subdir, "*.csv")))

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

    clean = []
    removed = 0
    for m in unique.values():
        name = (m.get("first_name", "") + m.get("last_name", "") + m.get("username", "")).lower()
        is_bot = str(m.get("is_bot", "")).strip().lower() == "true"
        if is_bot or any(kw in name for kw in STAFF_KEYWORDS):
            removed += 1
            continue
        clean.append(m)

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

    output_dir = os.path.join(TOOLKIT_DIR, "名單輸出")
    if os.path.isdir(output_dir):
        import shutil
        for fn in ["all_members.csv", "members_with_username.csv", "members_no_username.csv"]:
            shutil.copy2(os.path.join(TOOLKIT_DIR, fn), os.path.join(output_dir, fn))

    has_un = len([m for m in clean if m.get("username")])
    has_id = len(clean) - has_un

    print(f"\n  📊 合併去重+清洗:")
    print(f"     去重前: {len(unique)}")
    print(f"     清洗:   {removed} 位（管理員/Bot/工作人員）")
    print(f"     清洗後: {len(clean)} 位")
    print(f"     可發送: {len(clean)}（username {has_un} + user_id {has_id}）")

    return len(clean)


# ============================================================
# 全自動流程
# ============================================================

async def run_full_cycle():
    """完整一輪：搜尋 → 深度搜尋 → 加入 → 撈取 → 退出 → 合併清洗"""
    acc = load_scraper_account()
    if acc:
        client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"])
    else:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    await client.start()
    me = await client.get_me()
    print(f"  ✅ 登入: {me.first_name}")

    scraped_ids = load_scraped_groups()

    # 取得已加入的群組/頻道 ID
    dialogs = await client.get_dialogs()
    joined_ids = set()
    existing_groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            joined_ids.add(d.entity.id)
            if getattr(d.entity, "megagroup", False):
                existing_groups.append(d)

    # ── Phase 0a: 關鍵字搜尋 ──
    search_groups, search_channels = await search_new_groups(client, scraped_ids, joined_ids)

    # ── Phase 0b: 深度搜尋（從訊息挖連結）──
    deep_groups, deep_channels = await deep_crawl_links(client, scraped_ids, joined_ids)

    # 合併搜尋結果（群組優先）
    all_new_groups = {**search_groups, **deep_groups}
    all_new_channels = {**search_channels, **deep_channels}

    # 限制數量
    if len(all_new_groups) > MAX_NEW_GROUPS:
        limited = dict(list(all_new_groups.items())[:MAX_NEW_GROUPS])
        print(f"\n  ⚠️ 找到 {len(all_new_groups)} 個新群組，本輪只處理 {MAX_NEW_GROUPS} 個")
        all_new_groups = limited

    print(f"\n  📊 搜尋結果: 群組 {len(all_new_groups)} 個 | 頻道 {len(all_new_channels)} 個（頻道暫不加入）")

    # ── Phase 1: 自動加入群組（頻道不加入）──
    newly_joined = await join_groups(client, all_new_groups)

    # 更新 joined_ids
    for entity in newly_joined:
        joined_ids.add(entity.id)

    # ── Phase 2: 撈取所有群組（現有 + 新加入）──
    total_members = 0
    total_senders = 0

    # 只撈還沒撈過的現有群組
    unscrapped = [d for d in existing_groups if d.entity.id not in scraped_ids]
    if unscrapped:
        print(f"\n  📥 撈取未撈過的現有群組（{len(unscrapped)} 個，跳過 {len(existing_groups) - len(unscrapped)} 個已撈過）...")
        for d in unscrapped:
            m, s = await scrape_group(client, d.entity, d.title)
            if m or s:
                print(f"    ✅ {d.title}: 成員 {m} + 發言者 {s}")
            save_scraped_group(d.entity.id)
            total_members += m
            total_senders += s
            await asyncio.sleep(1)
    else:
        print(f"\n  ⏭ 現有群組全部已撈過（{len(existing_groups)} 個），跳過")

    if newly_joined:
        print(f"\n  📥 撈取新群組（{len(newly_joined)} 個）...")
        for entity in newly_joined:
            m, s = await scrape_group(client, entity, entity.title)
            if m or s:
                print(f"    ✅ {entity.title}: 成員 {m} + 發言者 {s}")
            save_scraped_group(entity.id)
            total_members += m
            total_senders += s
            await asyncio.sleep(1)

    print(f"\n  撈取結果: 成員 {total_members} + 發言者 {total_senders}")

    # ── Phase 3: 退出新加入的群組 ──
    await leave_groups(client, newly_joined)

    await client.disconnect()

    # ── Phase 4: 合併去重 + 清洗 ──
    total = merge_dedup_and_clean()

    # 儲存頻道清單供之後參考
    if all_new_channels:
        channels_file = os.path.join(TOOLKIT_DIR, "discovered_channels.json")
        existing_ch = []
        if os.path.exists(channels_file):
            with open(channels_file, "r", encoding="utf-8") as f:
                existing_ch = json.load(f)
        for gid, (entity, source) in all_new_channels.items():
            username = getattr(entity, "username", "") or ""
            existing_ch.append({
                "id": gid,
                "title": entity.title,
                "username": username,
                "link": f"https://t.me/{username}" if username else "",
                "source": source,
                "found_at": datetime.now().strftime("%Y-%m-%d"),
            })
        with open(channels_file, "w", encoding="utf-8") as f:
            json.dump(existing_ch, f, ensure_ascii=False, indent=2)
        print(f"\n  📢 發現的頻道已存到 discovered_channels.json（{len(all_new_channels)} 個）")
        print(f"     之後可手動決定要不要加入")

    return total


# ============================================================
# 主程式
# ============================================================

async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       撈名單 託管模式（全自動）                 ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")
    print("  全自動流程：")
    print("    1. 關鍵字搜尋新群組")
    print("    2. 深度搜尋（從訊息挖 t.me 連結找新群組）")
    print("    3. 自動加入群組（帶冷卻，每輪最多 20 個）")
    print("    4. 撈成員列表 + 撈訊息發言者")
    print("    5. 撈完退出新群組（避免佔滿 500 上限）")
    print("    6. 合併去重 + 自動清洗")
    print("    頻道另外記錄，不自動加入")
    print("    每週自動跑一次")
    print()
    print("  按 Ctrl+C 停止\n")

    confirm = input("  啟動？(y/n): ").strip().lower()
    if confirm != "y":
        return

    try:
        while True:
            print(f"\n{'='*55}")
            print(f"  📋 {datetime.now().strftime('%Y-%m-%d %H:%M')} 開始全自動撈名單")

            total = await run_full_cycle()

            next_run = datetime.now() + timedelta(weeks=1)
            wait = (next_run - datetime.now()).total_seconds()
            print(f"\n  ✅ 完成！清洗後名單: {total} 位")
            print(f"  下次: {next_run.strftime('%Y-%m-%d %H:%M')}（{wait/3600/24:.1f} 天後）")
            await asyncio.sleep(wait)

    except KeyboardInterrupt:
        print("\n\n  ⚠️ 中斷")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
