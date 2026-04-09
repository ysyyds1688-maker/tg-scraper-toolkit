"""
互動式選單 UI — 上下鍵選擇 + Enter 確認
跨平台（Mac / Windows / Linux）
"""

import os
import sys


def _get_key():
    """讀取一個按鍵（跨平台）"""
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getch()
        if key in (b"\x00", b"\xe0"):
            key2 = msvcrt.getch()
            if key2 == b"H":
                return "up"
            elif key2 == b"P":
                return "down"
        elif key == b"\r":
            return "enter"
        elif key == b" ":
            return "space"
        elif key == b"a":
            return "all"
        elif key == b"g":
            return "groups"
        elif key == b"c":
            return "channels"
        return None
    else:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                if ch2 == "[":
                    if ch3 == "A":
                        return "up"
                    elif ch3 == "B":
                        return "down"
            elif ch in ("\r", "\n"):
                return "enter"
            elif ch == " ":
                return "space"
            elif ch == "a":
                return "all"
            elif ch == "g":
                return "groups"
            elif ch == "c":
                return "channels"
            elif ch == "q":
                return "quit"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        return None


def select_menu(title, options, descriptions=None):
    """
    互動式選單
    title: 標題
    options: ["選項1", "選項2", ...]
    descriptions: ["說明1", "說明2", ...] (選填)
    回傳: 選中的 index (0-based), 或 -1 表示離開
    """
    selected = 0
    total = len(options)

    while True:
        # 清屏
        os.system("cls" if os.name == "nt" else "clear")

        # 標題
        print(f"\033[1;36m")
        print(f"  ╔═══════════════════════════════════════════════╗")
        print(f"  ║  {title:<45s} ║")
        print(f"  ╚═══════════════════════════════════════════════╝")
        print(f"\033[0m")
        print(f"  \033[90m上下鍵選擇，Enter 確認\033[0m\n")

        # 選項
        for i, opt in enumerate(options):
            if i == selected:
                print(f"  \033[1;32m ❯ {opt}\033[0m")
                if descriptions and i < len(descriptions) and descriptions[i]:
                    print(f"    \033[90m{descriptions[i]}\033[0m")
            else:
                print(f"    {opt}")

        # 讀取按鍵
        key = _get_key()
        if key == "up":
            selected = (selected - 1) % total
        elif key == "down":
            selected = (selected + 1) % total
        elif key == "enter":
            return selected
        elif key == "quit":
            return -1


def select_multi(title, options):
    """
    多選選單 — 空白鍵勾選/取消，a 全選/全取消，Enter 確認
    回傳: 選中的 index 列表，或 [] 表示取消
    """
    selected = 0
    total = len(options)
    checked = set()

    while True:
        os.system("cls" if os.name == "nt" else "clear")

        print(f"\033[1;36m")
        print(f"  ╔═══════════════════════════════════════════════╗")
        print(f"  ║  {title:<45s} ║")
        print(f"  ╚═══════════════════════════════════════════════╝")
        print(f"\033[0m")
        print(f"  \033[90m上下鍵移動，空白鍵勾選，Enter 確認\033[0m")
        print(f"  \033[90ma 全選  g 勾選群組  c 勾選頻道  q 離開\033[0m")
        print(f"  \033[90m已選 {len(checked)} 個\033[0m\n")

        for i, opt in enumerate(options):
            check = "\033[32m[v]\033[0m" if i in checked else "[ ]"
            if i == selected:
                print(f"  \033[1;33m ❯ {check} {opt}\033[0m")
            else:
                print(f"    {check} {opt}")

        key = _get_key()
        if key == "up":
            selected = (selected - 1) % total
        elif key == "down":
            selected = (selected + 1) % total
        elif key == "space":
            if selected in checked:
                checked.discard(selected)
            else:
                checked.add(selected)
        elif key == "all":
            if len(checked) == total:
                checked.clear()
            else:
                checked = set(range(total))
        elif key == "groups":
            # 勾選所有群組（👥）
            group_ids = {i for i, o in enumerate(options) if "👥" in o}
            if group_ids.issubset(checked):
                checked -= group_ids
            else:
                checked |= group_ids
        elif key == "channels":
            # 勾選所有頻道（📢）
            ch_ids = {i for i, o in enumerate(options) if "📢" in o}
            if ch_ids.issubset(checked):
                checked -= ch_ids
            else:
                checked |= ch_ids
        elif key == "enter":
            return sorted(checked)
        elif key == "quit":
            return []


def select_menu_grouped(title, groups):
    """
    分組選單
    title: 標題
    groups: [
        {"label": "分組名", "items": [
            {"name": "選項名", "desc": "說明"},
            ...
        ]},
        ...
    ]
    回傳: 選中的全局 index (0-based), 或 -1 表示離開
    """
    # 展平所有選項
    flat_items = []
    group_headers = {}  # index -> group label

    for g in groups:
        group_headers[len(flat_items)] = g["label"]
        for item in g["items"]:
            flat_items.append(item)

    selected = 0
    total = len(flat_items)

    while True:
        os.system("cls" if os.name == "nt" else "clear")

        print(f"\033[1;36m")
        print(f"  ╔═══════════════════════════════════════════════╗")
        print(f"  ║  {title:<45s} ║")
        print(f"  ╚═══════════════════════════════════════════════╝")
        print(f"\033[0m")
        print(f"  \033[90m上下鍵選擇，Enter 確認，q 離開\033[0m\n")

        idx = 0
        for g in groups:
            print(f"  \033[1;33m【{g['label']}】\033[0m")
            for item in g["items"]:
                if idx == selected:
                    print(f"  \033[1;32m ❯ {item['name']}\033[0m")
                    if item.get("desc"):
                        print(f"    \033[90m{item['desc']}\033[0m")
                else:
                    print(f"    {item['name']}")
                idx += 1
            print()

        key = _get_key()
        if key == "up":
            selected = (selected - 1) % total
        elif key == "down":
            selected = (selected + 1) % total
        elif key == "enter":
            return selected
        elif key == "quit":
            return -1
