# ==============================================================================
# plugins/_archive_common.py
# A / ZIP / UA 外掛共用輔助函式（檔名以 _ 開頭，外掛掃描器會略過此檔）
# ==============================================================================

import os
import base64
from datetime import datetime


def archive_selected_files(work_path, selected_items, project_name="Default"):
    files_data = {}
    file_count = 0
    for rel_path in sorted(list(selected_items)):
        full_path = os.path.normpath(os.path.join(work_path, rel_path))
        if not os.path.isfile(full_path): continue
        json_key = rel_path.replace(os.path.sep, '/')
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                files_data[json_key] = f.read()
        except:
            with open(full_path, 'rb') as f:
                files_data[json_key] = base64.b64encode(f.read()).decode('utf-8')
        file_count += 1

    archive_data = {
        "project_name": project_name,
        "files": files_data,
        "__metadata": {
            "original_root_name": os.path.basename(work_path),
            "archive_timestamp": datetime.now().isoformat(),
            "file_count": file_count
        }
    }
    return archive_data, file_count


def generate_tree_string(fm, selected_items):
    tree = {}
    for path in sorted(selected_items):
        parts = path.replace(os.path.sep, '/').split('/')
        curr = tree
        for p in parts: curr = curr.setdefault(p, {})
    lines = [f"📦 {fm.current_work_path_name}"]
    def build(node, prefix=""):
        items = sorted(node.keys())
        for i, name in enumerate(items):
            is_l = (i == len(items)-1); conn = "└── " if is_l else "├── "
            lines.append(f"{prefix}{conn}{name}")
            if node[name]: build(node[name], prefix + ("    " if is_l else "│   "))
    build(tree); return "\n".join(lines)
