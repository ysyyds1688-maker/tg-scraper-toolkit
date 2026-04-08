"""
Telegram 群組成員列表爬取腳本
使用前請先：
1. 到 https://my.telegram.org 取得 api_id 和 api_hash
2. pip install telethon
"""

import asyncio
import csv
import os
import string
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.errors import ChatAdminRequiredError
from telethon.tl.functions.channels import GetParticipantsRequest
from telethon.tl.types import ChannelParticipantsSearch

# ============ 設定區 ============
# ================================


async def get_group_members(client: TelegramClient, group_link: str):
    """取得指定群組的所有成員"""
    entity = await client.get_entity(group_link)
    print(f"群組名稱: {entity.title}")
    print(f"群組 ID: {entity.id}")
    print("正在抓取成員列表...")

    seen_ids = set()
    members = []

    # 先嘗試直接抓取（需要管理員權限）
    try:
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
            print(f"  已抓取 {len(members)} 位成員...")
            if offset >= participants.count:
                break

    except ChatAdminRequiredError:
        print("  非管理員，改用逐字搜尋模式（較慢但不需權限）...")
        # 用不同字母/數字搜尋來收集成員
        search_chars = list(string.ascii_lowercase) + list(string.digits) + [
            "а", "б", "в", "г", "д", "е", "ж", "з", "и", "к", "л", "м",
            "н", "о", "п", "р", "с", "т", "у", "ф", "х", "ц", "ч", "ш",
            "щ", "э", "ю", "я",  # 俄文常見字母
            "的", "是", "我", "不", "了", "人", "在", "有", "這",  # 中文常見字
            "_", ".", "-",
        ]

        for i, char in enumerate(search_chars):
            try:
                participants = await client(GetParticipantsRequest(
                    channel=entity,
                    filter=ChannelParticipantsSearch(char),
                    offset=0,
                    limit=200,
                    hash=0,
                ))
                new_count = 0
                for user in participants.users:
                    if user.id not in seen_ids:
                        seen_ids.add(user.id)
                        new_count += 1
                        members.append({
                            "user_id": user.id,
                            "username": user.username or "",
                            "first_name": user.first_name or "",
                            "last_name": user.last_name or "",
                            "phone": user.phone or "",
                            "is_bot": user.bot or False,
                        })
                if new_count > 0:
                    print(f"  搜尋 '{char}' → 新增 {new_count} 位，累計 {len(members)} 位")
                await asyncio.sleep(0.5)  # 避免觸發速率限制
            except ChatAdminRequiredError:
                print("  此群組完全禁止非管理員查詢成員，無法繼續。")
                break
            except Exception as e:
                print(f"  搜尋 '{char}' 時出錯: {e}")
                continue

    print(f"總共抓取 {len(members)} 位不重複成員")
    return members


def save_to_csv(members: list, filename: str):
    """將成員列表存成 CSV"""
    if not members:
        print("沒有成員資料可儲存")
        return

    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=members[0].keys())
        writer.writeheader()
        writer.writerows(members)

    print(f"已儲存至 {filename}")


async def main():
    if API_ID == 0 or API_HASH == "":
        print("請先設定 API_ID 和 API_HASH")
        print("到 https://my.telegram.org 申請")
        sys.exit(1)

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    # 列出你加入的所有群組 / 頻道
    print("\n你加入的群組 / 頻道：")
    print("-" * 50)
    dialogs = await client.get_dialogs()
    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)
            print(f"  [{len(groups)}] {d.title}")

    if not groups:
        print("找不到任何群組")
        await client.disconnect()
        return

    # 讓使用者選擇
    choice = input("\n輸入群組編號 (或直接貼群組連結): ").strip()

    if choice.startswith("http") or choice.startswith("@") or choice.startswith("t.me"):
        group_link = choice
    else:
        idx = int(choice) - 1
        group_link = groups[idx]

    members = await get_group_members(client, group_link)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"tg_members_{timestamp}.csv"
    save_to_csv(members, filename)

    # 自動合併去重
    print("\n自動合併去重中...")
    import subprocess
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
