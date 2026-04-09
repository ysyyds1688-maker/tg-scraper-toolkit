"""
全自動託管模式
一鍵啟動，按帳號角色自動分工：
  - bot 帳號 → 啟動客服 Bot
  - forwarder 帳號 → 即時監聽轉發到頻道（24 小時）
  - dm 帳號 → 每天輪換發私訊
  - scraper 帳號 → 每週一自動撈名單
"""

import asyncio
import csv
import json
import os
import re
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, TOOLKIT_DIR)
os.environ["PYTHONPATH"] = TOOLKIT_DIR

from config import (
    API_ID, API_HASH, SESSION_NAME, TOOLKIT_DIR, DATA_DIR,
    GROUP_INVITE_LINK, DM_TYPING_DELAY, DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX,
)
from telethon import TelegramClient, events, errors
from messages import get_personalized_messages
import socks

ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
STATE_FILE = os.path.join(TOOLKIT_DIR, "dm_state.json")
AUTOPILOT_LOG = os.path.join(TOOLKIT_DIR, "autopilot.log")
PYTHON = sys.executable


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(AUTOPILOT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================================
# 帳號載入
# ============================================================

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return []
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [a for a in data.get("accounts", []) if a.get("enabled", True)]


def get_accounts_by_role(accounts, role):
    return [a for a in accounts if a.get("role") == role]


def make_proxy(proxy_conf):
    if not proxy_conf:
        return None
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy_type = proxy_conf.get("type", "socks5").lower()
    proxy = (type_map.get(proxy_type, socks.SOCKS5), proxy_conf["host"], proxy_conf["port"])
    user = proxy_conf.get("username", "")
    pwd = proxy_conf.get("password", "")
    if user:
        proxy = proxy + (True, user, pwd)
    return proxy


# ============================================================
# 名單/狀態
# ============================================================

def load_contacts():
    from config import DM_CONTACT_FILES
    contacts = []
    seen = set()
    for fp in DM_CONTACT_FILES:
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    if row.get("is_bot", "").strip().lower() == "true":
                        continue
                    uid = row.get("user_id", "").strip()
                    username = row.get("username", "").strip().lstrip("@")
                    if not uid and not username:
                        continue
                    ident = username or uid
                    if ident in seen:
                        continue
                    seen.add(ident)
                    first = row.get("first_name", "").strip()
                    last = row.get("last_name", "").strip()
                    name = f"{first} {last}".strip() or username or "朋友"
                    contacts.append({"user_id": int(uid) if uid.isdigit() else None,
                                     "username": username or None, "name": name})
        except Exception:
            continue
    return contacts


def load_sent_log():
    sent = set()
    if not os.path.exists(SENT_LOG):
        return sent
    with open(SENT_LOG, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("identifier"):
                sent.add(row["identifier"])
    return sent


def get_identifier(c):
    if c["username"]:
        return f"username:{c['username']}"
    if c["user_id"]:
        return f"id:{c['user_id']}"
    return None


def log_send(account_name, identifier, name, status, note=""):
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp", "account", "identifier", "name", "status", "note"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     account_name, identifier, name, status, note])


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"date": datetime.now().strftime("%Y-%m-%d")}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    if state.get("date") != datetime.now().strftime("%Y-%m-%d"):
        return {"date": datetime.now().strftime("%Y-%m-%d")}
    return state


def save_state(state):
    state["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ============================================================
# Task 1: Bot 客服（背景）
# ============================================================

def start_bot_background():
    """背景啟動 Bot"""
    bot_path = os.path.join(TOOLKIT_DIR, "5_bot.py")
    log_path = os.path.join(TOOLKIT_DIR, "bot.log")
    if os.name == "nt":
        os.environ["PYTHONPATH"] = TOOLKIT_DIR
        subprocess.Popen([PYTHON, bot_path],
                         stdout=open(log_path, "w"), stderr=subprocess.STDOUT,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        env_str = f"PYTHONPATH={TOOLKIT_DIR}"
        os.system(f"nohup env {env_str} {PYTHON} {bot_path} > {log_path} 2>&1 &")
    log("🤖 Bot 已在背景啟動")


# ============================================================
# Task 2: 內容轉發（背景持續）
# ============================================================

BOT_USERNAME = "teaprincess_bot"
FOOTER = ("\n\n━━━━━━━━━━━━━━━\n🍵 想約這位佳麗？點擊下方從茶王客服，找茶莊的客服了解"
          "\n👉 @teaprincess_bot\n📌 聯繫時請說是「茶王推薦」的唷！")
TG_LINKS = [r"https?://t\.me/\+?\w+/?[\w]*", r"https?://telegram\.me/\+?\w+/?[\w]*", r"@[\w]{5,}"]
BLOCK_KW = ["福利", "買一送一", "半價", "現金劵", "現金券", "VIP", "vip", "免費無套",
            "名單", "LADIES LIST", "預約制", "BOOKINGS", "gleezy", "jkf699"]


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


async def task_forward(acc, source_ids, target_id):
    """用 forwarder 帳號即時監聽轉發"""
    proxy = make_proxy(acc.get("proxy"))
    client = TelegramClient(acc["session_name"] + "_fwd", acc["api_id"], acc["api_hash"], proxy=proxy)
    await client.start()
    target = await client.get_entity(target_id)
    log(f"📢 [{acc['name']}] 內容轉發啟動: 監聽 {len(source_ids)} 個來源 → {target.title}")

    count = 0
    TEMP = os.path.join(TOOLKIT_DIR, "_temp_media")

    @client.on(events.NewMessage(chats=source_ids))
    async def handler(event):
        nonlocal count
        msg = event.message
        text = (msg.text or "").strip()
        if should_skip(text):
            return
        text = replace_links(text)
        text = (text + FOOTER) if text else FOOTER.strip()
        try:
            if msg.media:
                os.makedirs(TEMP, exist_ok=True)
                fp = await client.download_media(msg, file=TEMP)
                if fp:
                    await client.send_file(target, fp, caption=text)
                    os.remove(fp)
                else:
                    await client.send_message(target, text)
            elif text:
                await client.send_message(target, text)
            count += 1
            log(f"  📢 #{count} → {(msg.text or '[媒體]')[:30]}")
        except Exception as e:
            log(f"  📢 轉發失敗: {e}")

    await client.run_until_disconnected()


# ============================================================
# Task 3: 多帳號私訊
# ============================================================

async def send_to_contact(client, contact, account_name):
    identifier = get_identifier(contact)
    name = contact["name"]
    try:
        user = await client.get_entity(contact["username"] or contact["user_id"])
    except Exception:
        log_send(account_name, identifier, name, "resolve_error")
        return "skip"

    msgs = get_personalized_messages(name, GROUP_INVITE_LINK)
    try:
        for i, msg in enumerate(msgs):
            async with client.action(user, "typing"):
                await asyncio.sleep(max(DM_TYPING_DELAY, len(msg) * 0.05))
            await client.send_message(user, msg)
            if i < len(msgs) - 1:
                await asyncio.sleep(random.uniform(DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX))
        log_send(account_name, identifier, name, "success", f"{len(msgs)} 段")
        return "success"
    except errors.FloodWaitError as e:
        log_send(account_name, identifier, name, "flood_wait", f"{e.seconds}s")
        return f"flood:{e.seconds}"
    except errors.PeerFloodError:
        log_send(account_name, identifier, name, "peer_flood")
        return "peer_flood"
    except errors.UserPrivacyRestrictedError:
        log_send(account_name, identifier, name, "privacy")
        return "skip"
    except Exception as e:
        log_send(account_name, identifier, name, "error", str(e))
        return "skip"


async def task_dm(dm_accounts):
    """多帳號輪換私訊"""
    log("📨 開始多帳號私訊")

    contacts = load_contacts()
    sent_set = load_sent_log()
    pending = [c for c in contacts if get_identifier(c) not in sent_set]
    state = load_state()

    log(f"  名單: {len(contacts)}, 已發: {len(sent_set)}, 待發: {len(pending)}")
    if not pending:
        log("  沒有待發名單")
        return

    # 預分配名單
    idx = 0
    total_success = 0

    random.shuffle(dm_accounts)

    for acc in dm_accounts:
        sent_today = state.get(acc["name"], 0)
        remaining = max(0, acc["daily_limit"] - sent_today)
        if remaining == 0:
            continue

        batch = pending[idx:idx + remaining]
        if not batch:
            break
        idx += len(batch)

        log(f"\n  [{acc['name']}] 分配 {len(batch)} 人")

        proxy = make_proxy(acc.get("proxy"))
        try:
            client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
            await client.start()
            me = await client.get_me()
            log(f"  [{acc['name']}] 登入: {me.first_name}")
        except Exception as e:
            log(f"  [{acc['name']}] 登入失敗: {e}")
            continue

        success = 0
        for i, contact in enumerate(batch):
            ident = get_identifier(contact)
            if ident in sent_set:
                continue

            log(f"    #{i+1}/{len(batch)} → {contact['name']}")
            result = await send_to_contact(client, contact, acc["name"])

            if result == "success":
                success += 1
                sent_set.add(ident)
                log(f"      ✅")
            elif result == "peer_flood":
                log(f"      🚫 帳號被限制，停止")
                break
            elif isinstance(result, str) and result.startswith("flood:"):
                wait = int(result.split(":")[1])
                if wait > 300:
                    log(f"      ⚠️ 限流太久，停止")
                    break
                log(f"      ⚠️ 限流 {wait}s")
                await asyncio.sleep(wait + 10)
            else:
                log(f"      ⏭ 跳過")

            await asyncio.sleep(random.uniform(acc["delay_min"], acc["delay_max"]))

        await client.disconnect()
        total_success += success
        state[acc["name"]] = state.get(acc["name"], 0) + success
        save_state(state)

        # 帳號間休息 30 分鐘
        if idx < len(pending):
            log(f"  [{acc['name']}] 完成 {success} 人，休息 30 分鐘...")
            await asyncio.sleep(30 * 60)

    log(f"\n📊 私訊完成: 成功 {total_success} 人")


# ============================================================
# Task 4: 撈名單
# ============================================================

async def task_scrape(scraper_accounts):
    """用探路號自動撈名單"""
    if not scraper_accounts:
        return
    acc = scraper_accounts[0]
    log("📋 開始自動撈名單")

    proxy = make_proxy(acc.get("proxy"))
    client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
    await client.start()

    from telethon.tl.functions.channels import GetFullChannelRequest, GetParticipantsRequest
    from telethon.tl.types import ChannelParticipantsSearch
    from telethon.errors import ChatAdminRequiredError

    dialogs = await client.get_dialogs()
    total = 0
    os.makedirs(DATA_DIR, exist_ok=True)

    for d in dialogs:
        entity = d.entity
        if not getattr(entity, "megagroup", False):
            continue
        try:
            full = await client(GetFullChannelRequest(entity))
            if not getattr(full.full_chat, "can_view_participants", False):
                continue
            test = await client(GetParticipantsRequest(
                channel=entity, filter=ChannelParticipantsSearch(""),
                offset=0, limit=10, hash=0))
            if test.count < 50:
                continue

            members = []
            seen = set()
            offset = 0
            while True:
                p = await client(GetParticipantsRequest(
                    channel=entity, filter=ChannelParticipantsSearch(""),
                    offset=offset, limit=200, hash=0))
                if not p.users:
                    break
                for u in p.users:
                    if u.id not in seen:
                        seen.add(u.id)
                        members.append({"user_id": u.id, "username": u.username or "",
                                        "first_name": u.first_name or "", "last_name": u.last_name or "",
                                        "phone": u.phone or "", "is_bot": u.bot or False,
                                        "source_group": d.title, "source_group_id": entity.id})
                offset += len(p.users)
                if offset >= p.count:
                    break

            if members:
                safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in d.title)[:50]
                fp = os.path.join(DATA_DIR, f"{safe}_{datetime.now().strftime('%Y%m%d')}.csv")
                with open(fp, "w", newline="", encoding="utf-8-sig") as f:
                    csv.DictWriter(f, fieldnames=members[0].keys()).writeheader()
                    csv.DictWriter(f, fieldnames=members[0].keys()).writerows(members)
                total += len(members)
                log(f"  ✅ {d.title}: {len(members)} 位")
        except (ChatAdminRequiredError, Exception):
            continue
        await asyncio.sleep(1)

    await client.disconnect()
    log(f"📊 撈名單完成: {total} 位")


# ============================================================
# 主程式
# ============================================================

async def main():
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       全自動託管模式                           ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")

    accounts = load_accounts()
    bot_accounts = get_accounts_by_role(accounts, "bot")
    scraper_accounts = get_accounts_by_role(accounts, "scraper")
    forwarder_accounts = get_accounts_by_role(accounts, "forwarder")
    dm_accounts = get_accounts_by_role(accounts, "dm")

    contacts = load_contacts()
    sent_set = load_sent_log()

    print(f"  帳號分配：")
    print(f"    🤖 Bot 管理:   {len(bot_accounts)} 個")
    print(f"    🔍 探路/撈名單: {len(scraper_accounts)} 個")
    print(f"    📢 內容轉發:   {len(forwarder_accounts)} 個")
    print(f"    📨 私訊導流:   {len(dm_accounts)} 個")
    print()
    print(f"  名單: {len(contacts)} 人（待發: {len(contacts) - len(sent_set)}）")
    print()

    # 內容轉發需要設定來源和目標
    source_ids = []
    target_input = None

    if forwarder_accounts:
        print("  ── 內容轉發設定 ──\n")
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
        await client.start()
        dialogs = await client.get_dialogs()
        groups = [d for d in dialogs if d.is_group or d.is_channel]

        for i, d in enumerate(groups):
            icon = "📢" if getattr(d.entity, "broadcast", False) else "👥"
            print(f"    [{i+1:3d}] {icon} {d.title[:45]}")

        source_input = input("\n  輸入來源編號（逗號分隔。留空跳過轉發）: ").strip()
        if source_input:
            for n in source_input.split(","):
                try:
                    source_ids.append(groups[int(n.strip()) - 1].entity.id)
                except (ValueError, IndexError):
                    pass
            if source_ids:
                target_input = input("  輸入你的頻道（username 或 ID）: ").strip()
                if target_input.lstrip("-").isdigit():
                    target_input = int(target_input)

        await client.disconnect()
        print()

    # 確認
    print("  託管模式將執行：")
    if bot_accounts:
        print("    ✅ Bot 客服（背景持續運行）")
    if forwarder_accounts and source_ids:
        print("    ✅ 內容轉發（24 小時即時監聽）")
    if dm_accounts:
        dm_total = sum(a["daily_limit"] for a in dm_accounts)
        print(f"    ✅ 私訊導流（{len(dm_accounts)} 帳號，每天 {dm_total} 人）")
    if scraper_accounts:
        print("    ✅ 撈名單（每週一自動執行）")
    print()

    confirm = input("  啟動？(y/n): ").strip().lower()
    if confirm != "y":
        return

    log("🚀 全自動託管模式啟動")
    log(f"   Bot: {len(bot_accounts)} | 轉發: {len(forwarder_accounts)} | "
        f"私訊: {len(dm_accounts)} | 撈名單: {len(scraper_accounts)}")

    # 1. 啟動 Bot（背景）
    if bot_accounts:
        start_bot_background()

    # 2. 啟動內容轉發（背景）
    forward_task = None
    if forwarder_accounts and source_ids and target_input:
        forward_task = asyncio.create_task(
            task_forward(forwarder_accounts[0], source_ids, target_input))

    # 3. 每日循環：私訊 + 每週撈名單
    last_scrape = None

    try:
        while True:
            now = datetime.now()
            log(f"\n{'='*55}")
            log(f"📅 {now.strftime('%Y-%m-%d %H:%M')} 開始今日任務")

            # 私訊
            if dm_accounts:
                await task_dm(dm_accounts)

            # 每週一撈名單
            if scraper_accounts and now.weekday() == 0 and last_scrape != now.date():
                await task_scrape(scraper_accounts)
                last_scrape = now.date()

            # 等到明天早上 8 點
            tomorrow = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0)
            wait = (tomorrow - datetime.now()).total_seconds()
            log(f"\n✅ 今日完成")
            log(f"   📢 內容轉發持續監聽中..." if forward_task else "")
            log(f"   🤖 Bot 持續運行中..." if bot_accounts else "")
            log(f"   下次私訊: {tomorrow.strftime('%Y-%m-%d %H:%M')}（{wait/3600:.1f} 小時後）")

            await asyncio.sleep(wait)

    except KeyboardInterrupt:
        log("\n⚠️ 使用者中斷，進度已保存")
        if forward_task:
            forward_task.cancel()

    input("\n按 Enter 返回主選單...")


if __name__ == "__main__":
    asyncio.run(main())
