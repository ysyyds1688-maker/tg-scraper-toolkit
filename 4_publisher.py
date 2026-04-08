"""
Telegram 頻道發佈工具
功能：
  - 讀取 girl_scraper 抓取的 CSV + 圖片
  - 用管理員帳號重新發送到自己的頻道（不顯示轉發來源）
  - 自動替換原始連結為你的 Bot 連結（不導流回原始頻道）
  - 記錄已發佈的訊息，避免重複發送
  - 支援：單張圖+文字、相簿多張圖+文字
"""

import asyncio
import csv
import json
import os
import re
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, TOOLKIT_DIR
from telethon import TelegramClient
from telethon.errors import FloodWaitError


# ============================================================
# 設定
# ============================================================

# 你的 Bot username（用來替換原始連結）
BOT_USERNAME = "teaprincess_bot"

# 已發佈記錄檔
PUBLISHED_LOG = os.path.join(TOOLKIT_DIR, "published_log.json")


# ============================================================
# 連結替換
# ============================================================

# 匹配 Telegram 連結的正則
TG_LINK_PATTERNS = [
    r"https?://t\.me/\+?\w+/?[\w]*",        # t.me 連結
    r"https?://telegram\.me/\+?\w+/?[\w]*",  # telegram.me 連結
    r"@[\w]{5,}",                             # @username 格式
]


def replace_links(text, bot_username):
    """把原始 TG 連結替換成 Bot 連結"""
    if not text or not bot_username:
        return text

    bot_link = f"https://t.me/{bot_username}"

    for pattern in TG_LINK_PATTERNS:
        # 不替換自己的 Bot 連結
        matches = re.findall(pattern, text)
        for match in matches:
            if bot_username not in match:
                text = text.replace(match, f"👉 諮詢客服: {bot_link}")

    # 去除重複的替換文字
    while f"👉 諮詢客服: {bot_link}\n👉 諮詢客服: {bot_link}" in text:
        text = text.replace(
            f"👉 諮詢客服: {bot_link}\n👉 諮詢客服: {bot_link}",
            f"👉 諮詢客服: {bot_link}"
        )

    return text


# ============================================================
# 已發佈記錄
# ============================================================

def load_published():
    """讀取已發佈記錄"""
    if not os.path.exists(PUBLISHED_LOG):
        return {}
    with open(PUBLISHED_LOG, "r", encoding="utf-8") as f:
        return json.load(f)


def save_published(published):
    """儲存已發佈記錄"""
    with open(PUBLISHED_LOG, "w", encoding="utf-8") as f:
        json.dump(published, f, ensure_ascii=False, indent=2)


