"""
批次掃描並抓取所有可爬取的 Telegram 群組成員
自動篩選：megagroup + can_view_participants + 非管理員可抓取
"""

import asyncio
import csv
import os
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, get_scraped_group_ids
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch
from telethon.errors import ChatAdminRequiredError


# 輸出資料夾
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


async def check_scrapable(client, dialog):
    """檢查群組是否可抓取，回傳 (可抓取, 原因, 預估數量)"""
    entity = dialog.entity

    # 必須是 megagroup（不是頻道）
    if not getattr(entity, "megagroup", False):
        return False, "頻道/非超級群組", 0

    # 檢查 can_view_participants
    try:
        full = await client(GetFullChannelRequest(entity))
        can_view = getattr(full.full_chat, "can_view_participants", False)
        count = getattr(full.full_chat, "participants_count", 0)
        if not can_view:
            return False, "管理員禁止查看成員", count
    except Exception as e:
        return False, f"無法取得資訊: {e}", 0

    # 測試實際能抓到多少
    try:
        test = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=0,
            limit=10,
            hash=0,
        ))
        if test.count > 0 and test.count == count:
            return True, "可完整抓取", count
        elif test.count > 100:
            return True, f"可抓取 {test.count}/{count} 位", test.count
        else:
            return False, f"只能抓到 {test.count}/{count} 位（限制過嚴）", test.count
    except ChatAdminRequiredError:
        return False, "需要管理員權限", count
    except Exception as e:
        return False, f"測試失敗: {e}", 0


async def scrape_group(client, dialog):
    """抓取單一群組的所有成員"""
    entity = dialog.entity
    members = []
    seen_ids = set()
    offset = 0

    while True:
        participants = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=offset,
            limit=200,
            hash=0,
        ))

        if not participants.users:
            break

        for user in participants.users:
            if user.id not in seen_ids:
                seen_ids.add(user.id)
                members.append({
                    "user_id": user.id,
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "phone": user.phone or "",
                    "is_bot": user.bot or False,
                })

        offset += len(participants.users)
        if offset >= participants.count:
            break

    return members


def save_csv(members, group_name, output_dir):
    """儲存成 CSV"""
    if not members:
        return None
    # 清理檔名
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in group_name)[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{safe_name}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=members[0].keys())
        writer.writeheader()
        writer.writerows(members)

    return filepath


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("正在掃描所有群組...\n")
    dialogs = await client.get_dialogs()

    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)

    # Phase 1: 掃描所有群組
    scrapable = []
    not_scrapable = []

    for i, d in enumerate(groups):
        ok, reason, count = await check_scrapable(client, d)
        status = "✓" if ok else "✗"
        print(f"  [{i+1:2d}] {status} {d.title[:40]:<40s} | {count:>6d} 人 | {reason}")
        if ok:
            scrapable.append((d, count))
        else:
            not_scrapable.append((d, reason))
        await asyncio.sleep(0.3)

    print(f"\n{'='*60}")
    print(f"可抓取: {len(scrapable)} 個群組")
    print(f"不可抓取: {len(not_scrapable)} 個群組")

    if not scrapable:
        print("沒有可抓取的群組")
        await client.disconnect()
        return

    # Phase 2: 確認後開始抓取
    print(f"\n可抓取的群組:")
    for d, count in scrapable:
        print(f"  - {d.title} ({count} 人)")

    confirm = input(f"\n要開始抓取這 {len(scrapable)} 個群組嗎？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        await client.disconnect()
        return

    # Phase 3: 批次抓取
    scraped_ids = get_scraped_group_ids()
    print(f"\n已爬過的群組: {len(scraped_ids)} 個")
    print(f"開始批次抓取，儲存至: {OUTPUT_DIR}\n")
    total_members = 0

    for d, count in scrapable:
        if str(d.entity.id) in scraped_ids:
            print(f"⏭ 已爬過，跳過: {d.title}")
            continue
        print(f"抓取: {d.title} ({count} 人)...")
        try:
            members = await scrape_group(client, d)
            filepath = save_csv(members, d.title, OUTPUT_DIR)
            total_members += len(members)
            print(f"  → 完成! {len(members)} 位成員 → {filepath}")
        except Exception as e:
            print(f"  → 失敗: {e}")
        await asyncio.sleep(1)  # 避免速率限制

    print(f"\n{'='*60}")
    print(f"全部完成! 共抓取 {total_members} 位成員")
    print(f"檔案儲存在: {OUTPUT_DIR}")

    # 自動合併去重
    print("\n自動合併去重中...")
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
