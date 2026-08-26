# ==============================================================================
# plugins/archive_pack.py
# 外掛：打包選取檔案為 JSON (含目錄樹)
# ==============================================================================

import os
import json
from datetime import datetime
from plugins._archive_common import archive_selected_files, generate_tree_string

__plugin_command__ = "A"
__plugin_name__ = "打包為 JSON"
__plugin_description__ = "打包選取檔案為 JSON (含目錄樹)"
__plugin_usage__ = "A  -> 將目前選取的檔案打包成單一 JSON 封存檔"


def run(fm, args):
    if not fm.selected_items:
        print("❌ 未選取")
        input()
        return
    data, count = archive_selected_files(fm.work_path, fm.selected_items, fm.current_work_path_name)
    tree_str = generate_tree_string(fm, fm.selected_items)
    data["__metadata"]["tree_view"] = tree_str
    name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(os.path.join(fm.current_path, name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ 打包成功!\n{tree_str}")
    input("Enter 繼續...")
