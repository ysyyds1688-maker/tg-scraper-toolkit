"""
多帳號輪換私訊工具
功能：
  - 讀取 accounts.json 中所有帳號
  - 每個帳號獨立 API_ID/HASH + 代理 IP
  - 自動分配名單（不重疊）
  - 帳號輪換發送，被限速自動切換下一個
  - 共享已發送記錄，避免重複
  - 每個帳號不同延遲和每日上限
"""

import asyncio
import csv
import json
import os
import random
from datetime import datetime

from telethon import TelegramClient, errors
from messages import get_personalized_messages
import socks

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_FILE = os.path.join(TOOLKIT_DIR, "accounts.json")
SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
STATE_FILE = os.path.join(TOOLKIT_DIR, "dm_state.json")


# ============================================================
# 設定（從 config.py 讀取共用設定）
# ============================================================
from config import GROUP_INVITE_LINK, DM_TYPING_DELAY, DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX


# ============================================================
# 帳號與狀態管理
# ============================================================

def load_accounts():
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [a for a in data["accounts"] if a.get("enabled", True)]


def make_proxy(proxy_conf):
    if not proxy_conf:
        return None
    proxy_type = proxy_conf.get("type", "socks5").lower()
    type_map = {"socks5": socks.SOCKS5, "socks4": socks.SOCKS4, "http": socks.HTTP}
    proxy = (
        type_map.get(proxy_type, socks.SOCKS5),
        proxy_conf["host"],
        proxy_conf["port"],
    )
    user = proxy_conf.get("username", "")
    pwd = proxy_conf.get("password", "")
    if user:
        proxy = proxy + (True, user, pwd)
    return proxy


def load_state():
    """載入每個帳號的今日發送狀態"""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
    # 如果日期不是今天，重置計數
    today = datetime.now().strftime("%Y-%m-%d")
    if state.get("date") != today:
        return {"date": today}
    return state


def save_state(state):
    state["date"] = datetime.now().strftime("%Y-%m-%d")
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_account_sent_count(state, account_name):
    return state.get(account_name, 0)


def increment_account_sent(state, account_name):
    state[account_name] = state.get(account_name, 0) + 1
    save_state(state)


# ============================================================
# 名單管理
# ============================================================

def load_contacts(file_paths):
    """讀取所有名單"""
    contacts = []
    seen = set()
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
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
                contacts.append({
                    "user_id": int(uid) if uid.isdigit() else None,
                    "username": username or None,
                    "name": name,
                })
    return contacts


def load_sent_log():
    sent = set()
    if not os.path.exists(SENT_LOG):
        return sent
    with open(SENT_LOG, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ident = row.get("identifier", "")
            if ident:
                sent.add(ident)
    return sent


def get_identifier(contact):
    if contact["username"]:
        return f"username:{contact['username']}"
    if contact["user_id"]:
        return f"id:{contact['user_id']}"
    return None


def log_send(account_name, identifier, name, status, note=""):
    exists = os.path.exists(SENT_LOG)
    with open(SENT_LOG, "a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(["timestamp", "account", "identifier", "name", "status", "note"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            account_name, identifier, name, status, note,
        ])


# ============================================================
# 發送引擎
# ============================================================

async def send_to_contact(client, contact, account_name):
    """對一個聯絡人發送擬人化訊息"""
    identifier = get_identifier(contact)
    name = contact["name"]

    # 解析用戶
    try:
        if contact["username"]:
            user = await client.get_entity(contact["username"])
        elif contact["user_id"]:
            user = await client.get_entity(contact["user_id"])
        else:
            return "skip"
    except errors.UsernameNotOccupiedError:
        log_send(account_name, identifier, name, "not_found")
        return "skip"
    except Exception as e:
        log_send(account_name, identifier, name, "resolve_error", str(e))
        return "skip"

    messages = get_personalized_messages(name, GROUP_INVITE_LINK)

    try:
        for i, msg in enumerate(messages):
            async with client.action(user, "typing"):
                typing_time = max(DM_TYPING_DELAY, len(msg) * 0.05)
                await asyncio.sleep(typing_time)
            await client.send_message(user, msg)
            if i < len(messages) - 1:
                await asyncio.sleep(random.uniform(DM_SPLIT_DELAY_MIN, DM_SPLIT_DELAY_MAX))

        log_send(account_name, identifier, name, "success", f"{len(messages)} 段")
        return "success"

    except errors.FloodWaitError as e:
        log_send(account_name, identifier, name, "flood_wait", f"{e.seconds}s")
        return f"flood:{e.seconds}"

    except errors.UserPrivacyRestrictedError:
        log_send(account_name, identifier, name, "privacy")
        return "skip"

    except errors.PeerFloodError:
        log_send(account_name, identifier, name, "peer_flood")
        return "peer_flood"

    except Exception as e:
        log_send(account_name, identifier, name, "error", str(e))
        return "skip"


