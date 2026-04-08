"""
Telegram 訊息轉發工具
功能：
  1. 即時監聽 - 新訊息自動重新發送到目標頻道（不顯示來源）
  2. 歷史批量重發 - 把群組歷史訊息重新發送到頻道
  3. 原始轉發 - 直接轉發（會顯示「轉發自」）
"""

import asyncio
import os
import re
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, TARGET_CHANNEL
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError


# ============================================================
# 設定
# ============================================================

# Bot username（替換原始連結用，留空不替換）
BOT_USERNAME = "teaprincess_bot"

# 每則訊息底部自動加上的導流文字
FOOTER_TEXT = "\n\n━━━━━━━━━━━━━━━\n🍵 想約這位佳麗？點擊下方找茶莊客服\n👉 @teaprincess_bot\n📌 聯繫時請說是「茶王推薦」的唷！"

# Telegram 連結正則
TG_LINK_PATTERNS = [
    r"https?://t\.me/\+?\w+/?[\w]*",
    r"https?://telegram\.me/\+?\w+/?[\w]*",
    r"@[\w]{5,}",
]


# ============================================================
# 工具函式
# ============================================================

def replace_links(text, bot_username):
    """替換原始 TG 連結為 Bot 連結"""
    if not text or not bot_username:
        return text

    bot_link = f"https://t.me/{bot_username}"
    for pattern in TG_LINK_PATTERNS:
        matches = re.findall(pattern, text)
        for match in matches:
            if bot_username not in match:
                text = text.replace(match, f"👉 諮詢客服: {bot_link}")

    # 去重複
    dup = f"👉 諮詢客服: {bot_link}\n👉 諮詢客服: {bot_link}"
    single = f"👉 諮詢客服: {bot_link}"
    while dup in text:
        text = text.replace(dup, single)

    return text


async def list_groups(client):
    """列出所有群組/頻道"""
    dialogs = await client.get_dialogs()
    groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            groups.append(d)

    print(f"\n{'':>4} {'名稱':<45} {'類型':<10} {'成員':>8}")
    print("-" * 75)

    for i, d in enumerate(groups):
        entity = d.entity
        is_broadcast = getattr(entity, "broadcast", False)
        is_mega = getattr(entity, "megagroup", False)
        count = getattr(entity, "participants_count", 0) or 0
        icon = "📢" if is_broadcast else "👥" if is_mega else "💬"
        type_str = "頻道" if is_broadcast else "超級群組" if is_mega else "群組"
        print(f"  [{i+1:3d}] {icon} {d.title[:42]:<42s} {type_str:<10} {count:>6d} 人")

    return groups


async def select_groups(groups, prompt="選擇群組編號（逗號分隔，如 1,3,5）: "):
    nums = input(prompt).strip()
    indices = [int(n.strip()) - 1 for n in nums.split(",")]
    return [groups[i] for i in indices if 0 <= i < len(groups)]


async def get_target(client, target_channel):
    if not target_channel:
        target_channel = input("\n輸入目標頻道（username 或 ID 或連結）: ").strip()
    if target_channel.lstrip("-").isdigit():
        target_channel = int(target_channel)
    entity = await client.get_entity(target_channel)
    print(f"✅ 目標頻道: {entity.title}")
    return entity


TEMP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_temp_media")


async def download_media(client, msg):
    """下載訊息中的媒體到暫存資料夾，回傳檔案路徑"""
    if not msg.media:
        return None
    os.makedirs(TEMP_DIR, exist_ok=True)
    try:
        path = await client.download_media(msg, file=TEMP_DIR)
        return path
    except Exception:
        return None


async def resend_message(client, target, msg, bot_username):
    """重新發送一則訊息（先下載媒體再重新上傳，完全不顯示來源）"""
    text = (msg.text or "").strip()

    if bot_username:
        text = replace_links(text, bot_username)

    # 加上底部導流文字
    text = (text + FOOTER_TEXT) if text else FOOTER_TEXT.strip()

    try:
        if msg.media:
            filepath = await download_media(client, msg)
            if filepath:
                await client.send_file(target, filepath, caption=text)
                os.remove(filepath)
            else:
                await client.send_message(target, text)
        else:
            await client.send_message(target, text)
        return True

    except FloodWaitError as e:
        print(f"    ⚠️  限速 {e.seconds}s，等待中...")
        await asyncio.sleep(e.seconds + 5)
        return await resend_message(client, target, msg, bot_username)
    except Exception as e:
        print(f"    ❌ 發送失敗: {e}")
        return False


