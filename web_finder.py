"""
從網路搜尋 Telegram 群組連結，檢查是否可抓取
支援 Google 搜尋 + Telegram 目錄站
"""

import asyncio
import csv
import os
import re
import ssl
import sys
import urllib.request
import urllib.parse
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, get_scraped_group_ids
from telethon import TelegramClient
from telethon.tl.types import Channel
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.errors import (
    ChatAdminRequiredError, FloodWaitError,
    InviteHashExpiredError, InviteHashInvalidError,
    UserAlreadyParticipantError, ChannelPrivateError,
)

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(TOOLKIT_DIR, "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# SSL context (忽略證書驗證)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ============================================================
# 搜尋關鍵字 - 修改這裡
# ============================================================
SEARCH_QUERIES = [
    # t.me 連結搜尋（DuckDuckGo/Bing 友好格式）
    "t.me 外送茶 群組",
    "t.me 約砲 台灣 群",
    "t.me 約炮群 台灣",
    "t.me 台灣 成人 群組",
    "t.me 茶友 討論群",
    "t.me 老司機 群組",
    "t.me 深夜 台灣 群",
    "t.me 外約 台灣",
    "t.me 喝茶 群組",
    "t.me 紳士俱樂部",
    "t.me 福利群 台灣",
    "t.me 成人交友 台灣",
    "t.me 外送茶 台北",
    "t.me 外送茶 台中",
    "t.me 外送茶 高雄",
    "t.me 約砲群 台北",
    "t.me 約砲群 台中",
    "t.me 步兵 群組",
    "t.me 本土 兼職妹",
    "t.me 夜生活 台灣",
    "t.me 一夜情 台灣",
    "t.me 按摩 舒壓 台灣",
    # telegram 關鍵字搜尋
    "telegram 外送茶 群組 連結 加入",
    "telegram 約砲 群組 t.me 台灣",
    "telegram 台灣 成人群 連結 2025",
    "telegram 老司機 群組 t.me",
    "telegram 深夜群 t.me 連結",
    "telegram 茶友群 台灣 加入",
    "telegram 外約 群組 台灣 連結",
    "telegram 約炮 群 加入 t.me",
    # 論壇/PTT/Dcard 搜尋（這些地方常有人分享連結）
    "外送茶 telegram 群 t.me PTT",
    "約砲 telegram t.me dcard",
    "外約 telegram 連結 分享",
    "茶訊 telegram 群組 推薦",
    "成人 telegram 群組 台灣 推薦",
]


def fetch_url(url, retries=2):
    """抓取網頁內容"""
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            if i == retries - 1:
                return ""
    return ""


def extract_tg_links(text):
    """從文字中提取 t.me 連結"""
    patterns = [
        r'(?:https?://)?(?:t\.me|telegram\.me)/(?:\+|joinchat/)([a-zA-Z0-9_\-]+)',
        r'(?:https?://)?(?:t\.me|telegram\.me)/([a-zA-Z0-9_]+)',
    ]
    links = set()
    for p in patterns:
        for match in re.finditer(p, text):
            link_id = match.group(1)
            # 過濾掉常見的非群組連結
            skip = ["proxy", "socks", "share", "addstickers", "addtheme",
                     "setlanguage", "bg", "invoice", "boost", "addlist",
                     "privacy", "tos", "faq"]
            if link_id.lower() in skip:
                continue
            if len(link_id) < 3:
                continue
            # 判斷是邀請連結還是 username
            full = match.group(0)
            if "/+" in full or "/joinchat/" in full:
                links.add(f"+{link_id}")
            else:
                links.add(link_id)
    return links


def duckduckgo_search(query, num_pages=2):
    """用 DuckDuckGo 搜尋，提取 t.me 連結"""
    all_links = set()
    # DuckDuckGo HTML 版本，不擋爬蟲
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    html = fetch_url(url)
    if html:
        # 提取所有 URL
        urls = re.findall(r'href="([^"]*)"', html)
        for u in urls:
            # DuckDuckGo 會把真實 URL 放在 uddg 參數裡
            if "uddg=" in u:
                real_url = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                links = extract_tg_links(real_url)
                all_links.update(links)
            elif "t.me" in u:
                links = extract_tg_links(u)
                all_links.update(links)
        # 直接從頁面文字也提取
        links = extract_tg_links(html)
        all_links.update(links)
    return all_links


def bing_search(query, num_pages=2):
    """用 Bing 搜尋，提取 t.me 連結"""
    all_links = set()
    for page in range(num_pages):
        first = page * 10 + 1
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&first={first}"
        html = fetch_url(url)
        if html:
            links = extract_tg_links(html)
            all_links.update(links)
            # 從所有 URL 中提取
            urls = re.findall(r'href="([^"]*)"', html)
            for u in urls:
                if "t.me" in u:
                    links2 = extract_tg_links(u)
                    all_links.update(links2)
    return all_links


def web_search(query):
    """同時用 DuckDuckGo + Bing 搜尋"""
    links = set()
    links.update(duckduckgo_search(query))
    links.update(bing_search(query))
    return links


def search_tg_directories(keywords):
    """搜尋 Telegram 目錄站"""
    all_links = set()
    # 常見的 TG 目錄站
    directories = [
        "https://tgstat.com/search?q={}&type=channel",
        "https://telegramchannels.me/search?q={}",
        "https://combot.org/telegram/top/groups?q={}",
    ]
    for kw in keywords:
        for tmpl in directories:
            url = tmpl.format(urllib.parse.quote(kw))
            html = fetch_url(url)
            if html:
                links = extract_tg_links(html)
                all_links.update(links)
    return all_links


async def check_link(client, link_id):
    """檢查一個連結是什麼類型"""
    result = {
        "link": link_id,
        "name": "?",
        "type": "?",
        "members": 0,
        "megagroup": False,
        "can_scrape": False,
        "joined": False,
        "status": "",
    }

    try:
        if link_id.startswith("+"):
            # 邀請連結
            hash_str = link_id[1:]
            try:
                info = await client(CheckChatInviteRequest(hash=hash_str))
                if hasattr(info, "chat"):
                    chat = info.chat
                    result["name"] = getattr(chat, "title", "?")
                    result["members"] = getattr(chat, "participants_count", 0) or 0
                    result["joined"] = True
                    if isinstance(chat, Channel):
                        result["megagroup"] = getattr(chat, "megagroup", False)
                        result["type"] = "群組" if result["megagroup"] else "頻道"
                    else:
                        result["type"] = "小群組"
                        result["megagroup"] = True
                elif hasattr(info, "title"):
                    result["name"] = info.title
                    result["members"] = getattr(info, "participants_count", 0) or 0
                    result["type"] = "未加入"
                    result["joined"] = False
                    # 嘗試判斷是否為群組
                    if not getattr(info, "broadcast", True):
                        result["megagroup"] = True
                        result["type"] = "群組(未加入)"
            except InviteHashExpiredError:
                result["status"] = "連結失效"
                return result
            except InviteHashInvalidError:
                result["status"] = "連結無效"
                return result
        else:
            # username
            try:
                entity = await client.get_entity(link_id)
                if isinstance(entity, Channel):
                    result["name"] = entity.title
                    result["megagroup"] = entity.megagroup
                    result["type"] = "群組" if entity.megagroup else "頻道"
                    try:
                        full = await client(GetFullChannelRequest(entity))
                        result["members"] = full.full_chat.participants_count or 0
                    except Exception:
                        result["members"] = getattr(entity, "participants_count", 0) or 0
                    result["joined"] = not getattr(entity, "left", True)
                else:
                    result["status"] = "非群組/頻道"
                    return result
            except ChannelPrivateError:
                result["status"] = "私人頻道"
                return result
            except Exception as e:
                result["status"] = f"錯誤: {type(e).__name__}"
                return result

        # 檢查是否可抓取
        if result["megagroup"] and result["members"] > 0 and result["members"] <= 5000:
            result["can_scrape"] = True
            result["status"] = f"可抓取 ({result['members']}人)"
        elif result["megagroup"] and result["members"] > 5000:
            result["status"] = f"群組太大 ({result['members']}人)"
        elif not result["megagroup"]:
            result["status"] = "頻道(非群組)"
        else:
            result["status"] = f"{result['members']}人"

    except FloodWaitError as e:
        result["status"] = f"限速 {e.seconds}秒"
        await asyncio.sleep(min(e.seconds, 60))
    except Exception as e:
        result["status"] = f"錯誤: {type(e).__name__}"

    return result


async def main():
    print("=" * 55)
    print("  網路搜尋 Telegram 群組連結")
    print("=" * 55)
    print()
    print("  [1] 自動搜尋 (用預設關鍵字，DuckDuckGo + Bing)")
    print("  [2] 自訂關鍵字搜尋")
    print("  [3] 貼上連結 (手動輸入 t.me 連結)")
    print()

    mode = input("選擇模式 (1/2/3): ").strip()

    all_links = set()

    if mode == "1":
        print(f"\n開始搜尋 ({len(SEARCH_QUERIES)} 組關鍵字，DuckDuckGo + Bing)...\n")
        for i, q in enumerate(SEARCH_QUERIES):
            print(f"  [{i+1}/{len(SEARCH_QUERIES)}] {q}", end="", flush=True)
            links = web_search(q)
            new = links - all_links
            all_links.update(links)
            print(f" → {len(links)} 個連結，新增 {len(new)} 個")
            await asyncio.sleep(1.5)

        # 額外搜尋 Telegram 目錄站
        print(f"\n  搜尋 Telegram 目錄站...", end="", flush=True)
        dir_keywords = ["外送茶", "約砲", "台灣成人", "老司機", "茶友", "深夜群", "外約"]
        dir_links = search_tg_directories(dir_keywords)
        new = dir_links - all_links
        all_links.update(dir_links)
        print(f" → {len(dir_links)} 個連結，新增 {len(new)} 個")

    elif mode == "2":
        print("\n輸入搜尋關鍵字（每行一個，輸入空行結束）：")
        keywords = []
        while True:
            kw = input("  > ").strip()
            if not kw:
                break
            keywords.append(kw)

        if not keywords:
            print("沒有輸入關鍵字")
            return

        for i, kw in enumerate(keywords):
            queries = [
                f"site:t.me {kw}",
                f"telegram {kw} 群組 連結",
            ]
            for q in queries:
                print(f"  [{i+1}/{len(keywords)}] {q}", end="", flush=True)
                links = web_search(q)
                new = links - all_links
                all_links.update(links)
                print(f" → {len(links)} 個連結，新增 {len(new)} 個")
                await asyncio.sleep(2)

    elif mode == "3":
        print("\n貼上 t.me 連結（每行一個，輸入空行結束）：")
        while True:
            line = input("  > ").strip()
            if not line:
                break
            links = extract_tg_links(line)
            all_links.update(links)
            if not links:
                # 嘗試直接當 username
                if line.startswith("@"):
                    all_links.add(line[1:])
                elif "/" not in line and " " not in line:
                    all_links.add(line)

    else:
        print("無效選擇")
        return

    if not all_links:
        print("\n沒有找到任何連結")
        return

    print(f"\n共找到 {len(all_links)} 個不重複連結")

    # Phase 2: 用 Telegram API 檢查每個連結
    print(f"\n正在連接 Telegram...\n")
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    results = []
    scrapable = []

    for i, link_id in enumerate(sorted(all_links)):
        display = f"t.me/{link_id}" if not link_id.startswith("+") else f"t.me/{link_id}"
        print(f"  [{i+1}/{len(all_links)}] {display:<40}", end="", flush=True)

        result = await check_link(client, link_id)
        results.append(result)

        status = result["status"]
        if result["can_scrape"]:
            print(f" → \033[1;32m{result['name']} ({result['status']})\033[0m")
            scrapable.append(result)
        elif result["megagroup"] and not result["joined"] and result["members"] <= 5000:
            print(f" → \033[1;33m{result['name']} ({result['status']}) [可嘗試加入]\033[0m")
            scrapable.append(result)
        else:
            print(f" → {result.get('name', '?')} ({status})")

        await asyncio.sleep(1)

    # 報告
    print(f"\n{'='*55}")
    print(f"搜尋完成!")
    print(f"  總連結: {len(all_links)}")
    print(f"  可抓取/可嘗試: {len(scrapable)} 個")

    if not scrapable:
        print("  沒有找到可抓取的群組")
        await client.disconnect()
        return

    print(f"\n可抓取的群組：")
    for i, r in enumerate(scrapable):
        joined = "已加入" if r["joined"] else "未加入"
        print(f"  [{i+1}] {r['name']} ({r['members']}人) [{joined}]")

    # 詢問是否自動加入+爬取
    not_joined = [r for r in scrapable if not r["joined"]]
    already_joined = [r for r in scrapable if r["joined"]]

    if not_joined:
        print(f"\n其中 {len(not_joined)} 個未加入的群組")
        confirm = input("要自動加入並爬取成員嗎？(y/n): ").strip().lower()
        if confirm == "y":
            for r in not_joined:
                link_id = r["link"]
                print(f"\n  加入: {r['name']}...", end="", flush=True)
                try:
                    if link_id.startswith("+"):
                        await client(ImportChatInviteRequest(hash=link_id[1:]))
                    else:
                        entity = await client.get_entity(link_id)
                        from telethon.tl.functions.channels import JoinChannelRequest
                        await client(JoinChannelRequest(entity))
                    print(" 成功!", flush=True)
                    r["joined"] = True
                    already_joined.append(r)
                    await asyncio.sleep(3)
                except UserAlreadyParticipantError:
                    print(" 已在群組中", flush=True)
                    r["joined"] = True
                    already_joined.append(r)
                except FloodWaitError as e:
                    print(f" 限速，等待 {e.seconds} 秒...", flush=True)
                    if e.seconds > 300:
                        print("  等待時間太長，跳過剩餘")
                        break
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f" 失敗: {type(e).__name__}", flush=True)

    # 爬取已加入的可抓取群組
    to_scrape = [r for r in already_joined if r["megagroup"]]
    if to_scrape:
        scraped_ids = get_scraped_group_ids()
        print(f"\n已爬過的群組: {len(scraped_ids)} 個")
        print(f"\n準備爬取 {len(to_scrape)} 個群組的成員...")
        confirm2 = input("開始爬取？(y/n): ").strip().lower()
        if confirm2 == "y":
            from telethon.tl.functions.channels import GetParticipantsRequest
            from telethon.tl.types import ChannelParticipantsSearch

            all_members = {}
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            for r in to_scrape:
                link_id = r["link"]
                name = r["name"]
                print(f"\n  📥 爬取: {name}...", end="", flush=True)

                try:
                    if link_id.startswith("+"):
                        # 用名稱搜尋 entity
                        dialogs = await client.get_dialogs()
                        entity = None
                        for d in dialogs:
                            if hasattr(d.entity, 'title') and d.entity.title == name:
                                entity = d.entity
                                break
                        if not entity:
                            print(" 找不到群組", flush=True)
                            continue
                    else:
                        entity = await client.get_entity(link_id)

                    if str(entity.id) in scraped_ids:
                        print(f" ⏭ 已爬過，跳過", flush=True)
                        continue

                    # 逐字搜尋抓取成員
                    members = {}
                    search_chars = [""] + list("abcdefghijklmnopqrstuvwxyz0123456789")
                    for ch in search_chars:
                        try:
                            result = await client(GetParticipantsRequest(
                                channel=entity,
                                filter=ChannelParticipantsSearch(ch),
                                offset=0,
                                limit=200,
                                hash=0
                            ))
                            for user in result.users:
                                if user.id not in members and not user.bot:
                                    members[user.id] = {
                                        "user_id": str(user.id),
                                        "username": user.username or "",
                                        "first_name": user.first_name or "",
                                        "last_name": user.last_name or "",
                                        "phone": user.phone or "",
                                        "is_bot": str(user.bot),
                                        "source_group": name,
                                        "source_group_id": str(entity.id),
                                    }
                            if not result.users:
                                break
                        except ChatAdminRequiredError:
                            print(f" 需要管理員權限", flush=True)
                            break
                        except FloodWaitError as e:
                            await asyncio.sleep(min(e.seconds, 30))
                        except Exception:
                            break

                    print(f" {len(members)} 位", flush=True)

                    for uid, m in members.items():
                        if uid not in all_members:
                            all_members[uid] = m

                except Exception as e:
                    print(f" 錯誤: {type(e).__name__}", flush=True)

            # 儲存成員
            if all_members:
                members_path = os.path.join(OUTPUT_DIR, f"web_members_{timestamp}.csv")
                fieldnames = ["user_id", "username", "first_name", "last_name", "phone", "is_bot", "source_group", "source_group_id"]
                with open(members_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(all_members.values())
                print(f"\n共 {len(all_members)} 位不重複成員")
                print(f"儲存至: {members_path}")

                # 自動合併去重
                print("\n自動合併去重中...")
                import subprocess
                subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])
            else:
                print("\n沒有抓到任何成員")

    # 儲存報告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(OUTPUT_DIR, f"web_search_report_{timestamp}.csv")
    with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["link", "name", "type", "members", "megagroup", "can_scrape", "joined", "status"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n報告已存至: {report_path}")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
