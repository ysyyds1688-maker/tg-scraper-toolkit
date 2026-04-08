"""
客服導流 Bot - 茶王公主的佳麗
功能：
  - 歡迎語 + 茶莊客服按鈕
  - 用戶輸入佳麗名字 → 自動比對來源 → 回覆對應客服
  - 管理員可用指令管理客服列表
  - 按鈕格式：來源名稱-茶莊客服
"""

import csv
import glob
import json
import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.custom import Button

from config import API_ID, API_HASH, TOOLKIT_DIR

# ============================================================
# 設定
# ============================================================

BOT_TOKEN = "8703326700:AAGsyecmLr_uKJBBApPQDAsTND-xXBgZ8H8"
AGENTS_FILE = os.path.join(TOOLKIT_DIR, "agents.json")
ADMIN_IDS = [8287730126]

# girl_scraper 資料目錄
DATA_DIR = os.path.join(TOOLKIT_DIR, "data")


# ============================================================
# 客服管理
# ============================================================

def load_agents():
    if not os.path.exists(AGENTS_FILE):
        save_agents([])
        return []
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        agents = json.load(f)
    # 兼容舊格式：name → source_name
    for a in agents:
        if "source_name" not in a and "name" in a:
            a["source_name"] = a.pop("name")
        if "group_name" in a:
            del a["group_name"]
    return agents


def save_agents(agents):
    with open(AGENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)


def add_agent(source_name, username):
    """新增客服，source_name = 來源名稱（如 大神、極樂）"""
    agents = load_agents()
    agents.append({
        "source_name": source_name,
        "username": username,
    })
    save_agents(agents)
    return agents


def remove_agent(source_name):
    agents = load_agents()
    agents = [a for a in agents if a["source_name"] != source_name]
    save_agents(agents)
    return agents


# ============================================================
# 佳麗來源比對
# ============================================================

def load_girls_data():
    """從 girl_scraper 的 CSV 載入所有佳麗資料"""
    all_posts = []
    for f in glob.glob(os.path.join(DATA_DIR, "girls_*.csv")):
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    if row.get("text", "").strip():
                        all_posts.append({
                            "text": row["text"],
                            "channel_name": row.get("channel_name", ""),
                            "message_link": row.get("message_link", ""),
                        })
        except Exception:
            continue
    return all_posts


def search_girl(keyword, posts, agents):
    """
    用關鍵字在爬取的資料中搜尋佳麗
    回傳: (找到的貼文, 對應的客服 agent) 或 (None, None)
    """
    keyword = keyword.strip()
    if not keyword:
        return None, None

    # 在所有貼文中搜尋
    matched_posts = []
    for post in posts:
        if keyword in post["text"]:
            matched_posts.append(post)

    if not matched_posts:
        return None, None

    # 用第一個匹配的貼文，找對應的來源
    best = matched_posts[0]
    channel_name = best["channel_name"]

    # 比對哪個客服負責這個來源
    matched_agent = None
    for agent in agents:
        source = agent["source_name"]
        if source in channel_name or channel_name in source:
            matched_agent = agent
            break

    return best, matched_agent


# ============================================================
# Bot 主體
# ============================================================

