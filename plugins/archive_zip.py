# ==============================================================================
# plugins/archive_zip.py
# 外掛：壓縮選取檔案為 ZIP 壓縮檔
# ==============================================================================

import os
import zipfile
from datetime import datetime
from plugins._archive_common import generate_tree_string

__plugin_command__ = "ZIP"
__plugin_name__ = "壓縮為 ZIP"
__plugin_description__ = "壓縮選取檔案為 ZIP 壓縮檔"
__plugin_usage__ = "ZIP  -> 將目前選取的檔案/資料夾壓縮成 ZIP"


def run(fm, args):
    if not fm.selected_items:
        print("❌ 未選取任何檔案，無法進行壓縮")
        input()
        return

    zip_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = os.path.join(fm.current_path, zip_name)

    print(f"📦 開始將選取的 {len(fm.selected_items)} 個項目打包為 ZIP...")
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for rel_path in fm.selected_items:
                full_path = os.path.normpath(os.path.join(fm.work_path, rel_path))
                if os.path.isfile(full_path):
                    zipf.write(full_path, rel_path)
                    print(f"  ➕ 已加入檔案: {rel_path}")
                elif os.path.isdir(full_path):
                    print(f"  📂 正在打包資料夾: {rel_path}")
                    for root, dirs, files in os.walk(full_path):
                        for file in files:
                            f_full = os.path.join(root, file)
                            f_rel = os.path.relpath(f_full, fm.work_path)
                            zipf.write(f_full, f_rel)

        tree_str = generate_tree_string(fm, fm.selected_items)
        print(f"\n✅ ZIP 壓縮成功!\n產出檔案: {zip_name}\n\n【包含結構】\n{tree_str}")
    except Exception as e:
        print(f"❌ ZIP 壓縮失敗: {str(e)}")
    input("按 Enter 繼續...")
