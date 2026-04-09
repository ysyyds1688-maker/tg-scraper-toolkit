"""
Telegram 群組成員撈取工具
功能：
  1. 撈單一群組成員
  2. 批量撈所有已加入的群組
  3. 關鍵字搜尋群組並撈取
  結果自動合併去重
"""

import asyncio
import csv
import glob
import os
import string
import sys
from datetime import datetime

from config import (
    API_ID, API_HASH, SESSION_NAME,
    TOOLKIT_DIR, DATA_DIR, SEARCH_KEYWORDS,
    get_scraped_group_ids,
)
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import ChannelParticipantsSearch, Channel
from telethon.errors import ChatAdminRequiredError, FloodWaitError


# ============================================================
# 通用工具
# ============================================================

def safe_filename(name, max_len=50):
    return "".join(c if c.isalnum() or c in "_ -" else "_" for c in name)[:max_len]


def save_members_csv(members, label, output_dir):
    """儲存成員到 CSV"""
    if not members:
        return None
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_filename(label)}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    fieldnames = ["user_id", "username", "first_name", "last_name",
                  "phone", "is_bot", "source_group", "source_group_id"]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(members)
    return filepath


async def scrape_members(client, entity, group_title="", group_id=""):
    """抓取群組成員，自動判斷是否需要逐字搜尋"""
    members = []
    seen = set()

    try:
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
                        "source_group": group_title,
                        "source_group_id": group_id,
                    })
            offset += len(participants.users)
            if offset >= participants.count:
                break

    except ChatAdminRequiredError:
        print("  非管理員，改用逐字搜尋模式...")
        search_chars = (
            list(string.ascii_lowercase) + list(string.digits)
            + ["的", "是", "我", "人", "在", "有", "_", ".", "-"]
        )
        for char in search_chars:
            try:
                participants = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsSearch(char),
                    offset=0, limit=200, hash=0,
                ))
                new = 0
                for user in participants.users:
                    if user.id not in seen:
                        seen.add(user.id)
                        new += 1
                        members.append({
                            "user_id": user.id,
                            "username": user.username or "",
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "phone": user.phone or "",
                            "is_bot": user.bot or False,
                            "source_group": group_title,
                            "source_group_id": group_id,
                        })
                if new > 0:
                    print(f"    搜尋 '{char}' → +{new}，累計 {len(members)}")
                await asyncio.sleep(0.5)
            except ChatAdminRequiredError:
                break
            except Exception:
                continue

    return members


async def check_scrapable(client, entity):
    """檢查群組是否可抓取"""
    if not getattr(entity, "megagroup", False):
        return False, "頻道/非超級群組", 0

    try:
        full = await client(GetFullChannelRequest(entity))
        can_view = getattr(full.full_chat, "can_view_participants", False)
        count = getattr(full.full_chat, "participants_count", 0)
        if not can_view:
            return False, f"禁止查看({count}人)", count

        test = await client(GetParticipantsRequest(
            channel=entity, filter=ChannelParticipantsSearch(""),
            offset=0, limit=10, hash=0,
        ))
        if test.count >= 50:
            return True, f"可抓取({test.count}/{count}人)", count
        else:
            return False, f"太少({test.count}/{count}人)", count

    except ChatAdminRequiredError:
        return False, "需管理員", 0
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return False, "限速", 0
    except Exception as e:
        return False, f"{type(e).__name__}", 0


# ============================================================
# 模式 1：撈單一群組
# ============================================================

