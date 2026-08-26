# ==============================================================================
# plugins/pattern_search.py
# 外掛：在已選取檔案中搜尋特定內容
# ==============================================================================

import os

__plugin_command__ = "PA"
__plugin_name__ = "內容搜尋"
__plugin_description__ = "在已選取檔案中搜尋特定內容"
__plugin_usage__ = "PA <pattern>  -> 在目前選取的檔案中搜尋關鍵字"


def run(fm, args):
    if not args:
        print("❌ 請輸入要搜尋的 Pattern")
        input()
        return
    if not fm.selected_items:
        print("❌ 未選取任何檔案")
        input()
        return

    pattern = " ".join(args)
    found_list = []
    print(f"正在搜尋關鍵字: '{pattern}' ...")

    for rel in sorted(list(fm.selected_items)):
        full_path = os.path.join(fm.work_path, rel)
        if not os.path.isfile(full_path): continue
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                if pattern in content:
                    found_list.append(rel)
        except Exception:
            pass

    if found_list:
        print(f"\n{'='*10} 符合條件的檔案 ({len(found_list)}) {'='*10}")
        for p in found_list: print(f" [MATCH] {p}")
    else:
        print(f"❌ 未在選取的檔案中找到關鍵字: '{pattern}'")
    input("\n按 Enter 繼續...")
