# ==============================================================================
# plugins/example_hello.py
# 外掛範例模板 - 最小可運行範例
# 指令: HELLO
# 這是一個教學用模板，展示如何撰寫一個符合規範的外掛
# ==============================================================================

import os
from pathlib import Path

# --- 1. 外掛資訊 (必須) ---
__plugin_name__ = "Hello Example"
__plugin_command__ = "HELLO"  # 使用者輸入 HELLO 就會觸發
__plugin_description__ = "範例模板：向選取的檔案打招呼並示範如何與主程式互動"
__plugin_usage__ = "HELLO [名字] | HELLO --list | HELLO --help"

# --- 2. 外掛邏輯 (可自行拆分函式) ---
def list_selected_files(file_manager):
    """示範如何讀取主程式的選取清單"""
    if not file_manager.selected_items:
        print("  (目前沒有選取任何檔案，試試用數字鍵選取幾個檔案再執行 HELLO)")
        return
    print(f"\n  你已選取 {len(file_manager.selected_items)} 個檔案:")
    for i, rel_path in enumerate(sorted(file_manager.selected_items)[:10], 1):
        print(f"    {i}. {rel_path}")
    if len(file_manager.selected_items) > 10:
        print(f"    ... 還有 {len(file_manager.selected_items)-10} 個")

def greet_files(file_manager, name="World"):
    """示範如何遍歷專案檔案"""
    root = Path(file_manager.work_path)
    print(f"\n  Hello, {name}! 來自 {root.name} 專案")
    list_selected_files(file_manager)
    
    # 範例：計算 .py 檔案數量 (記得排除忽略清單)
    count = 0
    for p in root.rglob("*.py"):
        if '.git' in p.parts or '__pycache__' in p.parts or 'venv' in p.parts:
            continue
        count += 1
    print(f"\n  專案內共有 {count} 個 .py 檔案")

# --- 3. 外掛入口 (必須) ---
def run(file_manager, args):
    """
    主程式會呼叫這個函式
    file_manager: 主程式的 FileManager 物件
    args: 使用者額外輸入的參數，例如輸入 HELLO Linus，則 args = ['Linus']
    """
    print(f"\n{'='*20} 🔌 {__plugin_name__} {'='*20}")

    # 參數解析：自己處理，不依賴主程式
    if not args:
        # 沒有參數 -> 互動模式
        name = input("  請輸入你的名字 (直接 Enter 使用 World): ").strip()
        if not name:
            name = "World"
        greet_files(file_manager, name)
    elif args[0] in ('--help', '-h', 'help'):
        print(f"\n  說明: {__plugin_description__}")
        print(f"  用法: {__plugin_usage__}")
        print(f"\n  範例:")
        print(f"    HELLO            -> 互動模式")
        print(f"    HELLO Linus      -> 向 Linus 打招呼")
        print(f"    HELLO --list     -> 只列出已選取檔案")
    elif args[0] == '--list':
        list_selected_files(file_manager)
    else:
        # 有參數，直接當名字
        name = " ".join(args)
        greet_files(file_manager, name)

    # 結束前暫停，讓使用者看得到結果 (重要！)
    input("\n  按 Enter 返回主選單...")

# 讓模板也能獨立測試: python3 plugins/example_hello.py
if __name__ == "__main__":
    class DummyFM:
        work_path = os.getcwd()
        current_path = os.getcwd()
        selected_items = {"example.py", "plugins/py_rename.py"}
    import sys
    run(DummyFM(), sys.argv[1:])
