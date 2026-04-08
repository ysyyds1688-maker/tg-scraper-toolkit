"""
深度爬蟲 - 自動加入群組/頻道 → 掃描訊息中的連結 → 加入新群組 → 繼續深挖
遞迴式探索，自動發現並爬取可抓群組的成員
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, get_scraped_group_ids
from telethon import TelegramClient
from telethon.tl.functions.channels import (
    GetFullChannelRequest, GetParticipantsRequest, JoinChannelRequest,
)
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.types import (
    ChannelParticipantsSearch, Channel,
    ChatInvite, ChatInviteAlready, ChatInvitePeek,
)
from telethon.errors import (
    ChatAdminRequiredError, FloodWaitError,
    InviteHashExpiredError, UserAlreadyParticipantError,
    ChannelPrivateError, InviteHashInvalidError,
)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SCAN_MESSAGES = 1000

# === 防偵測設定 ===
JOIN_DELAY = (15, 30)      # 加入群組間隔（秒），隨機範圍
CHECK_DELAY = (5, 10)      # 檢查連結間隔（秒）
MAX_JOINS_PER_RUN = 10     # 每次執行最多加入幾個群組
FLOOD_WAIT_ABORT = 120     # 限速超過幾秒就停止加入
RECONNECT_RETRIES = 3      # 斷線重連次數

# === 過濾設定（只保留台灣/中文相關群組）===
import unicodedata
import random

async def safe_call(client, coro_func, *args, **kwargs):
    """帶重連機制的 API 呼叫"""
    for attempt in range(RECONNECT_RETRIES):
        try:
            if not client.is_connected():
                print("    🔄 重新連線中...")
                await client.connect()
            return await coro_func(*args, **kwargs)
        except (ConnectionError, TimeoutError, OSError) as e:
            if attempt < RECONNECT_RETRIES - 1:
                wait = (attempt + 1) * 10
                print(f"    ⚠ 連線中斷，{wait}秒後重連 (第{attempt+2}次)...")
                await asyncio.sleep(wait)
                try:
                    await client.disconnect()
                except Exception:
                    pass
                try:
                    await client.connect()
                except Exception:
                    pass
            else:
                raise
    return None


def has_chinese(text):
    """檢查是否包含中文字"""
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3400' <= ch <= '\u4dbf':
            return True
    return False

def is_relevant(title):
    """檢查群組名稱是否相關（包含中文或台灣相關關鍵字）"""
    if not title:
        return False
    # 必須包含中文
    if not has_chinese(title):
        return False
    # 排除明顯不相關的
    block_words = ["德國", "Deutschland", "русск", "korea", "japan", "india",
                   "العرب", "فارسی", "ไทย", "Việt", "bahasa", "GH |", "Group Help"]
    for w in block_words:
        if w.lower() in title.lower():
            return False
    return True

TG_LINK_RE = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:(?:\+|joinchat/)([a-zA-Z0-9_\-]+)|([a-zA-Z0-9_]+))',
    re.IGNORECASE,
)

SKIP_USERNAMES = {"s", "proxy", "socks", "share", "addstickers", "addemoji",
                  "setlanguage", "addtheme", "c", "iv", "boost", "addlist",
                  "username", "privacy", "tos", "faq", "dl", "durov",
                  "GroupHelpBot", "chelpbot", "ModularBot", "iGroupHelp"}


async def extract_links(client, entity, limit=SCAN_MESSAGES):
    """從群組/頻道訊息中提取 t.me 連結"""
    invite_hashes = set()
    usernames = set()
    count = 0

    async for msg in client.iter_messages(entity, limit=limit):
        text = msg.text or ""
        if msg.reply_markup:
            for row in getattr(msg.reply_markup, "rows", []):
                for btn in row.buttons:
                    url = getattr(btn, "url", None)
                    if url:
                        text += " " + url
        for match in TG_LINK_RE.finditer(text):
            inv = match.group(1)
            uname = match.group(2)
            if inv:
                invite_hashes.add(inv)
            elif uname and uname.lower() not in SKIP_USERNAMES and len(uname) > 2:
                usernames.add(uname)
        count += 1

    return invite_hashes, usernames, count


async def check_scrapable(client, entity):
    """檢查群組是否可抓取，回傳 (可抓數, 總數)"""
    if not isinstance(entity, Channel) or not entity.megagroup:
        return 0, 0
    try:
        result = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=0, limit=10, hash=0,
        ))
        return result.count, getattr(entity, "participants_count", 0) or result.count
    except (ChatAdminRequiredError, FloodWaitError):
        return 0, 0
    except Exception:
        return 0, 0


async def scrape_members(client, entity):
    """爬取成員"""
    members = {}
    search_chars = [""] + list("abcdefghijklmnopqrstuvwxyz0123456789")
    for ch in search_chars:
        try:
            result = await client(GetParticipantsRequest(
                channel=entity,
                filter=ChannelParticipantsSearch(ch),
                offset=0, limit=200, hash=0,
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
                        "source_group": entity.title,
                        "source_group_id": str(entity.id),
                    }
            if not result.users:
                break
        except ChatAdminRequiredError:
            break
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 30))
        except Exception:
            break
    return list(members.values())


async def try_join_invite(client, inv_hash, join_count):
    """嘗試加入邀請連結，回傳 (entity, name, status, new_join_count)"""
    try:
        # 先檢查（不加入）
        info = await client(CheckChatInviteRequest(hash=inv_hash))
        if isinstance(info, ChatInviteAlready):
            chat = info.chat
            return chat, getattr(chat, "title", "?"), "已加入", join_count
        elif isinstance(info, (ChatInvite, ChatInvitePeek)):
            title = getattr(info, "title", "?")
            is_mega = getattr(info, "megagroup", False)
            is_broadcast = getattr(info, "broadcast", False)
            count = getattr(info, "participants_count", 0) or 0
            if is_broadcast and not is_mega:
                return None, title, f"頻道({count}人)", join_count
            # 過濾非中文群組
            if not is_relevant(title):
                return None, title, "跳過(非中文/不相關)", join_count
            # 加入數量限制
            if join_count >= MAX_JOINS_PER_RUN:
                return None, title, "跳過(已達加入上限)", join_count
            # 加入前隨機延遲
            delay = random.randint(*JOIN_DELAY)
            await asyncio.sleep(delay)
            updates = await client(ImportChatInviteRequest(hash=inv_hash))
            if updates.chats:
                return updates.chats[0], title, "新加入", join_count + 1
            return None, title, "加入失敗", join_count
    except UserAlreadyParticipantError:
        return None, "?", "已加入", join_count
    except (InviteHashExpiredError, InviteHashInvalidError):
        return None, "?", "連結失效", join_count
    except FloodWaitError as e:
        if e.seconds > FLOOD_WAIT_ABORT:
            return None, "?", f"限速{e.seconds}秒(停止加入)", join_count
        await asyncio.sleep(e.seconds)
        return None, "?", "限速跳過", join_count
    except Exception as e:
        err_name = type(e).__name__
        # 跳過需要人類驗證的群組
        if "InviteRequestSent" in err_name:
            return None, "?", "需要管理員審核", join_count
        return None, "?", f"錯誤:{err_name}", join_count


async def try_join_username(client, username, join_count):
    """嘗試加入公開群組，回傳 (entity, name, status, new_join_count)"""
    try:
        entity = await client.get_entity(username)
        if not isinstance(entity, Channel):
            return None, username, "非群組/頻道", join_count
        title = entity.title
        # 過濾非中文群組
        if not is_relevant(title) and not entity.megagroup:
            return None, title, "跳過(非中文/不相關)", join_count
        if entity.left:
            # 過濾非中文
            if not is_relevant(title):
                return None, title, "跳過(非中文/不相關)", join_count
            # 加入數量限制
            if join_count >= MAX_JOINS_PER_RUN:
                return None, title, "跳過(已達加入上限)", join_count
            # 隨機延遲
            delay = random.randint(*JOIN_DELAY)
            await asyncio.sleep(delay)
            await client(JoinChannelRequest(entity))
            entity = await client.get_entity(username)
            return entity, title, "新加入", join_count + 1
        return entity, title, "已加入", join_count
    except ChannelPrivateError:
        return None, username, "私人頻道", join_count
    except FloodWaitError as e:
        if e.seconds > FLOOD_WAIT_ABORT:
            return None, username, f"限速{e.seconds}秒(停止)", join_count
        await asyncio.sleep(e.seconds)
        return None, username, "限速跳過", join_count
    except Exception as e:
        err_name = type(e).__name__
        if "InviteRequestSent" in err_name:
            return None, username, "需要管理員審核", join_count
        return None, username, f"錯誤:{err_name}", join_count


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    print("=" * 55)
    print("  深度爬蟲 - 自動深挖群組連結")
    print("=" * 55)
    print()

    # 設定深度
    max_depth = input("最大深度 (建議 2-3，預設 2): ").strip()
    max_depth = int(max_depth) if max_depth.isdigit() else 2

    print(f"\n深度: {max_depth} 層")
    print(f"每層掃描: {SCAN_MESSAGES} 則訊息")
    print()

    # 選擇起始群組
    dialogs = await client.get_dialogs()
    source_groups = [d for d in dialogs if d.is_group or d.is_channel]

    print("你的群組/頻道：")
    for i, d in enumerate(source_groups):
        kind = "📢" if getattr(d.entity, "broadcast", False) else "👥"
        print(f"  [{i+1:2d}] {kind} {d.title}")

    print(f"\n選擇起始群組（逗號分隔，或 a 全部）：")
    choice = input("> ").strip()

    if choice.lower() == "a":
        seeds = [d.entity for d in source_groups]
    else:
        indices = [int(n.strip()) - 1 for n in choice.split(",")]
        seeds = [source_groups[i].entity for i in indices if 0 <= i < len(source_groups)]

    if not seeds:
        print("沒有選擇任何群組")
        await client.disconnect()
        return

    # 開始深度爬取
    visited_ids = set()       # 已掃描過的群組 ID
    visited_links = set()     # 已處理過的連結
    all_scrapable = []        # 可抓取的群組
    all_members = []          # 所有成員
    join_count = 0            # 本次已加入的群組數
    abort_joining = False     # 是否停止加入新群組

    # 初始化佇列
    queue = [(e, 0) for e in seeds]  # (entity, depth)

    scraped_ids = get_scraped_group_ids()
    print(f"\n已爬過的群組: {len(scraped_ids)} 個")

    print(f"\n防偵測設定：")
    print(f"  加入間隔: {JOIN_DELAY[0]}-{JOIN_DELAY[1]} 秒")
    print(f"  最多加入: {MAX_JOINS_PER_RUN} 個群組")
    print(f"  限速閾值: {FLOOD_WAIT_ABORT} 秒以上停止")
    print(f"  過濾: 只保留中文相關群組")

    while queue:
        entity, depth = queue.pop(0)

        if not isinstance(entity, Channel):
            continue
        if entity.id in visited_ids:
            continue
        visited_ids.add(entity.id)

        kind = "📢頻道" if getattr(entity, "broadcast", False) else "👥群組"
        indent = "  " * depth
        print(f"\n{indent}{'─'*40}")
        print(f"{indent}[深度 {depth}] {kind}: {entity.title}")

        # 確認連線
        try:
            if not client.is_connected():
                print(f"{indent}  🔄 重新連線中...")
                await client.connect()
        except Exception:
            print(f"{indent}  ⚠ 重連失敗，等待 30 秒...")
            await asyncio.sleep(30)
            try:
                await client.connect()
            except Exception:
                print(f"{indent}  ❌ 重連失敗，跳過此群組")
                continue

        # 1. 檢查是否可抓取
        if getattr(entity, "megagroup", False):
            try:
                scrape_count, total = await check_scrapable(client, entity)
                if scrape_count >= 50:
                    print(f"{indent}  ✓ 可抓取 ({scrape_count}/{total} 人)")
                    if str(entity.id) in scraped_ids:
                        print(f"{indent}  ⏭ 已爬過，跳過")
                    else:
                        all_scrapable.append(entity)
                        print(f"{indent}  📥 爬取中...", end="", flush=True)
                        members = await scrape_members(client, entity)
                        all_members.extend(members)
                        print(f" {len(members)} 位")
                else:
                    print(f"{indent}  ✗ 不可抓取 ({scrape_count}/{total} 人)")
            except (ConnectionError, TimeoutError, OSError) as e:
                print(f"{indent}  ⚠ 連線中斷: {type(e).__name__}，等待 30 秒...")
                await asyncio.sleep(30)
                continue

        # 2. 掃描訊息中的連結（如果還沒到最大深度）
        if depth < max_depth:
            print(f"{indent}  🔍 掃描訊息...", end="", flush=True)
            try:
                inv_hashes, unames, msg_count = await extract_links(client, entity)
                new_inv = inv_hashes - visited_links
                new_unames = unames - visited_links
                visited_links.update(inv_hashes)
                visited_links.update(unames)
                total_new = len(new_inv) + len(new_unames)
                print(f" {msg_count} 則，找到 {total_new} 個新連結")
            except (ConnectionError, TimeoutError, OSError) as e:
                print(f" 連線中斷: {type(e).__name__}，等待 30 秒...")
                await asyncio.sleep(30)
                continue
            except Exception as e:
                print(f" 掃描失敗: {type(e).__name__}")
                continue

            if total_new == 0:
                continue

            # 3. 處理新找到的連結
            new_entities = []

            # 處理邀請連結
            for inv_hash in sorted(new_inv):
                print(f"{indent}    +{inv_hash[:20]:<20s}", end=" ", flush=True)
                try:
                    ent, name, status, join_count = await try_join_invite(client, inv_hash, join_count)
                    if ent and isinstance(ent, Channel) and ent.id not in visited_ids:
                        if is_relevant(getattr(ent, "title", "")):
                            print(f"→ {name[:25]} ({status})")
                            new_entities.append(ent)
                        else:
                            print(f"→ {name[:25]} (跳過:非中文)")
                    else:
                        print(f"→ {name[:25]} ({status})")
                except (ConnectionError, TimeoutError, OSError):
                    print(f"→ 連線中斷，跳過")
                    await asyncio.sleep(15)
                delay = random.randint(*CHECK_DELAY)
                await asyncio.sleep(delay)

            # 處理公開連結
            for uname in sorted(new_unames):
                print(f"{indent}    @{uname:<20s}", end=" ", flush=True)
                try:
                    ent, name, status, join_count = await try_join_username(client, uname, join_count)
                    if ent and isinstance(ent, Channel) and ent.id not in visited_ids:
                        if is_relevant(getattr(ent, "title", "")):
                            print(f"→ {name[:25]} ({status})")
                            new_entities.append(ent)
                        else:
                            print(f"→ {name[:25]} (跳過:非中文)")
                    else:
                        print(f"→ {name[:25]} ({status})")
                except (ConnectionError, TimeoutError, OSError):
                    print(f"→ 連線中斷，跳過")
                    await asyncio.sleep(15)
                delay = random.randint(*CHECK_DELAY)
                await asyncio.sleep(delay)

            # 加入佇列繼續深挖
            for ent in new_entities:
                queue.append((ent, depth + 1))

            if new_entities:
                print(f"{indent}  → {len(new_entities)} 個新群組加入佇列 (深度 {depth+1})")
            print(f"{indent}  📊 已加入 {join_count}/{MAX_JOINS_PER_RUN} 個群組")

    # 儲存結果
    print(f"\n{'='*55}")
    print(f"深度爬取完成!")
    print(f"  掃描群組: {len(visited_ids)} 個")
    print(f"  處理連結: {len(visited_links)} 個")
    print(f"  可抓取群組: {len(all_scrapable)} 個")

    if all_members:
        # 去重
        seen = set()
        unique = []
        for m in all_members:
            uid = m["user_id"]
            if uid not in seen:
                seen.add(uid)
                unique.append(m)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(OUTPUT_DIR, f"deep_crawl_members_{timestamp}.csv")
        fieldnames = ["user_id", "username", "first_name", "last_name", "phone", "is_bot", "source_group", "source_group_id"]
        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(unique)

        print(f"  總成員: {len(unique)} 位不重複")
        print(f"  儲存至: {filepath}")

        # 自動合併去重
        print("\n自動合併去重中...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])
    else:
        print("  沒有抓到任何成員")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
