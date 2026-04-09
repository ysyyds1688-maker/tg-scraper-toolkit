"""
Bot 客服管理工具 — 互動式介面
不需要編輯任何檔案，全部透過選單操作
"""

import json
import os

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
AGENTS_FILE = os.path.join(TOOLKIT_DIR, "agents.json")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def load_agents():
    if not os.path.exists(AGENTS_FILE):
        return []
    with open(AGENTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_agents(agents):
    with open(AGENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(agents, f, ensure_ascii=False, indent=2)


def header():
    clear()
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║         Bot 客服管理                          ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")


def show_agents():
    agents = load_agents()
    if not agents:
        print("  目前沒有客服\n")
        return

    print(f"  共 {len(agents)} 個客服:\n")
    print(f"  {'#':<4} {'來源名稱':<15} {'客服帳號':<25} {'按鈕顯示'}")
    print(f"  {'─'*65}")
    for i, a in enumerate(agents, 1):
        btn = f"[Tea] {a['source_name']}-茶莊客服"
        print(f"  {i:<4} {a['source_name']:<15} @{a['username']:<24} {btn}")
    print()


def add_agent():
    header()
    print("  ── 新增客服 ──\n")

    source_name = input("  來源名稱（如 大神、極樂）: ").strip()
    if not source_name:
        print("  已取消")
        return

    username = input("  客服 TG 帳號（如 daishen_service）: ").strip().lstrip("@")
    if not username:
        print("  已取消")
        return

    print(f"\n  確認:")
    print(f"    來源:   {source_name}")
    print(f"    客服:   @{username}")
    print(f"    按鈕:   [Tea] {source_name}-茶莊客服")

    confirm = input(f"\n  確認新增？(y/n): ").strip().lower()
    if confirm != "y":
        print("  已取消")
        return

    agents = load_agents()
    agents.append({"source_name": source_name, "username": username})
    save_agents(agents)
    print(f"\n  \033[32m已新增: {source_name} -> @{username}\033[0m")


def remove_agent():
    from menu_ui import select_menu
    agents = load_agents()
    if not agents:
        print("  目前沒有客服\n")
        return

    options = [f"{a['source_name']} (@{a['username']})" for a in agents] + ["取消"]
    idx = select_menu("選擇要刪除的客服", options)

    if idx == -1 or idx == len(agents):
        return

    a = agents[idx]
    confirm = input(f"  確認刪除 {a['source_name']} (@{a['username']})？(y/n): ").strip().lower()
    if confirm != "y":
        return

    agents.pop(idx)
    save_agents(agents)
    print(f"\n  \033[32m已刪除\033[0m")


def main():
    from menu_ui import select_menu

    OPTIONS = ["新增客服", "刪除客服", "返回主選單"]

    while True:
        idx = select_menu("Bot 客服管理", OPTIONS)
        if idx == -1 or idx == 2:
            break
        elif idx == 0:
            add_agent()
            input("  按 Enter 繼續...")
        elif idx == 1:
            remove_agent()
            input("  按 Enter 繼續...")


if __name__ == "__main__":
    main()