async def resend_album(client, target, album_msgs, bot_username):
    """重新發送一組相簿（下載所有圖片再重新上傳）"""
    text = ""
    for m in album_msgs:
        if m.text and m.text.strip():
            text = m.text.strip()
            break

    if bot_username:
        text = replace_links(text, bot_username)

    # 加上底部導流文字
    text = (text + FOOTER_TEXT) if text else FOOTER_TEXT.strip()

    try:
        filepaths = []
        for m in album_msgs:
            if m.media:
                fp = await download_media(client, m)
                if fp:
                    filepaths.append(fp)

        if filepaths:
            await client.send_file(target, filepaths, caption=text or None)
            for fp in filepaths:
                os.remove(fp)
            return True
        return False

    except FloodWaitError as e:
        print(f"    ⚠️  限速 {e.seconds}s，等待中...")
        await asyncio.sleep(e.seconds + 5)
        return await resend_album(client, target, album_msgs, bot_username)
    except Exception as e:
        print(f"    ❌ 相簿發送失敗: {e}")
        return False


# ============================================================
# 模式 1：即時監聽重發（不顯示來源）
# ============================================================

async def mode_realtime(client):
    """即時監聽，用自己帳號重新發送"""
    groups = await list_groups(client)
    sources = await select_groups(groups, "\n選擇要監聽的來源群組（逗號分隔）: ")

    if not sources:
        print("未選擇任何群組")
        return

    target = await get_target(client, TARGET_CHANNEL)

    source_ids = [s.entity.id for s in sources]
    source_names = {s.entity.id: s.title for s in sources}

    # 相簿暫存（grouped_id → [msgs]）
    album_buffer = {}
    album_timers = {}

    print(f"\n即時監聽中... (Ctrl+C 停止)")
    print(f"來源: {', '.join(s.title for s in sources)}")
    print(f"目標: {target.title}")
    print(f"連結替換: {'@' + BOT_USERNAME if BOT_USERNAME else '不替換'}")
    print("-" * 50)

    count = 0

    async def flush_album(grouped_id):
        """延遲後發送完整相簿"""
        nonlocal count
        await asyncio.sleep(2)  # 等 2 秒收齊相簿
        if grouped_id in album_buffer:
            msgs = album_buffer.pop(grouped_id)
            ok = await resend_album(client, target, msgs, BOT_USERNAME)
            if ok:
                count += 1
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"  [{time_str}] #{count} 相簿({len(msgs)}張) ✅")

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count
        msg = event.message
        grouped_id = getattr(msg, "grouped_id", None)

        if grouped_id:
            # 相簿 → 暫存，等收齊再一起發
            if grouped_id not in album_buffer:
                album_buffer[grouped_id] = []
                asyncio.create_task(flush_album(grouped_id))
            album_buffer[grouped_id].append(msg)
        else:
            # 單則訊息
            ok = await resend_message(client, target, msg, BOT_USERNAME)
            if ok:
                count += 1
                source_name = source_names.get(event.chat_id, "未知")
                time_str = datetime.now().strftime("%H:%M:%S")
                preview = (event.text or "[媒體]")[:50]
                print(f"  [{time_str}] #{count} {source_name} → {preview} ✅")

    try:
        await client.run_until_disconnected()
    except KeyboardInterrupt:
        print(f"\n\n停止監聽，共重發 {count} 則訊息")


# ============================================================
# 模式 2：歷史批量重發（不顯示來源）
# ============================================================

