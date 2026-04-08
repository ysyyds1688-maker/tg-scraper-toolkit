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


async def scrape_channel(client, dialog, max_messages=0):
    """抓取頻道訊息 + 下載圖片"""
    entity = dialog.entity
    title = dialog.title
    channel_link = get_channel_link(entity)
    safe_name = safe_dirname(title)

    # 建立圖片資料夾
    img_dir = os.path.join(IMAGES_DIR, safe_name)
    os.makedirs(img_dir, exist_ok=True)

    messages = []
    img_count = 0
    msg_count = 0

    print(f"  開始掃描: {title}")
    print(f"  頻道連結: {channel_link}")
    print(f"  圖片存至: {img_dir}")
    print()

    async for msg in client.iter_messages(entity, limit=max_messages or None):
        msg_count += 1

        row = {
            "message_id": msg.id,
            "message_link": f"{channel_link}/{msg.id}",
            "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
            "text": (msg.text or "").strip(),
            "views": getattr(msg, "views", ""),
            "forwards": getattr(msg, "forwards", ""),
            "channel_name": title,
            "channel_link": channel_link,
            "has_photo": False,
            "photo_paths": "",
        }

        # 下載圖片
        photo_paths = []

        # 單張圖片
        if isinstance(msg.media, MessageMediaPhoto):
            try:
                filename = f"{msg.id}.jpg"
                filepath = os.path.join(img_dir, filename)
                await client.download_media(msg, file=filepath)
                photo_paths.append(filepath)
                img_count += 1
            except Exception:
                pass

        # 文件類型（可能是圖片或影片）
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
                        photo_paths.append(filepath)
                        img_count += 1
                    except Exception:
                        pass

        # 相簿（grouped media）- Telethon 會分開處理每個 message
        # 所以每則 message 只會有一張圖，相簿的多張圖是多則 message

        if photo_paths:
            row["has_photo"] = True
            row["photo_paths"] = "; ".join(photo_paths)

        # 只保留有內容的訊息（有文字或有圖片）
        if row["text"] or photo_paths:
            messages.append(row)

        if msg_count % 100 == 0:
            print(f"    已處理 {msg_count} 則訊息，{img_count} 張圖片...")

    print(f"    完成! {msg_count} 則訊息，{img_count} 張圖片，{len(messages)} 筆有效資料")
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
        "channel_name", "channel_link", "has_photo", "photo_paths",
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
