"""
妹子資料爬取 - 從外送茶/茶妹頻道抓取訊息 + 圖片
輸出：CSV（文字/來源/時間）+ 圖片資料夾
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument,
    DocumentAttributeFilename, DocumentAttributeVideo,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
IMAGES_DIR = os.path.join(OUTPUT_DIR, "images")


def safe_dirname(name):
    """清理資料夾名稱"""
    return "".join(c if c.isalnum() or c in "_ -" else "_" for c in name)[:50].strip("_")


def get_channel_link(entity):
    """取得頻道/群組的公開連結"""
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}"
    return f"https://t.me/c/{entity.id}"


async def download_photo(client, msg, img_dir):
    """下載訊息中的圖片，回傳檔案路徑 or None"""
    if isinstance(msg.media, MessageMediaPhoto):
        try:
            filename = f"{msg.id}.jpg"
            filepath = os.path.join(img_dir, filename)
            await client.download_media(msg, file=filepath)
            return filepath
        except Exception:
            return None

    elif isinstance(msg.media, MessageMediaDocument):
        doc = msg.media.document
        if doc:
            mime = getattr(doc, "mime_type", "") or ""
            if mime.startswith("image/"):
                try:
                    ext = mime.split("/")[-1]
                    if ext == "jpeg":
                        ext = "jpg"
                    filename = f"{msg.id}.{ext}"
                    filepath = os.path.join(img_dir, filename)
                    await client.download_media(msg, file=filepath)
                    return filepath
                except Exception:
                    return None
    return None


async def scrape_channel(client, dialog, max_messages=0):
    """抓取頻道訊息 + 下載圖片，相簿自動合併"""
    entity = dialog.entity
    title = dialog.title
    channel_link = get_channel_link(entity)
    safe_name = safe_dirname(title)

    # 建立圖片資料夾
    img_dir = os.path.join(IMAGES_DIR, safe_name)
    os.makedirs(img_dir, exist_ok=True)

    print(f"  開始掃描: {title}")
    print(f"  頻道連結: {channel_link}")
    print(f"  圖片存至: {img_dir}")
    print()

    # 先收集所有訊息
    raw_messages = []
    msg_count = 0
    async for msg in client.iter_messages(entity, limit=max_messages or None):
        raw_messages.append(msg)
        msg_count += 1
        if msg_count % 200 == 0:
            print(f"    已讀取 {msg_count} 則訊息...")

    # 反轉成時間順序（舊→新），方便處理相簿
    raw_messages.reverse()

    # 按 grouped_id 歸組（相簿），沒有 grouped_id 的獨立一組
    groups = {}  # grouped_id -> [msg, msg, ...]
    singles = []
    for msg in raw_messages:
        gid = getattr(msg, "grouped_id", None)
        if gid:
            if gid not in groups:
                groups[gid] = []
            groups[gid].append(msg)
        else:
            singles.append(msg)

    # 處理所有訊息，輸出合併後的資料
    messages = []
    img_count = 0

    # 處理相簿（多張圖對應同一組文字）
    for gid, group_msgs in groups.items():
        # 找到有文字的那則訊息
        text = ""
        for m in group_msgs:
            if m.text and m.text.strip():
                text = m.text.strip()
                break

        # 下載所有圖片
        photo_paths = []
        all_ids = []
        for m in group_msgs:
            all_ids.append(str(m.id))
            path = await download_photo(client, m, img_dir)
            if path:
                photo_paths.append(path)
                img_count += 1

        first_msg = group_msgs[0]
        row = {
            "message_id": "; ".join(all_ids),
            "message_link": f"{channel_link}/{first_msg.id}",
            "date": first_msg.date.strftime("%Y-%m-%d %H:%M:%S") if first_msg.date else "",
            "text": text,
            "views": getattr(first_msg, "views", ""),
            "forwards": getattr(first_msg, "forwards", ""),
            "channel_name": title,
            "channel_link": channel_link,
            "has_photo": len(photo_paths) > 0,
            "photo_count": len(photo_paths),
            "photo_paths": "; ".join(photo_paths),
            "is_album": True,
        }

        if text or photo_paths:
            messages.append(row)

    # 處理單獨訊息
    for msg in singles:
        photo_path = await download_photo(client, msg, img_dir)
        if photo_path:
            img_count += 1

        row = {
            "message_id": str(msg.id),
            "message_link": f"{channel_link}/{msg.id}",
            "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
            "text": (msg.text or "").strip(),
            "views": getattr(msg, "views", ""),
            "forwards": getattr(msg, "forwards", ""),
            "channel_name": title,
            "channel_link": channel_link,
            "has_photo": photo_path is not None,
            "photo_count": 1 if photo_path else 0,
            "photo_paths": photo_path or "",
            "is_album": False,
        }

        if row["text"] or photo_path:
            messages.append(row)

    # 按時間排序
    messages.sort(key=lambda x: x["date"])

    print(f"    完成! {msg_count} 則訊息，{img_count} 張圖片")
    print(f"    相簿: {len(groups)} 組，單獨: {len([m for m in messages if not m['is_album']])} 則")
    return messages, img_count


def save_csv(messages, channel_name):
    """儲存為 CSV"""
    if not messages:
        return None

    safe_name = safe_dirname(channel_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"girls_{safe_name}_{timestamp}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)

    fieldnames = [
        "message_id", "message_link", "date", "text", "views", "forwards",
        "channel_name", "channel_link", "has_photo", "photo_count",
        "photo_paths", "is_album",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(messages)

    return filepath


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    os.makedirs(IMAGES_DIR, exist_ok=True)

    print("正在載入群組/頻道...\n")
    dialogs = await client.get_dialogs()

    # 列出所有群組/頻道
    all_groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            all_groups.append(d)

    for i, d in enumerate(all_groups):
        entity = d.entity
        kind = "📢" if getattr(entity, "broadcast", False) else "👥"
        count = getattr(entity, "participants_count", 0) or 0
        print(f"  [{i+1:2d}] {kind} {d.title} ({count} 人)")

    print(f"\n選擇要爬取的頻道/群組（逗號分隔，或 a 全部）：")
    choice = input("> ").strip()

    if choice.lower() == "a":
        targets = all_groups
    else:
        indices = [int(n.strip()) - 1 for n in choice.split(",")]
        targets = [all_groups[i] for i in indices if 0 <= i < len(all_groups)]

    if not targets:
        print("沒有選擇任何目標")
        await client.disconnect()
        return

    # 設定抓取數量
    limit_input = input("\n每個頻道最多抓幾則訊息？(0=全部，預設 500): ").strip()
    max_messages = int(limit_input) if limit_input.isdigit() else 500

    print(f"\n即將爬取 {len(targets)} 個頻道/群組")
    print(f"每個最多 {'全部' if max_messages == 0 else f'{max_messages} 則'}訊息")
    print(f"圖片存至: {IMAGES_DIR}\n")

    confirm = input("開始？(y/n): ").strip().lower()
    if confirm != "y":
        await client.disconnect()
        return

    # 開始爬取
    total_messages = 0
    total_images = 0

    for d in targets:
        print(f"\n{'='*55}")
        try:
            messages, img_count = await scrape_channel(client, d, max_messages)
            if messages:
                filepath = save_csv(messages, d.title)
                print(f"    CSV: {filepath}")
                total_messages += len(messages)
                total_images += img_count
        except Exception as e:
            print(f"    失敗: {type(e).__name__}: {e}")
        await asyncio.sleep(1)

    print(f"\n{'='*55}")
    print(f"全部完成!")
    print(f"  總訊息: {total_messages} 筆")
    print(f"  總圖片: {total_images} 張")
    print(f"  圖片位置: {IMAGES_DIR}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