async def mode_batch_resend(client):
    """批量重新發送歷史訊息"""
    groups = await list_groups(client)
    sources = await select_groups(groups, "\n選擇來源群組（逗號分隔）: ")

    if not sources:
        print("未選擇任何群組")
        return

    target = await get_target(client, TARGET_CHANNEL)

    limit_input = input("\n每個群組發幾則？(0=全部, 預設 100): ").strip()
    limit = int(limit_input) if limit_input else 100
    if limit == 0:
        limit = None

    delay_input = input("每則間隔秒數？(預設 3): ").strip()
    delay = int(delay_input) if delay_input.isdigit() else 3

    print(f"\n即將從 {len(sources)} 個群組重新發送到 {target.title}")
    print(f"連結替換: {'@' + BOT_USERNAME if BOT_USERNAME else '不替換'}")
    confirm = input("確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        return

    total = 0
    for source in sources:
        print(f"\n📥 來源: {source.title}")
        count = 0

        try:
            # 讀取訊息
            raw_msgs = []
            async for msg in client.iter_messages(source.entity, limit=limit):
                raw_msgs.append(msg)
            raw_msgs.reverse()  # 舊→新

            # 按 grouped_id 分組
            i = 0
            while i < len(raw_msgs):
                msg = raw_msgs[i]
                grouped_id = getattr(msg, "grouped_id", None)

                if grouped_id:
                    # 收集同一相簿的所有訊息
                    album = [msg]
                    j = i + 1
                    while j < len(raw_msgs) and getattr(raw_msgs[j], "grouped_id", None) == grouped_id:
                        album.append(raw_msgs[j])
                        j += 1

                    ok = await resend_album(client, target, album, BOT_USERNAME)
                    if ok:
                        count += 1
                        print(f"    ✅ 相簿({len(album)}張)")
                    i = j
                else:
                    ok = await resend_message(client, target, msg, BOT_USERNAME)
                    if ok:
                        count += 1
                        preview = (msg.text or "[媒體]")[:40]
                        if count % 10 == 0 or count <= 3:
                            print(f"    ✅ #{count} {preview}")
                    i += 1

                await asyncio.sleep(delay)

            print(f"    完成: {count} 則")
            total += count

        except Exception as e:
            print(f"    ❌ 失敗: {e}")

    print(f"\n{'='*50}")
    print(f"全部完成! 共重新發送 {total} 則訊息")


# ============================================================
# 模式 3：原始轉發（會顯示來源）
# ============================================================

async def mode_forward(client):
    """直接轉發（顯示「轉發自」）"""
    groups = await list_groups(client)
    sources = await select_groups(groups, "\n選擇來源群組（逗號分隔）: ")

    if not sources:
        print("未選擇任何群組")
        return

    target = await get_target(client, TARGET_CHANNEL)

    limit_input = input("\n每個群組轉發幾則？(0=全部, 預設 100): ").strip()
    limit = int(limit_input) if limit_input else 100
    if limit == 0:
        limit = None

    confirm = input(f"\n確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        return

    total = 0
    for source in sources:
        print(f"\n📥 轉發: {source.title}")
        count = 0
        try:
            messages = []
            async for msg in client.iter_messages(source.entity, limit=limit):
                messages.append(msg)
            messages.reverse()

            for msg in messages:
                try:
                    await client.forward_messages(target, msg)
                    count += 1
                    await asyncio.sleep(0.5)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                    await client.forward_messages(target, msg)
                    count += 1
                except Exception:
                    pass

            print(f"    ✅ 完成: {count} 則")
            total += count
        except Exception as e:
            print(f"    ❌ 失敗: {e}")

    print(f"\n全部完成! 共轉發 {total} 則")


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  Telegram 訊息轉發工具")
    print("=" * 55)
    print()
    print("  [1] 即時監聽 - 新訊息自動重發（不顯示來源）")
    print("  [2] 歷史批量重發（不顯示來源，連結替換為 Bot）")
    print("  [3] 原始轉發（會顯示「轉發自」）")
    print()

    mode = input("選擇模式 (1/2/3): ").strip()

    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"\n✅ 登入: {me.first_name} (@{me.username})")

    try:
        if mode == "1":
            await mode_realtime(client)
        elif mode == "2":
            await mode_batch_resend(client)
        elif mode == "3":
            await mode_forward(client)
        else:
            print("無效選擇")
    except KeyboardInterrupt:
        print("\n\n使用者中斷")
    finally:
        await client.disconnect()
        print("\n完成!")


if __name__ == "__main__":
    asyncio.run(main())