async def mode_single(client):
    """選擇一個群組撈取成員"""
    print("\n你加入的群組：")
    print("-" * 60)
    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or d.is_channel]

    for i, d in enumerate(groups):
        entity = d.entity
        count = getattr(entity, "participants_count", 0) or 0
        is_mega = "👥" if getattr(entity, "megagroup", False) else "📢"
        print(f"  [{i+1:3d}] {is_mega} {d.title[:45]:<45s} {count:>6d} 人")

    choice = input("\n輸入編號（或貼群組連結）: ").strip()
    if choice.startswith(("http", "@", "t.me")):
        entity = await client.get_entity(choice)
    else:
        idx = int(choice) - 1
        entity = groups[idx].entity

    title = getattr(entity, "title", "unknown")
    print(f"\n開始撈取: {title}")
    members = await scrape_members(client, entity, title, entity.id)
    print(f"共撈取 {len(members)} 位成員")

    filepath = save_members_csv(members, title, DATA_DIR)
    if filepath:
        print(f"已儲存: {filepath}")
    return members


# ============================================================
# 模式 2：批量撈所有群組
# ============================================================

async def mode_batch(client):
    """掃描所有群組並批量撈取"""
    print("\n正在掃描所有群組...\n")
    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or d.is_channel]

    scrapable = []
    for i, d in enumerate(groups):
        ok, reason, count = await check_scrapable(client, d.entity)
        status = "✓" if ok else "✗"
        print(f"  [{i+1:2d}] {status} {d.title[:40]:<40s} | {count:>6d} 人 | {reason}")
        if ok:
            scrapable.append(d)
        await asyncio.sleep(0.3)

    print(f"\n可抓取: {len(scrapable)} 個群組")
    if not scrapable:
        print("沒有可抓取的群組")
        return []

    confirm = input(f"\n開始撈取 {len(scrapable)} 個群組？(y/n): ").strip().lower()
    if confirm != "y":
        return []

    scraped_ids = get_scraped_group_ids()
    all_members = []

    for d in scrapable:
        if str(d.entity.id) in scraped_ids:
            print(f"  ⏭ 已爬過: {d.title}")
            continue
        print(f"  📥 {d.title}...", end="", flush=True)
        try:
            members = await scrape_members(client, d.entity, d.title, d.entity.id)
            all_members.extend(members)
            filepath = save_members_csv(members, d.title, DATA_DIR)
            print(f" {len(members)} 位 → {os.path.basename(filepath)}")
        except Exception as e:
            print(f" 失敗: {e}")
        await asyncio.sleep(1)

    return all_members


# ============================================================
# 模式 3：關鍵字搜尋並撈取
# ============================================================

