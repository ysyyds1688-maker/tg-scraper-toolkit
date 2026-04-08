"""
系統設定工具 — 互動式介面
不需要編輯程式碼，全部透過選單操作
"""

import json
import os

TOOLKIT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(TOOLKIT_DIR, "config.py")


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def header():
    clear()
    print("\033[1;36m")
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║           系統設定                            ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print("\033[0m")


def read_config():
    """讀取 config.py 中的設定值"""
    settings = {}
    if not os.path.exists(CONFIG_FILE):
        return settings
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line or line.startswith("import") or line.startswith("from") or line.startswith("def "):
                continue
            if " = " in line:
                key, _, val = line.partition(" = ")
                key = key.strip()
                val = val.split("#")[0].strip()  # 去掉行尾註解
                settings[key] = val
    return settings


def update_config(key, new_value):
    """更新 config.py 中的某個值"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(key + " =") or stripped.startswith(key + "="):
            # 保留原有的註解
            comment = ""
            if "#" in line and not line.strip().startswith("#"):
                parts = line.split("#", 1)
                comment = "  # " + parts[1].strip()

            if isinstance(new_value, str) and not new_value.startswith("[") and not new_value.startswith("os."):
                lines[i] = f'{key} = "{new_value}"{comment}\n'
            else:
                lines[i] = f'{key} = {new_value}{comment}\n'
            updated = True
            break

    if updated:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)

    return updated


def show_current():
    """顯示目前所有設定"""
    header()
    settings = read_config()

    print("  \033[1;33m【API 設定】\033[0m")
    print(f"    API ID:        {settings.get('API_ID', '未設定')}")
    api_hash = settings.get('API_HASH', '未設定').strip('"')
    print(f"    API Hash:      {api_hash[:6]}...{api_hash[-4:] if len(api_hash) > 10 else api_hash}")
    print(f"    手機號碼:      {settings.get('PHONE', '未設定')}")

    print(f"\n  \033[1;33m【導流設定】\033[0m")
    print(f"    群組邀請連結:  {settings.get('GROUP_INVITE_LINK', '未設定')}")

    print(f"\n  \033[1;33m【私訊延遲設定】\033[0m")
    print(f"    每人最短延遲:  {settings.get('DM_MIN_DELAY', '60')} 秒")
    print(f"    每人最長延遲:  {settings.get('DM_MAX_DELAY', '180')} 秒")
    print(f"    打字模擬:      {settings.get('DM_TYPING_DELAY', '3')} 秒")
    print(f"    分段最短間隔:  {settings.get('DM_SPLIT_DELAY_MIN', '5')} 秒")
    print(f"    分段最長間隔:  {settings.get('DM_SPLIT_DELAY_MAX', '15')} 秒")

    print(f"\n  \033[1;33m【發送限制】\033[0m")
    print(f"    每日上限:      {settings.get('DM_DAILY_LIMIT', '30')} 人")

    print()


def edit_setting(label, key, value_type="str"):
    """編輯單一設定"""
    settings = read_config()
    current = settings.get(key, "未設定").strip('"')
    new_val = input(f"  {label} [{current}]: ").strip()

    if not new_val:
        print("  保持不變")
        return

    if value_type == "int":
        if not new_val.isdigit():
            print("  \033[31m請輸入數字\033[0m")
            return
        update_config(key, new_val)
    else:
        update_config(key, new_val)

    print(f"  \033[32m已更新: {key} = {new_val}\033[0m")


def main():
    while True:
        show_current()
        print("  修改設定:\n")
        print("    [1] 修改群組邀請連結")
        print("    [2] 修改私訊延遲參數")
        print("    [3] 修改每日發送上限")
        print("    [4] 修改 API 設定（主帳號）")
        print("    [5] 修改手機號碼（主帳號）")
        print()
        print("    [0] 返回主選單")
        print()

        choice = input("  請選擇 > ").strip()

        if choice == "1":
            edit_setting("群組邀請連結", "GROUP_INVITE_LINK")
            input("  按 Enter 繼續...")

        elif choice == "2":
            print("\n  修改私訊延遲參數:\n")
            edit_setting("每人最短延遲(秒)", "DM_MIN_DELAY", "int")
            edit_setting("每人最長延遲(秒)", "DM_MAX_DELAY", "int")
            edit_setting("打字模擬(秒)", "DM_TYPING_DELAY", "int")
            edit_setting("分段最短間隔(秒)", "DM_SPLIT_DELAY_MIN", "int")
            edit_setting("分段最長間隔(秒)", "DM_SPLIT_DELAY_MAX", "int")
            input("  按 Enter 繼續...")

        elif choice == "3":
            edit_setting("每日發送上限", "DM_DAILY_LIMIT", "int")
            input("  按 Enter 繼續...")

        elif choice == "4":
            print("\n  修改主帳號 API 設定:\n")
            edit_setting("API ID", "API_ID", "int")
            edit_setting("API Hash", "API_HASH")
            input("  按 Enter 繼續...")

        elif choice == "5":
            edit_setting("手機號碼", "PHONE")
            input("  按 Enter 繼續...")

        elif choice == "0":
            break
        else:
            print("  無效選擇")
            input("  按 Enter 繼續...")


if __name__ == "__main__":
    main()
