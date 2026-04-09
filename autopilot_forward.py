"""
內容轉發 託管模式
24 小時即時監聽來源群組，自動重發到你的頻道
"""

import asyncio
import os
import re
import sys

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)

from config import API_ID, API_HASH, SESSION_NAME
from telethon import TelegramClient, events
from datetime import datetime

BOT_USERNAME = "teaprincess_bot"
FOOTER = ("\n\n━━━━━━━━━━━━━━━\n🍵 想約這位佳麗？點擊下方從茶王客服，找茶莊的客服了解"
          "\n👉 @teaprincess_bot\n📌 聯繫時請說是「茶王推薦」的唷！")
TG_LINKS = [r"https?://t\.me/\+?\w+/?[\w]*", r"https?://telegram\.me/\+?\w+/?[\w]*", r"@[\w]{5,}"]
BLOCK_KW = ["福利", "買一送一", "半價", "現金劵", "現金券", "VIP", "vip", "免費無套",
            "名單", "LADIES LIST", "預約制", "BOOKINGS", "gleezy", "jkf699"]
TEMP_DIR = os.path.join(TOOLKIT_DIR, "_temp_media")


def should_skip(text):
    if not text:
        return False
    for kw in BLOCK_KW:
        if kw in text:
            return True
    for marker in ["【", "🔺", "➡️"]:
        if text.count(marker) >= 5:
            return True
    return False


def replace_links(text):
    if not text:
        return text
    bot_link = f"https://t.me/{BOT_USERNAME}"
    for pattern in TG_LINKS:
        for match in re.findall(pattern, text):
            if BOT_USERNAME not in match:
                text = text.replace(match, f"👉 諮詢客服: {bot_link}")
    return text


async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       內容轉發 託管模式                        ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"  ✅ 登入: {me.first_name}\n")

    dialogs = await client.get_dialogs()
    groups = [d for d in dialogs if d.is_group or d.is_channel]

    print("  來源群組：")
    for i, d in enumerate(groups):
        icon = "📢" if getattr(d.entity, "broadcast", False) else "👥"
        print(f"    [{i+1:3d}] {icon} {d.title[:45]}")

    source_input = input("\n  輸入來源編號（逗號分隔）: ").strip()
    source_ids = []
    for n in source_input.split(","):
        try:
            source_ids.append(groups[int(n.strip()) - 1].entity.id)
        except (ValueError, IndexError):
            pass

    if not source_ids:
        print("  未選擇來源")
        return

    target_input = input("  輸入你的頻道（username 或 ID）: ").strip()
    if target_input.lstrip("-").isdigit():
        target_input = int(target_input)

    target = await client.get_entity(target_input)

    print(f"\n  📢 即時監聽中: {len(source_ids)} 個來源 → {target.title}")
    print(f"  按 Ctrl+C 停止\n")

    count = 0

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count
        msg = event.message
        text = (msg.text or "").strip()
        if should_skip(text):
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  [{ts}] ⏭ 已過濾")
            return
        text = replace_links(text)
        text = (text + FOOTER) if text else FOOTER.strip()
        try:
            if msg.media:
                os.makedirs(TEMP_DIR, exist_ok=True)
                fp = await client.download_media(msg, file=TEMP_DIR)
                if fp:
                    await client.send_file(target, fp, caption=text)
                    os.remove(fp)
                else:
                    await client.send_message(target, text)
            elif text:
                await client.send_message(target, text)
            count += 1
            ts = datetime.now().strftime("%H:%M:%S")
            print(f"  [{ts}] ✅ #{count} → {(msg.text or '[媒體]')[:40]}")
        except Exception as e:
            print(f"  ❌ {e}")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print(f"\n\n  停止。共轉發 {count} 則")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