# ============================================================
# 單帳號發送（跑完額度後斷線）
# ============================================================

async def run_single_account(acc, pending, sent_set, state):
    """用一個帳號發送直到額度用完，回傳已處理的數量"""
    acc_name = acc["name"]
    sent_today = get_account_sent_count(state, acc_name)
    remaining = acc["daily_limit"] - sent_today

    if remaining <= 0:
        print(f"  ⏭ {acc_name} 今日額度已用完")
        return 0

    proxy = make_proxy(acc.get("proxy"))
    try:
        client = TelegramClient(acc["session_name"], acc["api_id"], acc["api_hash"], proxy=proxy)
        await client.start()
        me = await client.get_me()
        print(f"  ✅ {acc_name} 登入: {me.first_name}")
    except Exception as e:
        print(f"  ❌ {acc_name} 登入失敗: {e}")
        return 0

    success = 0
    fail = 0
    processed = 0

    try:
        for contact in pending:
            if processed >= remaining:
                break

            identifier = get_identifier(contact)
            if identifier in sent_set:
                continue

            print(f"    [{acc_name}] #{processed+1}/{remaining} → {contact['name']}")

            result = await send_to_contact(client, contact, acc_name)

            if result == "success":
                success += 1
                increment_account_sent(state, acc_name)
                sent_set.add(identifier)
                print(f"      ✅ 成功")
            elif result == "peer_flood":
                print(f"      🚫 帳號被限制，提前結束")
                break
            elif isinstance(result, str) and result.startswith("flood:"):
                wait = int(result.split(":")[1])
                if wait > 300:
                    print(f"      ⚠️  限流 {wait}s，太久，提前結束")
                    break
                else:
                    print(f"      ⚠️  限流 {wait}s，等待中...")
                    await asyncio.sleep(wait + 10)
            else:
                fail += 1
                print(f"      ⏭ 跳過")

            processed += 1

            # 延遲
            if processed < remaining:
                delay = random.uniform(acc["delay_min"], acc["delay_max"])
                print(f"      ⏳ {delay:.0f}s")
                await asyncio.sleep(delay)

    except KeyboardInterrupt:
        print(f"\n  ⚠️ 使用者中斷 {acc_name}")

    await client.disconnect()
    print(f"  📊 {acc_name} 完成: 成功 {success}, 跳過 {fail}")
    return processed


# ============================================================
# 主程式
# ============================================================

