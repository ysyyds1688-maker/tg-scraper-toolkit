"""
內容轉發 託管模式
24 小時即時監聽來源群組，自動重發到你的頻道
防重複機制：
  1. 記錄已轉發的 message_id（不重複轉發同一則）
  2. 內容指紋比對（同樣的文字內容不重複發，即使來自不同群組）
"""

import asyncio
import hashlib
import json
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

# 已轉發記錄
FORWARD_LOG = os.path.join(TOOLKIT_DIR, "forward_log.json")


# ============================================================
# 防重複
# ============================================================

def load_forward_log():
    """載入已轉發記錄"""
    if not os.path.exists(FORWARD_LOG):
        return {"message_ids": [], "content_hashes": []}
    with open(FORWARD_LOG, "r", encoding="utf-8") as f:
        data = json.load(f)
    # 只保留最近 10000 筆，避免檔案太大
    data["message_ids"] = data.get("message_ids", [])[-10000:]
    data["content_hashes"] = data.get("content_hashes", [])[-10000:]
    return data


def save_forward_log(data):
    with open(FORWARD_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_content_hash(text):
    """取得文字內容的指紋（去除連結和表情後比對）"""
    if not text:
        return None
    # 去除連結、表情、空白，只留核心文字
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"@\w+", "", clean)
    clean = re.sub(r"[^\w\u4e00-\u9fff]", "", clean)  # 只留中英文和數字
    if len(clean) < 10:  # 太短的不比對
        return None
    return hashlib.md5(clean.encode()).hexdigest()


def is_duplicate(fwd_log, chat_id, msg_id, text):
    """檢查是否重複"""
    # 1. 檢查 message_id（同群組同訊息）
    key = f"{chat_id}:{msg_id}"
    if key in fwd_log["message_ids"]:
        return True

    # 2. 檢查內容指紋（不同群組但同樣內容）
    content_hash = get_content_hash(text)
    if content_hash and content_hash in fwd_log["content_hashes"]:
        return True

    return False


def mark_forwarded(fwd_log, chat_id, msg_id, text):
    """標記為已轉發"""
    key = f"{chat_id}:{msg_id}"
    fwd_log["message_ids"].append(key)

    content_hash = get_content_hash(text)
    if content_hash:
        fwd_log["content_hashes"].append(content_hash)

    save_forward_log(fwd_log)


# ============================================================
# 過濾/替換
# ============================================================

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


# ============================================================
# 主程式
# ============================================================

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

    # 載入已轉發記錄
    fwd_log = load_forward_log()
    already = len(fwd_log["message_ids"])

    print(f"\n  📢 即時監聽中: {len(source_ids)} 個來源 → {target.title}")
    print(f"  📝 已轉發記錄: {already} 則（重複的會自動跳過）")
    print(f"  按 Ctrl+C 停止\n")

    count = 0
    skipped_dup = 0

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count, skipped_dup
        msg = event.message
        text = (msg.text or "").strip()
        ts = datetime.now().strftime("%H:%M:%S")

        # 過濾福利/名單
        if should_skip(text):
            print(f"  [{ts}] ⏭ 過濾（福利/名單）")
            return

        # 檢查重複
        if is_duplicate(fwd_log, event.chat_id, msg.id, text):
            skipped_dup += 1
            preview = text[:30] if text else "[媒體]"
            print(f"  [{ts}] ⏭ 重複跳過: {preview}...")
            return

        # 替換連結 + 加底部文字
        original_text = text
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
            mark_forwarded(fwd_log, event.chat_id, msg.id, original_text)
            preview = (original_text or "[媒體]")[:40]
            print(f"  [{ts}] ✅ #{count} → {preview}")

        except Exception as e:
            print(f"  [{ts}] ❌ {e}")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print(f"\n\n  停止。轉發 {count} 則，跳過重複 {skipped_dup} 則")

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
