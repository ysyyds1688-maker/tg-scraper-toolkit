"""
TG 自動化獲客系統 - 主選單
所有功能透過選單操作，不需要接觸程式碼
"""

import os
import sys
import subprocess

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


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
    input("\n按 Enter 返回主選單...")


def run_script(script_name):
    env = os.environ.copy()
    env["PYTHONPATH"] = TOOLKIT_DIR
    subprocess.run([PYTHON, os.path.join(TOOLKIT_DIR, script_name)], env=env)


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
            print(f"\n  Bot 已在背景啟動!")
            print(f"  日誌: {log_path}")
            print(f"  停止: pkill -f 5_bot.py")
            pause()
        elif choice == "0":
            print("\n  再見!\n")
            break
        else:
            print("\n  無效選擇")
            pause()


if __name__ == "__main__":
    main_menu()
