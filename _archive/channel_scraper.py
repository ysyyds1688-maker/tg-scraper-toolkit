"""
批次爬取 Telegram 頻道/群組的訊息內容
自動偵測頻道類型（broadcast），批次抓取所有訊息
"""

import asyncio
import csv
import os
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 設定：每個頻道最多抓幾則訊息（0 = 全部）
MAX_MESSAGES = 0


async def scrape_messages(client, dialog):
    """抓取頻道/群組的所有訊息"""
    entity = dialog.entity
    messages = []
    sender_ids = set()
    count = 0

    async for msg in client.iter_messages(entity, limit=MAX_MESSAGES or None):
        row = {
            "message_id": msg.id,
            "date": msg.date.strftime("%Y-%m-%d %H:%M:%S") if msg.date else "",
            "sender_id": "",
            "sender_name": "",
            "text": (msg.text or "")[:2000],  # 限制長度避免太大
            "views": getattr(msg, "views", ""),
            "forwards": getattr(msg, "forwards", ""),
            "has_media": bool(msg.media),
            "media_type": type(msg.media).__name__ if msg.media else "",
            "reply_to": msg.reply_to_msg_id if msg.reply_to else "",
        }

        # 取得發送者資訊
        if msg.sender:
            row["sender_id"] = msg.sender_id
            if hasattr(msg.sender, "first_name"):
                name_parts = [msg.sender.first_name or "", msg.sender.last_name or ""]
                row["sender_name"] = " ".join(p for p in name_parts if p)
            elif hasattr(msg.sender, "title"):
                row["sender_name"] = msg.sender.title
            if msg.sender_id:
                sender_ids.add(msg.sender_id)

        messages.append(row)
        count += 1
        if count % 500 == 0:
            print(f"    已抓取 {count} 則訊息...")

    return messages, sender_ids


def save_messages_csv(messages, group_name, output_dir):
    """儲存訊息為 CSV"""
    if not messages:
        return None
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in group_name)[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"msg_{safe_name}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=messages[0].keys())
        writer.writeheader()
        writer.writerows(messages)

    return filepath


def save_senders_csv(senders_info, group_name, output_dir):
    """儲存發言者列表為 CSV"""
    if not senders_info:
        return None
    safe_name = "".join(c if c.isalnum() or c in "_ -" else "_" for c in group_name)[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"senders_{safe_name}_{timestamp}.csv"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=senders_info[0].keys())
        writer.writeheader()
        writer.writerows(senders_info)

    return filepath


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("正在掃描所有群組/頻道...\n")
    dialogs = await client.get_dialogs()

    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)

    # 列出所有頻道類型
    channels = []
    print(f"{'':>4} {'群組名稱':<45} {'類型':<10} {'成員數':>8}")
    print("-" * 75)

    for i, d in enumerate(groups):
        entity = d.entity
        is_broadcast = getattr(entity, "broadcast", False)
        is_mega = getattr(entity, "megagroup", False)
        count = getattr(entity, "participants_count", 0) or 0

        if is_broadcast:
            type_str = "頻道"
        elif is_mega:
            type_str = "超級群組"
        else:
            type_str = "普通群組"

        marker = " "
        if is_broadcast:
            marker = "📢"
            channels.append((i, d))
        elif is_mega:
            marker = "👥"

        print(f"  [{i+1:2d}] {marker} {d.title[:42]:<42s} {type_str:<10} {count:>6d} 人")

    print(f"\n偵測到 {len(channels)} 個頻道 (📢)")

    # 選擇模式
    print("\n選擇要抓取的目標:")
    print("  [1] 只抓所有頻道 (📢)")
    print("  [2] 全部都抓 (📢 + 👥)")
    print("  [3] 手動選擇 (輸入編號)")
    mode = input("\n選擇模式 (1/2/3): ").strip()

    targets = []
    if mode == "1":
        targets = [d for _, d in channels]
    elif mode == "2":
        targets = groups
    elif mode == "3":
        nums = input("輸入編號，用逗號分隔 (例: 6,8,10): ").strip()
        indices = [int(n.strip()) - 1 for n in nums.split(",")]
        targets = [groups[i] for i in indices if 0 <= i < len(groups)]
    else:
        print("無效選擇")
        await client.disconnect()
        return

    if not targets:
        print("沒有選擇任何目標")
        await client.disconnect()
        return

    print(f"\n即將抓取 {len(targets)} 個群組/頻道的訊息:")
    for d in targets:
        print(f"  - {d.title}")

    confirm = input(f"\n確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        await client.disconnect()
        return

    # 開始批次抓取
    print(f"\n開始抓取，儲存至: {OUTPUT_DIR}\n")
    total_msgs = 0
    total_senders = 0

    for d in targets:
        print(f"📥 抓取: {d.title}")
        try:
            messages, sender_ids = await scrape_messages(client, d)

            # 儲存訊息
            msg_path = save_messages_csv(messages, d.title, OUTPUT_DIR)
            print(f"    訊息: {len(messages)} 則 → {msg_path}")
            total_msgs += len(messages)

            # 從訊息中提取不重複的發言者資訊
            senders_map = {}
            for msg in messages:
                sid = msg["sender_id"]
                if sid and sid not in senders_map:
                    senders_map[sid] = {
                        "sender_id": sid,
                        "sender_name": msg["sender_name"],
                        "message_count": 0,
                        "first_seen": msg["date"],
                        "last_seen": msg["date"],
                    }
                if sid and sid in senders_map:
                    senders_map[sid]["message_count"] += 1
                    senders_map[sid]["last_seen"] = msg["date"]

            senders_info = list(senders_map.values())
            if senders_info:
                sender_path = save_senders_csv(senders_info, d.title, OUTPUT_DIR)
                print(f"    發言者: {len(senders_info)} 位 → {sender_path}")
                total_senders += len(senders_info)

        except Exception as e:
            print(f"    失敗: {e}")

        await asyncio.sleep(1)

    print(f"\n{'='*60}")
    print(f"全部完成!")
    print(f"  總訊息數: {total_msgs}")
    print(f"  總發言者: {total_senders}")
    print(f"  儲存位置: {OUTPUT_DIR}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