async def main():
    print("=" * 55)
    print("  茶王公主的佳麗 - 客服導流 Bot")
    print("=" * 55)

    bot = TelegramClient("bot_session", API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)

    me = await bot.get_me()
    print(f"\n✅ Bot 啟動: {me.first_name} (@{me.username})")
    print(f"   客服設定檔: {AGENTS_FILE}")

    # 載入佳麗資料
    girls_data = load_girls_data()
    print(f"   佳麗資料: {len(girls_data)} 筆貼文")
    print(f"\n🟢 Bot 運行中... (Ctrl+C 停止)\n")

    # === /start ===
    @bot.on(events.NewMessage(pattern="/start"))
    async def start_handler(event):
        agents = load_agents()

        text = "嗨～歡迎光臨，親愛的茶士 🍵\n\n"
        text += "想約哪位佳麗呢？\n"
        text += "請點選下方按鈕，直接聯繫該茶莊客服即可安排 ✨\n\n"
        text += "⚠️ 聯繫客服時記得說是「茶王推薦」的唷！"

        if not agents:
            await event.respond(text + "\n\n目前尚未設定客服，請稍後再試 🙏")
            return

        buttons = []
        for agent in agents:
            buttons.append([Button.url(
                f"🍵 {agent['source_name']}-茶莊客服",
                f"https://t.me/{agent['username']}"
            )])

        await event.respond(text, buttons=buttons)

    # === /add 來源名稱 username ===
    @bot.on(events.NewMessage(pattern=r"/add\s+(.+)"))
    async def add_handler(event):
        if ADMIN_IDS and event.sender_id not in ADMIN_IDS:
            return

        args = event.pattern_match.group(1).strip().split()
        if len(args) < 2:
            await event.respond(
                "用法: /add 來源名稱 客服username\n"
                "範例: /add 大神 daishen_service\n"
                "範例: /add 極樂 jile_cs"
            )
            return

        source_name = args[0]
        username = args[1].lstrip("@")

        agents = add_agent(source_name, username)
        await event.respond(
            f"✅ 已新增:\n"
            f"   來源: {source_name}\n"
            f"   客服: @{username}\n"
            f"   按鈕顯示: 🍵 {source_name}-茶莊客服\n\n"
            f"目前共 {len(agents)} 個來源"
        )
        print(f"  [管理] 新增: {source_name} → @{username}")

    # === /remove 來源名稱 ===
    @bot.on(events.NewMessage(pattern=r"/remove\s+(.+)"))
    async def remove_handler(event):
        if ADMIN_IDS and event.sender_id not in ADMIN_IDS:
            return

        source_name = event.pattern_match.group(1).strip()
        agents = remove_agent(source_name)
        await event.respond(
            f"✅ 已刪除: {source_name}\n"
            f"目前共 {len(agents)} 個來源"
        )
        print(f"  [管理] 刪除: {source_name}")

    # === /list ===
    @bot.on(events.NewMessage(pattern="/list"))
    async def list_handler(event):
        if ADMIN_IDS and event.sender_id not in ADMIN_IDS:
            return

        agents = load_agents()
        if not agents:
            await event.respond("目前沒有客服")
            return

        text = f"📋 客服列表 ({len(agents)} 個來源):\n\n"
        for i, a in enumerate(agents, 1):
            text += f"  {i}. {a['source_name']}-茶莊客服 → @{a['username']}\n"
        text += "\n指令:\n/add 來源名稱 username\n/remove 來源名稱\n/reload 重新載入佳麗資料"
        await event.respond(text)

    # === /reload 重新載入佳麗資料 ===
    @bot.on(events.NewMessage(pattern="/reload"))
    async def reload_handler(event):
        if ADMIN_IDS and event.sender_id not in ADMIN_IDS:
            return

        nonlocal girls_data
        girls_data = load_girls_data()
        await event.respond(f"✅ 已重新載入佳麗資料: {len(girls_data)} 筆貼文")
        print(f"  [管理] 重新載入: {len(girls_data)} 筆")

    # === 用戶輸入佳麗名字 → 比對來源 → 回覆客服 ===
    @bot.on(events.NewMessage())
    async def catch_all(event):
        if event.text and event.text.startswith("/"):
            return
        if event.sender_id == me.id:
            return

        agents = load_agents()
        keyword = (event.text or "").strip()

        if not keyword:
            return

        # 搜尋佳麗
        post, agent = search_girl(keyword, girls_data, agents)

        if post and agent:
            # 找到佳麗且有對應客服
            text = (
                f"您要約的佳麗來源是「{agent['source_name']}」🍵\n\n"
                f"請聯繫 {agent['source_name']}-茶莊客服 唷！\n\n"
                f"⚠️ 記得跟客服說是「茶王推薦」的！"
            )
            buttons = [[Button.url(
                f"🍵 {agent['source_name']}-茶莊客服",
                f"https://t.me/{agent['username']}"
            )]]
            await event.respond(text, buttons=buttons)

        elif post and not agent:
            # 找到佳麗但沒有對應客服
            text = (
                f"找到了相關的佳麗資訊，來源是「{post['channel_name']}」\n\n"
                f"但目前該來源尚未設定客服，請選擇其他客服聯繫 👇\n\n"
                f"⚠️ 記得跟客服說是「茶王推薦」的！"
            )
            buttons = []
            for a in agents:
                buttons.append([Button.url(
                    f"🍵 {a['source_name']}-茶莊客服",
                    f"https://t.me/{a['username']}"
                )])
            if buttons:
                await event.respond(text, buttons=buttons)
            else:
                await event.respond(text)

        else:
            # 完全沒找到
            text = "嗨～歡迎光臨，親愛的茶士 🍵\n\n"
            text += "想約哪位佳麗呢？\n"
            text += "請點選下方按鈕，直接聯繫該茶莊客服即可安排 ✨\n\n"
            text += "⚠️ 聯繫客服時記得說是「茶王推薦」的唷！"

            buttons = []
            for a in agents:
                buttons.append([Button.url(
                    f"🍵 {a['source_name']}-茶莊客服",
                    f"https://t.me/{a['username']}"
                )])
            if buttons:
                await event.respond(text, buttons=buttons)
            else:
                await event.respond(text + "\n\n目前尚未設定客服，請稍後再試 🙏")

    print("等待訊息中...\n")
    await bot.run_until_disconnected()


if __name__ == "__main__":
    import platform
    if platform.system() == "Darwin":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    else:
        asyncio.run(main())
