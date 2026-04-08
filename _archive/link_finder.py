"""
從你已加入的頻道/群組訊息中，提取所有 t.me 群組連結
然後自動加入、檢查、爬取可抓的群組成員
"""

import asyncio
import csv
import os
import re
import sys
from datetime import datetime

from config import API_ID, API_HASH, SESSION_NAME, get_scraped_group_ids
from telethon import TelegramClient
from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
from telethon.tl.functions.messages import ImportChatInviteRequest, CheckChatInviteRequest
from telethon.tl.types import (
    ChannelParticipantsSearch, Channel,
    ChatInvite, ChatInviteAlready, ChatInvitePeek,
)
from telethon.errors import (
    ChatAdminRequiredError,
    FloodWaitError,
    InviteHashExpiredError,
    UserAlreadyParticipantError,
    ChannelPrivateError,
    InviteHashInvalidError,
)


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# 每個頻道掃描幾則訊息（越多越慢，但找到越多連結）
SCAN_MESSAGES = 1000

# t.me 連結的正則 - 分別匹配公開連結和邀請連結
# group1 = invite hash (from +xxx or joinchat/xxx), group2 = public username
TG_LINK_RE = re.compile(
    r'(?:https?://)?(?:t\.me|telegram\.me)/(?:(?:\+|joinchat/)([a-zA-Z0-9_\-]+)|([a-zA-Z0-9_]+))',
    re.IGNORECASE,
)


async def extract_links_from_dialog(client, dialog, limit):
    """從一個頻道/群組的訊息中提取所有 t.me 連結"""
    invite_hashes = set()  # 邀請連結 (+xxx)
    usernames = set()      # 公開連結
    count = 0

    def process_text(text):
        for match in TG_LINK_RE.finditer(text):
            invite_hash = match.group(1)
            username = match.group(2)
            if invite_hash:
                invite_hashes.add(invite_hash)
            elif username:
                usernames.add(username)

    async for msg in client.iter_messages(dialog.entity, limit=limit):
        if msg.text:
            process_text(msg.text)
        if msg.reply_markup:
            for row in getattr(msg.reply_markup, "rows", []):
                for btn in row.buttons:
                    url = getattr(btn, "url", None)
                    if url:
                        process_text(url)
        count += 1
    return invite_hashes, usernames, count


async def resolve_invite(client, invite_hash):
    """解析邀請連結，檢查是群組還是頻道"""
    try:
        result = await client(CheckChatInviteRequest(hash=invite_hash))

        if isinstance(result, ChatInviteAlready):
            # 已經加入的群組
            chat = result.chat
            if isinstance(chat, Channel):
                title = chat.title
                is_mega = getattr(chat, "megagroup", False)
                count = getattr(chat, "participants_count", 0) or 0
                return chat, title, is_mega, count, "已加入"
            return None, "", False, 0, "已加入(非Channel)"

        elif isinstance(result, (ChatInvite, ChatInvitePeek)):
            # 還沒加入，可以預覽資訊
            title = getattr(result, "title", "未知")
            is_mega = getattr(result, "megagroup", False)
            count = getattr(result, "participants_count", 0) or 0
            chat = getattr(result, "chat", None)
            return chat, title, is_mega, count, "未加入"

        return None, "", False, 0, "未知類型"

    except (InviteHashExpiredError, InviteHashInvalidError):
        return None, "", False, 0, "連結失效"
    except FloodWaitError as e:
        print(f"      限速，等待 {e.seconds} 秒...")
        await asyncio.sleep(e.seconds)
        return None, "", False, 0, "限速跳過"
    except Exception as e:
        return None, "", False, 0, f"錯誤: {type(e).__name__}"


async def resolve_and_check(client, entity):
    """檢查一個已知 entity 是否可抓取"""
    if not isinstance(entity, Channel):
        return None, "非頻道/群組"
    if not getattr(entity, "megagroup", False):
        return entity, "頻道(非群組)"

    try:
        full = await client(GetFullChannelRequest(entity))
        can_view = getattr(full.full_chat, "can_view_participants", False)
        count = getattr(full.full_chat, "participants_count", 0)

        if not can_view:
            return entity, f"禁止查看成員 ({count}人)"

        test = await client(GetParticipantsRequest(
            channel=entity,
            filter=ChannelParticipantsSearch(""),
            offset=0,
            limit=10,
            hash=0,
        ))
        if test.count < 50:
            return entity, f"可抓數太少 ({test.count}/{count})"

        return entity, f"可抓取 ({test.count}人)"

    except ChatAdminRequiredError:
        return entity, f"需管理員權限"
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return None, "限速跳過"
    except Exception as e:
        return None, f"錯誤: {type(e).__name__}"


