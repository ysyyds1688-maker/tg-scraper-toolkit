"""
TG Scraper Toolkit - 主選單（方向鍵選擇）
"""

import os
import sys
import tty
import termios

SCRIPTS = [
    {
        "name": "成員爬取 (單一群組)",
        "desc": "選擇一個已加入的群組，爬取成員列表",
        "file": "member_scraper.py",
    },
    {
        "name": "批次爬取 (自動掃描所有可抓群組)",
        "desc": "掃描你加入的所有群組，自動爬取可抓的",
        "file": "batch_scraper.py",
    },
    {
        "name": "大量搜尋 (用關鍵字找新群組+爬取)",
        "desc": "用 120+ 關鍵字搜尋公開群組並自動爬取",
        "file": "mass_search.py",
    },
    {
        "name": "頻道訊息爬取",
        "desc": "抓取頻道/群組的聊天訊息和發言者",
        "file": "channel_scraper.py",
    },
    {
        "name": "連結探索 (從訊息中挖掘新群組)",
        "desc": "掃描訊息中的 t.me 連結，發現新群組並爬取",
        "file": "link_finder.py",
    },
    {
        "name": "群組診斷",
        "desc": "比較群組設定，分析為什麼能抓/不能抓",
        "file": "diagnose.py",
    },
    {
        "name": "合併去重",
        "desc": "合併所有 CSV，依 user_id 去除重複",
        "file": "merge_dedup.py",
    },
    {
        "name": "自動私訊 (DM)",
        "desc": "讀取 CSV 中的用戶，逐一發送私訊",
        "file": "auto_dm.py",
    },
    {
        "name": "網路搜尋 (DuckDuckGo+Bing 找群組連結)",
        "desc": "從搜尋引擎/目錄站搜尋 t.me 連結，或手動貼連結",
        "file": "web_finder.py",
    },
    {
        "name": "深度爬蟲 (自動加入+深挖連結)",
        "desc": "從起始群組開始，自動加入→掃連結→再加入→遞迴深挖",
        "file": "deep_crawler.py",
    },
    {
        "name": "退出群組/頻道 (騰出名額)",
        "desc": "退出不需要的頻道和群組，釋放加入名額",
        "file": "leave_channels.py",
    },
    {
        "name": "妹子資料爬取 (訊息+圖片)",
        "desc": "從茶妹頻道抓取訊息文字+圖片+來源連結，輸出CSV+圖片",
        "file": "girl_scraper.py",
    },
    {
        "name": "多帳號輪流私訊",
        "desc": "多帳號自動切換、輪流發送私訊，支援持續模式",
        "file": "multi_account_dm.py",
    },
]


def get_key():
    """讀取單一按鍵（支援方向鍵）"""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            ch2 = sys.stdin.read(1)
            if ch2 == "[":
                ch3 = sys.stdin.read(1)
                if ch3 == "A":
                    return "up"
                elif ch3 == "B":
                    return "down"
        elif ch == "\r" or ch == "\n":
            return "enter"
        elif ch == "q" or ch == "\x03":  # q 或 Ctrl+C
            return "quit"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def draw_menu(selected):
    """繪製選單"""
    os.system("clear")
    print()
    print("  \033[1;36m╔══════════════════════════════════════════════╗\033[0m")
    print("  \033[1;36m║        TG Scraper Toolkit                   ║\033[0m")
    print("  \033[1;36m╚══════════════════════════════════════════════╝\033[0m")
    print()
    print("  \033[90m↑↓ 選擇  Enter 確認  q 離開\033[0m")
    print()

    for i, item in enumerate(SCRIPTS):
        if i == selected:
            print(f"  \033[1;33m▶ [{i+1}] {item['name']}\033[0m")
            print(f"    \033[90m{item['desc']}\033[0m")
        else:
            print(f"    [{i+1}] {item['name']}")
            print(f"    \033[90m{item['desc']}\033[0m")
        print()


def main():
    selected = 0

    while True:
        draw_menu(selected)
        key = get_key()

        if key == "up":
            selected = (selected - 1) % len(SCRIPTS)
        elif key == "down":
            selected = (selected + 1) % len(SCRIPTS)
        elif key == "enter":
            script = SCRIPTS[selected]
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script["file"])

            if not os.path.exists(script_path):
                print(f"\n找不到腳本: {script['file']}")
                input("按 Enter 返回...")
                continue

            os.system("clear")
            print(f"\n  \033[1;32m啟動: {script['name']}\033[0m\n")
            print("─" * 50)
            # 使用虛擬環境的 Python
            venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tg_venv", "bin", "python3")
            if not os.path.exists(venv_python):
                venv_python = sys.executable
            os.execv(venv_python, [venv_python, script_path])
        elif key == "quit":
            os.system("clear")
            print("\n  掰掰～\n")
            break


if __name__ == "__main__":
    main()