async def main():
    print("=" * 55)
    print("  多帳號輪換私訊工具")
    print("  （一個帳號跑完 → 休息 → 自動換下一個）")
    print("=" * 55)

    accounts = load_accounts()
    print(f"\n📱 帳號數: {len(accounts)}")
    for acc in accounts:
        proxy_info = f"代理 {acc['proxy']['host']}" if acc.get("proxy") else "直連"
        print(f"  • {acc['name']} | 上限 {acc['daily_limit']}/天 | 延遲 {acc['delay_min']}-{acc['delay_max']}s | {proxy_info}")

    # 載入名單
    from config import DM_CONTACT_FILES
    contacts = load_contacts(DM_CONTACT_FILES)
    sent_set = load_sent_log()
    state = load_state()

    pending = [c for c in contacts if get_identifier(c) not in sent_set]
    print(f"\n📋 名單: {len(contacts)} 人, 已發 {len(sent_set)}, 待發 {len(pending)}")

    # 顯示各帳號狀態
    total_quota = 0
    for acc in accounts:
        sent_today = get_account_sent_count(state, acc["name"])
        remaining = max(0, acc["daily_limit"] - sent_today)
        total_quota += remaining
        print(f"  • {acc['name']}: 今日已發 {sent_today}/{acc['daily_limit']}, 剩餘 {remaining}")

    if total_quota == 0:
        print("\n所有帳號今日額度已用完")
        return

    if not pending:
        print("\n沒有待發名單")
        return

    # 帳號間休息時間
    rest_input = input(f"\n帳號之間休息幾分鐘？(預設 30): ").strip()
    rest_minutes = int(rest_input) if rest_input.isdigit() else 30

    print(f"\n⏱ 排程:")
    for i, acc in enumerate(accounts):
        sent_today = get_account_sent_count(state, acc["name"])
        remaining = max(0, acc["daily_limit"] - sent_today)
        if remaining == 0:
            continue
        est_time = remaining * (acc["delay_min"] + acc["delay_max"]) / 2 / 60
        print(f"  {i+1}. {acc['name']} → 發 {remaining} 人 (約 {est_time:.0f} 分鐘)")
        if i < len(accounts) - 1:
            print(f"     ↓ 休息 {rest_minutes} 分鐘")

    confirm = input(f"\n確認開始自動排程？(y/n): ").strip().lower()
    if confirm != "y":
        return

    # ============================================
    # 預先分配名單 — 每個帳號拿到完全不同的人
    # ============================================
    assignment = {}  # {帳號名: [聯絡人列表]}
    idx = 0

    active_accounts = []
    for acc in accounts:
        sent_today = get_account_sent_count(state, acc["name"])
        remaining = max(0, acc["daily_limit"] - sent_today)
        if remaining > 0:
            active_accounts.append((acc, remaining))

    random.shuffle(active_accounts)  # 隨機順序

    for acc, remaining in active_accounts:
        batch = pending[idx:idx + remaining]
        if not batch:
            break
        assignment[acc["name"]] = batch
        idx += len(batch)

    print(f"\n📦 名單預分配（每個帳號的人完全不重疊）:")
    for acc, _ in active_accounts:
        batch = assignment.get(acc["name"], [])
        print(f"  • {acc['name']} → {len(batch)} 人")

    # 開始逐帳號執行
    print(f"\n{'='*55}")
    print("開始自動排程\n")

    total_processed = 0

    try:
        for i, (acc, _) in enumerate(active_accounts):
            acc_name = acc["name"]
            batch = assignment.get(acc_name, [])
            if not batch:
                continue

            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'─'*55}")
            print(f"🕐 [{now}] 啟動 {acc_name}（分配 {len(batch)} 人）")
            print(f"{'─'*55}")

            processed = await run_single_account(acc, batch, sent_set, state)
            total_processed += processed

            # 帳號間休息（最後一個不用）
            remaining_accounts = [(a, b) for a, b in active_accounts[i+1:]
                                  if assignment.get(a["name"])]
            if remaining_accounts:
                from datetime import timedelta
                resume_time = (datetime.now() + timedelta(minutes=rest_minutes)).strftime("%H:%M")
                print(f"\n  😴 {acc_name} 完成，休息 {rest_minutes} 分鐘...")
                print(f"     下一個帳號預計 {resume_time} 啟動")
                await asyncio.sleep(rest_minutes * 60)

    except KeyboardInterrupt:
        print("\n\n⚠️  使用者中斷，進度已保存")

    print(f"\n{'='*55}")
    print(f"📊 今日總計:")
    print(f"   處理: {total_processed} 人")
    for acc in accounts:
        sent_today = get_account_sent_count(state, acc["name"])
        print(f"   {acc['name']}: {sent_today}/{acc['daily_limit']}")
    print(f"   記錄: {SENT_LOG}")
    print("完成!")


if __name__ == "__main__":
    asyncio.run(main())