def mark_published(published, csv_name, message_id):
    """標記某則訊息已發佈"""
    if csv_name not in published:
        published[csv_name] = []
    published[csv_name].append({
        "message_id": message_id,
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    save_published(published)


def is_published(published, csv_name, message_id):
    """檢查某則訊息是否已發佈"""
    if csv_name not in published:
        return False
    return any(p["message_id"] == message_id for p in published[csv_name])


# ============================================================
# 工具函式
# ============================================================

def find_girl_csvs():
    """找到所有 girl_scraper 產出的 CSV"""
    data_dir = os.path.join(TOOLKIT_DIR, "data")
    csvs = []
    if not os.path.exists(data_dir):
        return csvs
    for f in sorted(os.listdir(data_dir)):
        if f.startswith("girls_") and f.endswith(".csv"):
            csvs.append(os.path.join(data_dir, f))
    return csvs


def load_csv(path):
    """讀取 CSV 內容"""
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def parse_photo_paths(photo_paths_str):
    """解析 photo_paths 欄位，回傳存在的檔案列表"""
    if not photo_paths_str:
        return []
    paths = [p.strip() for p in photo_paths_str.split(";") if p.strip()]
    return [p for p in paths if os.path.exists(p)]


# ============================================================
# 發佈引擎
# ============================================================

async def publish_single(client, target, text, photo_paths):
    """發送單則訊息"""
    try:
        if len(photo_paths) == 0:
            if text:
                await client.send_message(target, text)
                return True
            return False

        elif len(photo_paths) == 1:
            await client.send_file(target, photo_paths[0], caption=text or "")
            return True

        else:
            await client.send_file(target, photo_paths, caption=text or "")
            return True

    except FloodWaitError as e:
        print(f"    ⚠️  限速 {e.seconds}s，等待中...")
        await asyncio.sleep(e.seconds + 5)
        return await publish_single(client, target, text, photo_paths)
    except Exception as e:
        print(f"    ❌ 發送失敗: {e}")
        return False


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  Telegram 頻道發佈工具")
    print("  （重新發送到你的頻道，自動替換連結）")
    print("=" * 55)

    # 找 CSV
    csvs = find_girl_csvs()
    if not csvs:
        print("\n❌ 找不到 girl_scraper 的 CSV 檔案")
        print("   請先執行 girl_scraper.py 抓取資料")
        return

    # 載入已發佈記錄
    published = load_published()

    print(f"\n找到 {len(csvs)} 個資料檔：")
    for i, path in enumerate(csvs):
        basename = os.path.basename(path)
        rows = load_csv(path)
        has_photo = len([r for r in rows if r.get("has_photo") == "True"])
        already = len(published.get(basename, []))
        remaining = len(rows) - already
        print(f"  [{i+1}] {basename} ({len(rows)} 則, {has_photo} 有圖, 已發{already}, 剩{remaining})")

    choice = input("\n選擇要發佈的 CSV 編號: ").strip()
    try:
        csv_path = csvs[int(choice) - 1]
    except (ValueError, IndexError):
        print("無效選擇")
        return

    csv_name = os.path.basename(csv_path)
    rows = load_csv(csv_path)

    # 過濾已發佈的
    original_count = len(rows)
    rows = [r for r in rows if not is_published(published, csv_name, r.get("message_id", ""))]
    skipped = original_count - len(rows)
    if skipped:
        print(f"\n  ⏭ 跳過 {skipped} 則已發佈的訊息")

    # Bot 連結設定
    bot_username = BOT_USERNAME
    if not bot_username:
        bot_username = input("\n輸入你的 Bot username（用來替換原始連結，留空跳過）: ").strip().lstrip("@")

    if bot_username:
        # 統計有多少則訊息含有連結
        link_count = 0
        for r in rows:
            text = r.get("text", "")
            for pattern in TG_LINK_PATTERNS:
                if re.search(pattern, text):
                    link_count += 1
                    break
        print(f"  🔗 將替換 {link_count} 則訊息中的連結 → @{bot_username}")
    else:
        print("  ⚠️  未設定 Bot，原始連結將保留")

    # 目標頻道
    target_input = input("\n輸入你的頻道（username 或連結或 ID）: ").strip()
    if target_input.lstrip("-").isdigit():
        target_input = int(target_input)

    # 篩選
    print(f"\n篩選要發佈的內容：")
    print(f"  [1] 全部 ({len(rows)} 則)")
    has_photo_rows = [r for r in rows if r.get("has_photo") == "True"]
    print(f"  [2] 只有圖的 ({len(has_photo_rows)} 則)")
    has_text_photo = [r for r in rows if r.get("has_photo") == "True" and r.get("text", "").strip()]
    print(f"  [3] 有圖+有文字 ({len(has_text_photo)} 則)")

    filter_mode = input("\n選擇 (1/2/3): ").strip()
    if filter_mode == "2":
        rows = has_photo_rows
    elif filter_mode == "3":
        rows = has_text_photo

    if not rows:
        print("沒有符合條件的訊息")
        return

    # 間隔
    delay_input = input(f"\n每則間隔秒數？(預設 3): ").strip()
    delay = int(delay_input) if delay_input.isdigit() else 3

    print(f"\n📋 準備發佈:")
    print(f"   來源: {csv_name}")
    print(f"   數量: {len(rows)} 則")
    print(f"   連結替換: {'@' + bot_username if bot_username else '不替換'}")
    print(f"   間隔: {delay}s")

    confirm = input("\n確認開始？(y/n): ").strip().lower()
    if confirm != "y":
        print("已取消")
        return

    # 登入
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"\n✅ 登入: {me.first_name} (@{me.username})")

    try:
        target = await client.get_entity(target_input)
        print(f"✅ 目標: {target.title}\n")
    except Exception as e:
        print(f"❌ 找不到頻道: {e}")
        await client.disconnect()
        return

    # 開始發佈
    success = 0
    fail = 0

    try:
        for i, row in enumerate(rows):
            text = row.get("text", "").strip()
            photo_paths = parse_photo_paths(row.get("photo_paths", ""))
            msg_id = row.get("message_id", "?")
            is_album = row.get("is_album", "False") == "True"

            # 替換連結
            if bot_username and text:
                text = replace_links(text, bot_username)

            # 進度
            preview = (text[:40] + "...") if len(text) > 40 else text
            photo_count = len(photo_paths)
            type_str = f"相簿({photo_count}張)" if is_album else f"{'圖+文' if photo_count and text else '圖' if photo_count else '文'}"
            print(f"  [{i+1}/{len(rows)}] {type_str} | {preview or '[無文字]'}")

            ok = await publish_single(client, target, text, photo_paths)
            if ok:
                success += 1
                mark_published(published, csv_name, msg_id)
            else:
                fail += 1

            if i < len(rows) - 1:
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        print("\n\n⚠️  中斷，進度已保存")
    finally:
        await client.disconnect()

    print(f"\n{'='*50}")
    print(f"📊 發佈統計:")
    print(f"   成功: {success}")
    print(f"   失敗: {fail}")
    print(f"   記錄: {PUBLISHED_LOG}")
    print("完成!")


if __name__ == "__main__":
    asyncio.run(main())
