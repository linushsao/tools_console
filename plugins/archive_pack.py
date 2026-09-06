# ==============================================================================
# plugins/archive_pack.py
# 外掛：打包選取檔案為 JSON (含目錄樹)
# ==============================================================================

import os
import json
from datetime import datetime
from plugins._archive_common import archive_selected_files, generate_tree_string, detect_flatten_conflicts

__plugin_command__ = "A"
__plugin_name__ = "打包為 JSON"
__plugin_description__ = "打包選取檔案為 JSON (含目錄樹)"
__plugin_usage__ = "A  -> 將目前選取的檔案打包成單一 JSON 封存檔"


def run(fm, args):
    if not fm.selected_items:
        print("❌ 未選取")
        input()
        return

    ans = input("是否採用 MetaAI式扁平化（僅保留「上層資料夾/檔名」，砍掉更上層路徑）？(y/N): ").strip().lower()
    flatten = ans in ('y', 'yes')

    add_suffix = False
    if flatten:
        conflicts = detect_flatten_conflicts(fm.selected_items)
        if conflicts:
            print(f"⚠️ 偵測到 {len(conflicts)} 組扁平化後 key 衝突:")
            for key, paths in conflicts.items():
                print(f"   - {key} <- {', '.join(paths)}")
            c_ans = input("是否自動加上流水號後綴 (_1, _2...) 以避免衝突？(y/N，選 N 將中止打包): ").strip().lower()
            if c_ans in ('y', 'yes'):
                add_suffix = True
            else:
                print("❌ 已中止打包（未加後綴且存在同名 key 衝突）。")
                input("按 Enter 返回...")
                return

    data, count = archive_selected_files(
        fm.work_path, fm.selected_items, fm.current_work_path_name,
        flatten=flatten, flatten_add_suffix=add_suffix
    )

    if flatten:
        tree_str = "📦 " + fm.current_work_path_name + " (MetaAI式扁平化)\n" + \
                   "\n".join(f"├── {k}" for k in sorted(data["files"].keys()))
        renamed = data["__metadata"].get("flatten_renamed")
        if renamed:
            print(f"ℹ️ 已自動改名 {len(renamed)} 個衝突檔案:")
            for r in renamed:
                print(f"   - {r['original']} -> {r['renamed_to']}")
    else:
        tree_str = generate_tree_string(fm, fm.selected_items)

    data["__metadata"]["tree_view"] = tree_str
    name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(os.path.join(fm.current_path, name), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"✅ 打包成功!\n{tree_str}")
    input("Enter 繼續...")