async def mode_search(client):
    """用關鍵字搜尋群組並撈取"""
    print(f"\n用 {len(SEARCH_KEYWORDS)} 個關鍵字搜尋群組...\n")
    all_found = {}

    for i, kw in enumerate(SEARCH_KEYWORDS):
        print(f"  [{i+1}/{len(SEARCH_KEYWORDS)}] '{kw}'", end="", flush=True)
        try:
            result = await client(SearchRequest(q=kw, limit=100))
            new = 0
            for chat in result.chats:
                if isinstance(chat, Channel) and chat.id not in all_found:
                    all_found[chat.id] = (chat, kw)
                    new += 1
            found = len([c for c in result.chats if isinstance(c, Channel)])
            print(f" → {found} 個, 新增 {new}") if found else print(" → 0")
        except FloodWaitError as e:
            print(f" → 限速 {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f" → {type(e).__name__}")
        await asyncio.sleep(1.2)

    print(f"\n共找到 {len(all_found)} 個群組，檢查可抓取性...\n")

    scrapable = []
    for i, (gid, (entity, kw)) in enumerate(all_found.items()):
        print(f"  [{i+1}/{len(all_found)}] {entity.title[:40]:<40s}", end=" ", flush=True)
        ok, status, count = await check_scrapable(client, entity)
        print(f"{'✓' if ok else '✗'} {status}")
        if ok:
            scrapable.append(entity)
        await asyncio.sleep(0.5)

    print(f"\n可抓取: {len(scrapable)} 個群組")
    if not scrapable:
        return []

    confirm = input(f"\n開始撈取 {len(scrapable)} 個群組？(y/n): ").strip().lower()
    if confirm != "y":
        return []

    scraped_ids = get_scraped_group_ids()
    all_members = []
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for entity in scrapable:
        if str(entity.id) in scraped_ids:
            print(f"  ⏭ 已爬過: {entity.title}")
            continue
        print(f"  📥 {entity.title}...", end="", flush=True)
        try:
            members = await scrape_members(client, entity, entity.title, entity.id)
            all_members.extend(members)
            print(f" {len(members)} 位")
        except Exception as e:
            print(f" 失敗: {e}")
        await asyncio.sleep(1)

    if all_members:
        filepath = save_members_csv(all_members, f"search_{timestamp}", DATA_DIR)
        print(f"\n搜尋結果已儲存: {filepath}")

    return all_members


# ============================================================
# 模式 5：從訊息撈發言者
# ============================================================

async def mode_message_senders(client):
    """從群組訊息中撈取所有發言者的 ID 和 username"""
    dialogs = await client.get_dialogs()
    all_chats = [d for d in dialogs if d.is_group or d.is_channel]

    # 只顯示群組（megagroup），過濾掉頻道
    groups = [d for d in all_chats if getattr(d.entity, "megagroup", False)]

    from menu_ui import select_multi
    options = []
    for d in groups:
        count = getattr(d.entity, "participants_count", 0) or 0
        options.append(f"👥 {d.title[:40]} ({count}人)")

    indices = select_multi("選擇群組（空白鍵勾選，a 全選，Enter 確認）", options)
    selected = [groups[i] for i in indices]

    if not selected:
        print("  未選擇群組")
        return []

    limit_input = input("每個群組掃描幾則訊息？(預設 500, 0=全部): ").strip()
    limit = int(limit_input) if limit_input.isdigit() else 500
    if limit == 0:
        limit = None

    all_members = []

    for d in selected:
        entity = d.entity
        title = d.title
        print(f"\n  📥 掃描訊息: {title}")

        # 先撈管理員 ID，用來過濾
        admin_ids = set()
        try:
            from telethon.tl.functions.channels import GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsAdmins
            admins = await client(GetParticipantsRequest(
                channel=entity, filter=ChannelParticipantsAdmins(),
                offset=0, limit=100, hash=0))
            for u in admins.users:
                admin_ids.add(u.id)
            print(f"    已識別 {len(admin_ids)} 位管理員（將排除）")
        except Exception:
            print(f"    無法取得管理員列表（不影響撈取）")

        seen_ids = set()
        members = []
        bot_count = 0
        admin_count = 0
        msg_count = 0

        async for msg in client.iter_messages(entity, limit=limit):
            msg_count += 1
            if msg_count % 200 == 0:
                print(f"    已掃描 {msg_count} 則訊息，找到 {len(members)} 位發言者...")

            if not msg.sender:
                continue

            sender = msg.sender
            sender_id = msg.sender_id

            if not sender_id or sender_id in seen_ids:
                continue

            # 跳過 bot
            is_bot = getattr(sender, "bot", False)
            if is_bot:
                bot_count += 1
                seen_ids.add(sender_id)
                continue

            # 跳過管理員
            if sender_id in admin_ids:
                admin_count += 1
                seen_ids.add(sender_id)
                continue

            # 跳過茶莊工作人員（名字含關鍵字）
            display_name = (
                (getattr(sender, "first_name", "") or "")
                + (getattr(sender, "last_name", "") or "")
                + (getattr(sender, "username", "") or "")
            ).lower()
            staff_keywords = [
                "客服", "經紀", "報班", "預約", "訂位", "接單",
                "小幫手", "助理", "管理", "官方", "service",
                "support", "admin", "boss", "老闆",
                "茶莊", "茶行", "外送", "line",
            ]
            is_staff = any(kw in display_name for kw in staff_keywords)
            if is_staff:
                admin_count += 1  # 算在管理/內部人員一起
                seen_ids.add(sender_id)
                continue

            seen_ids.add(sender_id)

            username = getattr(sender, "username", "") or ""
            first_name = getattr(sender, "first_name", "") or ""
            last_name = getattr(sender, "last_name", "") or ""
            phone = getattr(sender, "phone", "") or ""

            members.append({
                "user_id": sender_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "phone": phone,
                "is_bot": False,
                "source_group": title,
                "source_group_id": entity.id,
            })

        print(f"    完成: 掃描 {msg_count} 則訊息，撈到 {len(members)} 位發言者")
        print(f"    已過濾: 管理員/工作人員 {admin_count} 位，機器人 {bot_count} 位")

        if members:
            filepath = save_members_csv(members, f"senders_{safe_filename(title)}", DATA_DIR)
            if filepath:
                print(f"    已儲存: {filepath}")
            all_members.extend(members)

        with_un = len([m for m in members if m["username"]])
        print(f"    有 username: {with_un} 位，無 username: {len(members) - with_un} 位")

    return all_members


# ============================================================
# 合併去重
# ============================================================

def merge_and_dedup():
    """合併 data/ 內所有成員 CSV 並去重"""
    print("\n合併去重中...")
    exclude = ["search_report", "msg_", "dm_sent_log", "all_members",
               "members_with", "members_no"]

    files = []
    for f in glob.glob(os.path.join(DATA_DIR, "*.csv")):
        basename = os.path.basename(f)
        if any(ex in basename for ex in exclude):
            continue
        files.append(f)

    if not files:
        print("  沒有找到成員 CSV")
        return

    all_members = []
    for f in sorted(files):
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if "user_id" not in (reader.fieldnames or []):
                    continue
                rows = list(reader)
                all_members.extend(rows)
                print(f"  [{len(rows):>6} 位] {os.path.basename(f)}")
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

    members = list(unique.values())
    fieldnames = ["user_id", "username", "first_name", "last_name",
                  "phone", "is_bot", "source_group", "source_group_id"]

    # 全部
    path_all = os.path.join(TOOLKIT_DIR, "all_members.csv")
    with open(path_all, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(members)

    # 有 username
    has_un = [m for m in members if m.get("username")]
    path_with = os.path.join(TOOLKIT_DIR, "members_with_username.csv")
    with open(path_with, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(has_un)

    # 無 username
    no_un = [m for m in members if not m.get("username")]
    path_without = os.path.join(TOOLKIT_DIR, "members_no_username.csv")
    with open(path_without, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(no_un)

    has_id = [m for m in no_un if m.get("user_id")]
    can_send = len(has_un) + len(has_id)

    print(f"\n統計：")
    print(f"  全部:          {len(members)} 位 → all_members.csv")
    print(f"  可發送:        {can_send} 位（有 username {len(has_un)} + 有 user_id {len(has_id)}）")
    print(f"  有 username:   {len(has_un)} 位 → members_with_username.csv")
    print(f"  無 username:   {len(no_un)} 位 → members_no_username.csv")


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  Telegram 群組成員撈取工具")
    print("=" * 55)
    print()
    print("  [1] 撈單一群組成員")
    print("  [2] 批量撈所有已加入的群組")
    print("  [3] 關鍵字搜尋群組並撈取")
    print("  [4] 只做合併去重（不撈取）")
    print("  [5] 從訊息撈發言者（撈不到成員時用這個）")
    print()

    mode = input("選擇模式 (1/2/3/4/5): ").strip()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"\n✅ 登入: {me.first_name} (@{me.username})\n")

    try:
        if mode == "1":
            await mode_single(client)
        elif mode == "2":
            await mode_batch(client)
        elif mode == "3":
            await mode_search(client)
        elif mode == "4":
            pass
        elif mode == "5":
            await mode_message_senders(client)
        else:
            print("無效選擇")
            await client.disconnect()
            return

        # 自動合併去重
        merge_and_dedup()

    except KeyboardInterrupt:
        print("\n\n使用者中斷")
    finally:
        await client.disconnect()
        print("\n完成!")
        input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
