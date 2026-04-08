"""
TG 自動化獲客系統 - 主選單
一行指令啟動，全部可視化操作，完全不需要接觸程式碼

使用方式:
  cd ~/Downloads/tg-scraper-toolkit
  source venv/bin/activate
  python3 tg.py
"""

import os
import sys
import subprocess

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable
CONFIG_FILE = os.path.join(TOOLKIT_DIR, "config.py")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    clear()
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       TG 自動化獲客系統 v2.0                  ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")


def pause():
    input("\n  按 Enter 返回主選單...")


def run_script(script_name):
    env = os.environ.copy()
    env["PYTHONPATH"] = TOOLKIT_DIR
    subprocess.run([PYTHON, os.path.join(TOOLKIT_DIR, script_name)], env=env)


# ============================================================
# 首次設定引導（config.py 不存在時自動觸發）
# ============================================================

def first_time_setup():
    """首次使用引導，自動產生 config.py"""
    header()
    print("  \033[1;33m歡迎！首次使用需要進行初始設定\033[0m\n")
    print("  請準備好以下資訊：")
    print("    1. 你的 TG 手機號碼")
    print("    2. API ID 和 API Hash（從 my.telegram.org 取得）")
    print("    3. 群組邀請連結（選填）")
    print()

    input("  準備好了按 Enter 開始...")
    print()

    # 手機號碼
    while True:
        phone = input("  你的 TG 手機號碼（含國碼，如 +886912345678）: ").strip()
        if phone.startswith("+") and len(phone) > 8:
            break
        if phone and not phone.startswith("+"):
            phone = "+886" + phone.lstrip("0")
            confirm = input(f"  自動加國碼: {phone}，正確嗎？(y/n): ").strip().lower()
            if confirm == "y":
                break
        print("  \033[31m請輸入正確的手機號碼\033[0m")

    # API ID
    while True:
        api_id = input("  API ID（數字）: ").strip()
        if api_id.isdigit():
            break
        print("  \033[31m請輸入數字\033[0m")

    # API Hash
    while True:
        api_hash = input("  API Hash（字串）: ").strip()
        if len(api_hash) > 10:
            break
        print("  \033[31m請輸入正確的 API Hash\033[0m")

    # 群組連結
    group_link = input("  群組邀請連結（選填，按 Enter 跳過）: ").strip()
    if not group_link:
        group_link = "https://t.me/+xxxxxxxx"

    # Bot Token
    bot_token = input("  Bot Token（選填，按 Enter 跳過）: ").strip()

    # 產生 config.py
    config_content = f'''"""
Telegram 工具包 - 共用設定檔
由系統自動產生，可透過主選單 [2] 修改
"""

import csv
import glob
import os

# ============================================================
# Telegram API 設定
# ============================================================
API_ID = {api_id}
API_HASH = "{api_hash}"
PHONE = "{phone}"
SESSION_NAME = "tg_session"

# ============================================================
# 路徑設定
# ============================================================
TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(TOOLKIT_DIR, "data")

# ============================================================
# 1_scraper.py 設定
# ============================================================
SEARCH_KEYWORDS = [
    "交友", "成人交友", "台灣", "台北", "台中", "高雄",
    "外送茶", "喝茶", "品茶", "茶友", "約砲",
    "老司機", "紳士", "深夜", "福利", "18禁", "俱樂部",
]

# ============================================================
# 2_forwarder.py 設定
# ============================================================
TARGET_CHANNEL = ""

# ============================================================
# 3_dm.py 設定
# ============================================================
GROUP_INVITE_LINK = "{group_link}"

DM_MIN_DELAY = 60
DM_MAX_DELAY = 180
DM_TYPING_DELAY = 3
DM_SPLIT_DELAY_MIN = 5
DM_SPLIT_DELAY_MAX = 15
DM_DAILY_LIMIT = 30
DM_SENT_LOG = os.path.join(TOOLKIT_DIR, "dm_sent_log.csv")
DM_CONTACT_FILES = [
    os.path.join(TOOLKIT_DIR, "all_members.csv"),
]

# ============================================================
# 工具函式
# ============================================================

def get_scraped_group_ids():
    """讀取所有已爬過的群組 ID"""
    scraped = set()
    for f in glob.glob(os.path.join(DATA_DIR, "*.csv")):
        try:
            with open(f, "r", encoding="utf-8-sig") as fh:
                reader = csv.DictReader(fh)
                if "source_group_id" not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    gid = row.get("source_group_id", "")
                    if gid:
                        scraped.add(str(gid))
        except Exception:
            pass
    return scraped
'''

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(config_content)

    # 更新 5_bot.py 的 token（如果有填）
    if bot_token:
        bot_file = os.path.join(TOOLKIT_DIR, "5_bot.py")
        if os.path.exists(bot_file):
            with open(bot_file, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace('BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"', f'BOT_TOKEN = "{bot_token}"')
            with open(bot_file, "w", encoding="utf-8") as f:
                f.write(content)

    # 建立必要目錄
    os.makedirs(os.path.join(TOOLKIT_DIR, "data"), exist_ok=True)
    os.makedirs(os.path.join(TOOLKIT_DIR, "sessions"), exist_ok=True)

    print(f"\n  \033[32m初始設定完成！\033[0m")
    print(f"  設定檔已儲存: config.py")
    print(f"  之後可透過主選單 [2] 修改設定\n")
    input("  按 Enter 進入主選單...")


# ============================================================
# 環境檢查
# ============================================================

def check_environment():
    """檢查必要套件是否已安裝"""
    try:
        import telethon
        return True
    except ImportError:
        header()
        print("  \033[31m尚未安裝必要套件\033[0m\n")
        print("  請先執行：")
        print(f"    pip install -r {os.path.join(TOOLKIT_DIR, 'requirements.txt')}\n")

        install = input("  要自動安裝嗎？(y/n): ").strip().lower()
        if install == "y":
            subprocess.run([PYTHON, "-m", "pip", "install", "-r",
                          os.path.join(TOOLKIT_DIR, "requirements.txt")])
            print("\n  \033[32m安裝完成！\033[0m")
            input("  按 Enter 繼續...")
            return True
        return False


# ============================================================
# 主選單
# ============================================================

def main_menu():
    while True:
        header()
        print("  \033[1;33m【設定】\033[0m")
        print("    [1] 帳號管理（新增/查看/刪除帳號）")
        print("    [2] 系統設定（群組連結/Bot/延遲參數）")
        print("    [3] Bot 客服管理（新增/刪除客服）")
        print()
        print("  \033[1;33m【採集】\033[0m")
        print("    [4] 撈名單（群組成員撈取）")
        print("    [5] 抓取圖文（頻道圖片+文字）")
        print()
        print("  \033[1;33m【發佈】\033[0m")
        print("    [6] 轉發到頻道（重新發送，不顯示來源）")
        print("    [7] 發佈到頻道（從爬取資料發佈）")
        print()
        print("  \033[1;33m【導流】\033[0m")
        print("    [8] 單帳號私訊")
        print("    [9] 多帳號私訊（自動輪換排程）")
        print()
        print("  \033[1;33m【運行】\033[0m")
        print("   [10] 啟動客服 Bot")
        print("   [11] 背景啟動 Bot（關終端也不停）")
        print()
        print("    [0] 離開")
        print()

        choice = input("  請選擇 > ").strip()

        if choice == "1":
            run_script("setup_accounts.py")
        elif choice == "2":
            run_script("setup_config.py")
        elif choice == "3":
            run_script("setup_agents.py")
        elif choice == "4":
            run_script("1_scraper.py")
        elif choice == "5":
            env = os.environ.copy()
            env["PYTHONPATH"] = TOOLKIT_DIR
            subprocess.run([PYTHON, os.path.join(TOOLKIT_DIR, "_archive", "girl_scraper.py")], env=env)
        elif choice == "6":
            run_script("2_forwarder.py")
        elif choice == "7":
            run_script("4_publisher.py")
        elif choice == "8":
            run_script("3_dm.py")
        elif choice == "9":
            run_script("3_dm_multi.py")
        elif choice == "10":
            run_script("5_bot.py")
        elif choice == "11":
            bot_path = os.path.join(TOOLKIT_DIR, "5_bot.py")
            log_path = os.path.join(TOOLKIT_DIR, "bot.log")
            env_str = f"PYTHONPATH={TOOLKIT_DIR}"
            os.system(f"nohup env {env_str} {PYTHON} {bot_path} > {log_path} 2>&1 &")
            print(f"\n  \033[32mBot 已在背景啟動!\033[0m")
            print(f"  日誌: {log_path}")
            print(f"  停止: pkill -f 5_bot.py")
            pause()
        elif choice == "0":
            print("\n  再見!\n")
            break
        else:
            print("\n  無效選擇")
            pause()


# ============================================================
# 啟動
# ============================================================

if __name__ == "__main__":
    # 1. 檢查套件
    if not check_environment():
        sys.exit(1)

    # 2. 首次設定（config.py 不存在時）
    if not os.path.exists(CONFIG_FILE):
        first_time_setup()

    # 3. 進入主選單
    main_menu()
