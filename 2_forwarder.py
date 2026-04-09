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

import hashlib
import json

from config import API_ID, API_HASH, SESSION_NAME, TARGET_CHANNEL
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError


# ============================================================
# 設定
# ============================================================

BOT_USERNAME = "teaprincess_bot"
FOOTER_TEXT = "\n\n━━━━━━━━━━━━━━━\n🍵 想約這位佳麗？點擊下方從茶王客服，找茶莊的客服了解\n👉 @teaprincess_bot\n📌 聯繫時請說是「茶王推薦」的唷！"
FORWARD_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "forward_log.json")


# ============================================================
# 防重複
# ============================================================

def load_forward_log():
    if not os.path.exists(FORWARD_LOG):
        return {"message_ids": [], "content_hashes": [], "last_msg_id": {}}
    with open(FORWARD_LOG, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["message_ids"] = data.get("message_ids", [])[-10000:]
    data["content_hashes"] = data.get("content_hashes", [])[-10000:]
    # 自動從 message_ids 推算 last_msg_id（如果沒有的話）
    if "last_msg_id" not in data or not data["last_msg_id"]:
        last = {}
        for mid in data["message_ids"]:
            parts = mid.split(":")
            if len(parts) == 2:
                chat_id, msg_id = parts[0], int(parts[1])
                if chat_id not in last or msg_id > last[chat_id]:
                    last[chat_id] = msg_id
        data["last_msg_id"] = {k: v for k, v in last.items()}
        save_forward_log(data)
    return data


def save_forward_log(data):
    with open(FORWARD_LOG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def get_content_hash(text):
    if not text:
        return None
    clean = re.sub(r"https?://\S+", "", text)
    clean = re.sub(r"@\w+", "", clean)
    clean = re.sub(r"[^\w\u4e00-\u9fff]", "", clean)
    if len(clean) < 10:
        return None
    return hashlib.md5(clean.encode()).hexdigest()


def is_duplicate(fwd_log, chat_id, msg_id, text):
    key = f"{chat_id}:{msg_id}"
    if key in fwd_log["message_ids"]:
        return True
    h = get_content_hash(text)
    if h and h in fwd_log["content_hashes"]:
        return True
    return False


def mark_forwarded(fwd_log, chat_id, msg_id, text):
    fwd_log["message_ids"].append(f"{chat_id}:{msg_id}")
    h = get_content_hash(text)
    if h:
        fwd_log["content_hashes"].append(h)
    # 記錄每個群組最後轉發的 message_id
    if "last_msg_id" not in fwd_log:
        fwd_log["last_msg_id"] = {}
    fwd_log["last_msg_id"][str(chat_id)] = msg_id
    save_forward_log(fwd_log)


def get_last_forwarded_id(fwd_log, chat_id):
    """取得某群組上次轉發到哪一則"""
    return fwd_log.get("last_msg_id", {}).get(str(chat_id), 0)

# Telegram 連結正則
TG_LINK_PATTERNS = [
    r"https?://t\.me/\+?\w+/?[\w]*",
    r"https?://telegram\.me/\+?\w+/?[\w]*",
    r"@[\w]{5,}",
]

# ============================================================
# 訊息過濾（不轉發的內容）
# ============================================================

# 包含這些關鍵字的訊息不轉發
BLOCK_KEYWORDS = [
    # 福利宣傳類
    "福利", "買一送一", "半價", "現金劵", "現金券", "VIP", "vip",
    "免費無套", "免車資", "免房費", "立減", "消費4000", "消費6000",
    "消費10000", "消費12000", "消費18000", "消費24000", "消費30000",
    "消費36000", "今日消費", "領取以下", "送原味", "自慰影片",
    "一日伴遊", "雙飛免費", "升級茶坊", "會員卡", "體驗高中",
    "炮友", "送長期",
    # 名單清單類
    "名單", "LADIES LIST", "ladies list", "預約制",
    "BOOKINGS", "bookings",
    # 推廣/廣告類
    "推廣", "合作的朋友", "禁止將價位截圖", "不定時發放",
    "加入思思", "喝茶不迷路", "一鍵訂閱", "新客必讀",
    "暗黑素人", "性福小天地",
    # 外部連結推廣
    "gleezy.net", "gleezy.top", "jkf699",
]

# 包含超過這個數量的地區標記就判定為名單
LIST_MARKERS = ["【", "🔺", "➡️"]
LIST_THRESHOLD = 5  # 超過 5 個就判定為名單


def should_skip(text):
    """判斷這則訊息是否應該跳過（不轉發）"""
    if not text:
        return False

    # 檢查關鍵字
    for kw in BLOCK_KEYWORDS:
        if kw in text:
            return True

    # 檢查是否為名單格式（大量 🔺 或 【地區】）
    for marker in LIST_MARKERS:
        if text.count(marker) >= LIST_THRESHOLD:
            return True

    return False


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

    # 過濾不要的訊息
    if should_skip(text):
        return "skipped"

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

    # 過濾不要的訊息
    if should_skip(text):
        return "skipped"

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
            if ok == "skipped":
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"  [{time_str}] ⏭ 相簿已過濾（福利/名單）")
            elif ok:
                count += 1
                time_str = datetime.now().strftime("%H:%M:%S")
                print(f"  [{time_str}] #{count} 相簿({len(msgs)}張) ✅")

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count
        msg = event.message
        grouped_id = getattr(msg, "grouped_id", None)

        if grouped_id:
            if grouped_id not in album_buffer:
                album_buffer[grouped_id] = []
                asyncio.create_task(flush_album(grouped_id))
            album_buffer[grouped_id].append(msg)
        else:
            ok = await resend_message(client, target, msg, BOT_USERNAME)
            if ok == "skipped":
                time_str = datetime.now().strftime("%H:%M:%S")
                preview = (event.text or "")[:30]
                print(f"  [{time_str}] ⏭ 已過濾: {preview}...")
            elif ok:
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

    want_input = input("\n每個群組要成功轉發幾則？(0=全部, 預設 10): ").strip()
    want = int(want_input) if want_input.isdigit() else 10
    if want == 0:
        want = 999999

    delay_input = input("每則間隔秒數？(預設 3): ").strip()
    delay = int(delay_input) if delay_input.isdigit() else 3

    print(f"\n即將從 {len(sources)} 個群組重新發送到 {target.title}")
    print(f"目標: 每個群組成功轉發 {want if want < 999999 else '全部'} 則")
    print(f"連結替換: {'@' + BOT_USERNAME if BOT_USERNAME else '不替換'}")
    confirm = input("確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        return

    fwd_log = load_forward_log()
    print(f"  📝 已轉發記錄: {len(fwd_log['message_ids'])} 則（重複/過濾的不算）\n")

    total = 0
    skipped_dup = 0

    for source in sources:
        last_id = get_last_forwarded_id(fwd_log, source.entity.id)
        if last_id:
            print(f"\n📥 來源: {source.title}（從上次 #{last_id} 之後開始）")
        else:
            print(f"\n📥 來源: {source.title}（首次抓取）")
        count = 0

        try:
            # 從所有訊息裡找，跳過已轉發/過濾的，湊滿目標數量
            fetch_limit = want * 10 if want < 999999 else None
            raw_msgs = []
            async for msg in client.iter_messages(source.entity, limit=fetch_limit):
                raw_msgs.append(msg)
            raw_msgs.reverse()  # 舊→新

            if not raw_msgs:
                print(f"    沒有訊息")
                continue

            print(f"    掃描 {len(raw_msgs)} 則，目標成功轉發 {want if want < 999999 else '全部'} 則")

            i = 0
            while i < len(raw_msgs):
                # 達到目標數量就停
                if count >= want:
                    print(f"    ✅ 已達目標 {want} 則，停止")
                    break

                msg = raw_msgs[i]
                grouped_id = getattr(msg, "grouped_id", None)

                if grouped_id:
                    album = [msg]
                    j = i + 1
                    while j < len(raw_msgs) and getattr(raw_msgs[j], "grouped_id", None) == grouped_id:
                        album.append(raw_msgs[j])
                        j += 1

                    album_text = ""
                    for m in album:
                        if m.text and m.text.strip():
                            album_text = m.text.strip()
                            break

                    if is_duplicate(fwd_log, source.entity.id, album[0].id, album_text):
                        skipped_dup += 1
                        i = j
                        continue

                    ok = await resend_album(client, target, album, BOT_USERNAME)
                    if ok == "skipped":
                        pass  # 過濾的不算，繼續找下一則
                    elif ok:
                        count += 1
                        mark_forwarded(fwd_log, source.entity.id, album[0].id, album_text)
                        print(f"    ✅ [{count}/{want}] 相簿({len(album)}張)")
                    i = j
                else:
                    msg_text = (msg.text or "").strip()

                    if is_duplicate(fwd_log, source.entity.id, msg.id, msg_text):
                        skipped_dup += 1
                        i += 1
                        continue

                    ok = await resend_message(client, target, msg, BOT_USERNAME)
                    if ok == "skipped":
                        pass  # 過濾的不算，繼續找下一則
                    elif ok:
                        count += 1
                        mark_forwarded(fwd_log, source.entity.id, msg.id, msg_text)
                        preview = msg_text[:40] if msg_text else "[媒體]"
                        print(f"    ✅ [{count}/{want}] {preview}")
                    elif ok:
                        count += 1
                        mark_forwarded(fwd_log, source.entity.id, msg.id, msg_text)
                        preview = msg_text[:40] if msg_text else "[媒體]"
                        if count % 10 == 0 or count <= 3:
                            print(f"    ✅ #{count} {preview}")
                    i += 1

                await asyncio.sleep(delay)

            print(f"    完成: {count} 則，跳過重複: {skipped_dup} 則")
            total += count

        except Exception as e:
            print(f"    ❌ 失敗: {e}")

    print(f"\n{'='*50}")
    print(f"全部完成! 轉發 {total} 則，跳過重複 {skipped_dup} 則")


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
        input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