async def resolve_username(client, username):
    """解析公開 username"""
    try:
        entity = await client.get_entity(username)
        return await resolve_and_check(client, entity)
    except (ChannelPrivateError, ValueError):
        return None, "無法解析"
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        return None, "限速跳過"
    except Exception as e:
        return None, f"錯誤: {type(e).__name__}"


async def scrape_members(client, entity):
    """抓取群組成員"""
    members = []
    seen = set()
    offset = 0

    while True:
        try:
            participants = await client(GetParticipantsRequest(
                channel=entity,
                filter=ChannelParticipantsSearch(""),
                offset=offset,
                limit=200,
                hash=0,
            ))
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            continue
        except Exception:
            break

        if not participants.users:
            break

        for user in participants.users:
            if user.id not in seen:
                seen.add(user.id)
                members.append({
                    "user_id": user.id,
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "phone": user.phone or "",
                    "is_bot": user.bot or False,
                    "source_group": entity.title,
                    "source_group_id": entity.id,
                })

        offset += len(participants.users)
        if offset >= participants.count:
            break

    return members


async def main():
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    await client.start()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Phase 1: 從已加入的群組中提取連結
    print("Phase 1: 從你的群組/頻道中提取 t.me 連結\n")
    dialogs = await client.get_dialogs()

    source_groups = []
    for d in dialogs:
        if d.is_group or d.is_channel:
            source_groups.append(d)

    print(f"你的群組/頻道列表:")
    for i, d in enumerate(source_groups):
        print(f"  [{i+1:2d}] {d.title}")

    print(f"\n要從哪些群組提取連結？")
    print(f"  [a] 全部掃描")
    print(f"  或輸入編號，逗號分隔 (例: 6,8,10,12,16)")
    choice = input("\n選擇: ").strip()

    if choice.lower() == "a":
        scan_targets = source_groups
    else:
        indices = [int(n.strip()) - 1 for n in choice.split(",")]
        scan_targets = [source_groups[i] for i in indices if 0 <= i < len(source_groups)]

    all_invite_hashes = set()
    all_usernames = set()
    for d in scan_targets:
        print(f"  掃描: {d.title[:50]}...", end="", flush=True)
        invite_hashes, usernames, msg_count = await extract_links_from_dialog(client, d, SCAN_MESSAGES)
        all_invite_hashes.update(invite_hashes)
        all_usernames.update(usernames)
        total = len(invite_hashes) + len(usernames)
        print(f" {msg_count} 則訊息，找到 {total} 個連結 (公開:{len(usernames)} 邀請:{len(invite_hashes)})")
        await asyncio.sleep(0.3)

    # 過濾掉常見非群組的 username
    skip = {"s", "proxy", "socks", "share", "addstickers", "addemoji",
            "setlanguage", "addtheme", "c", "iv", "boost", "addlist", "username"}
    filtered_usernames = {u for u in all_usernames if u.lower() not in skip and len(u) > 2}

    print(f"\n共找到: 公開連結 {len(filtered_usernames)} 個 + 邀請連結 {len(all_invite_hashes)} 個\n")

    # Phase 2: 逐一檢查
    print("Phase 2: 檢查連結\n")
    scrapable = []
    joinable_groups = []  # 未加入但是 megagroup 的邀請連結
    checked = 0
    total = len(filtered_usernames) + len(all_invite_hashes)

    # 2a: 檢查公開 username
    print("--- 公開連結 ---")
    for uname in sorted(filtered_usernames):
        checked += 1
        print(f"  [{checked}/{total}] t.me/{uname:<30s}", end=" ", flush=True)
        entity, status = await resolve_username(client, uname)
        print(f"→ {status}")
        if entity and "可抓取" in status:
            scrapable.append(entity)
        await asyncio.sleep(0.5)

    # 2b: 檢查邀請連結
    print("\n--- 邀請連結 ---")
    for inv_hash in sorted(all_invite_hashes):
        checked += 1
        print(f"  [{checked}/{total}] t.me/+{inv_hash:<28s}", end=" ", flush=True)
        chat, title, is_mega, count, join_status = await resolve_invite(client, inv_hash)
        type_str = "群組" if is_mega else "頻道"

        if join_status == "連結失效":
            print(f"→ 連結失效")
        elif join_status == "已加入" and chat:
            # 已加入，直接檢查能不能抓
            entity, check_status = await resolve_and_check(client, chat)
            print(f"→ {title[:30]} ({type_str},{count}人) [已加入] {check_status}")
            if entity and "可抓取" in check_status:
                scrapable.append(entity)
        elif join_status == "未加入":
            print(f"→ {title[:30]} ({type_str},{count}人) [未加入]", end="")
            if is_mega:
                print(f" ← 可嘗試加入")
                joinable_groups.append((inv_hash, title, count))
            else:
                print(f" (頻道，跳過)")
        else:
            print(f"→ {join_status}")
        await asyncio.sleep(0.5)

    # 2c: 詢問是否加入未加入的群組
    if joinable_groups:
        print(f"\n發現 {len(joinable_groups)} 個未加入的群組(megagroup):")
        for inv_hash, title, count in joinable_groups:
            print(f"  - {title} ({count}人)")
        join_confirm = input(f"\n要自動加入這些群組並嘗試抓取嗎？(y/n): ").strip().lower()
        if join_confirm == "y":
            for inv_hash, title, count in joinable_groups:
                print(f"  加入: {title}...", end="", flush=True)
                try:
                    updates = await client(ImportChatInviteRequest(hash=inv_hash))
                    chat = updates.chats[0] if updates.chats else None
                    if chat:
                        entity, check_status = await resolve_and_check(client, chat)
                        print(f" 成功! {check_status}")
                        if entity and "可抓取" in check_status:
                            scrapable.append(entity)
                    else:
                        print(f" 加入成功但無法取得群組資訊")
                except UserAlreadyParticipantError:
                    print(f" 已經在群組中")
                except FloodWaitError as e:
                    print(f" 限速，等待 {e.seconds} 秒...")
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    print(f" 失敗: {type(e).__name__}")
                await asyncio.sleep(2)

    print(f"\n可抓取的群組: {len(scrapable)} 個")

    if not scrapable:
        print("沒有找到可抓取的群組")
        await client.disconnect()
        return

    for e in scrapable:
        count = getattr(e, "participants_count", "?")
        print(f"  ✓ {e.title} ({count} 人)")

    confirm = input(f"\n開始爬取這 {len(scrapable)} 個群組的成員？(y/n): ").strip().lower()
    if confirm != "y":
        await client.disconnect()
        return

    # Phase 3: 批次爬取
    scraped_ids = get_scraped_group_ids()
    print(f"\n已爬過的群組: {len(scraped_ids)} 個")
    print(f"\nPhase 3: 開始爬取\n")
    all_members = []

    for entity in scrapable:
        if str(entity.id) in scraped_ids:
            print(f"  ⏭ 已爬過，跳過: {entity.title}")
            continue
        print(f"  📥 {entity.title}...", end="", flush=True)
        try:
            members = await scrape_members(client, entity)
            all_members.extend(members)
            print(f" {len(members)} 位成員")
        except Exception as e:
            print(f" 失敗: {e}")
        await asyncio.sleep(1)

    # 儲存
    if all_members:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 去重
        seen = set()
        unique = []
        for m in all_members:
            if m["user_id"] not in seen:
                seen.add(m["user_id"])
                unique.append(m)

        filepath = os.path.join(OUTPUT_DIR, f"discovered_members_{timestamp}.csv")
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=all_members[0].keys())
            writer.writeheader()
            writer.writerows(unique)

        print(f"\n{'='*60}")
        print(f"完成! 共 {len(unique)} 位不重複成員")
        print(f"儲存至: {filepath}")

        # 自動合併去重
        print("\n自動合併去重中...")
        import subprocess
        subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "merge_dedup.py")])
    else:
        print("\n沒有抓到任何成員")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
