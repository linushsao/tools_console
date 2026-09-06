# ==============================================================================
# plugins/_archive_common.py
# A / ZIP / UA 外掛共用輔助函式（檔名以 _ 開頭，外掛掃描器會略過此檔）
# ==============================================================================

import os
import base64
from datetime import datetime


def _metaai_flatten_key(rel_path):
    """MetaAI 式扁平化：僅保留「直接上層資料夾/檔名」，砍掉更上層路徑；無上層資料夾則僅保留檔名"""
    p = rel_path.replace(os.path.sep, '/')
    parts = [seg for seg in p.split('/') if seg]
    if len(parts) >= 2:
        return '/'.join(parts[-2:])
    return parts[-1]


def detect_flatten_conflicts(selected_items):
    """預先偵測 MetaAI 式扁平化後會產生衝突的 key，回傳 {扁平化後key: [原始相對路徑,...]}（僅含有衝突者）"""
    groups = {}
    for rel_path in selected_items:
        key = _metaai_flatten_key(rel_path)
        groups.setdefault(key, []).append(rel_path.replace(os.path.sep, '/'))
    return {k: v for k, v in groups.items() if len(v) > 1}


def archive_selected_files(work_path, selected_items, project_name="Default", flatten=False, flatten_add_suffix=False):
    files_data = {}
    renamed = []  # 記錄自動加流水號後綴的對照
    file_count = 0
    for rel_path in sorted(list(selected_items)):
        full_path = os.path.normpath(os.path.join(work_path, rel_path))
        if not os.path.isfile(full_path): continue

        if flatten:
            json_key = _metaai_flatten_key(rel_path)
            if json_key in files_data:
                if not flatten_add_suffix:
                    continue  # 未選擇加後綴時，略過後續同名 key（保留第一個）
                name_part, ext_part = os.path.splitext(json_key)
                seq = 1
                while json_key in files_data:
                    json_key = f"{name_part}_{seq}{ext_part}"
                    seq += 1
                renamed.append({"original": rel_path.replace(os.path.sep, '/'), "renamed_to": json_key})
        else:
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
            "file_count": file_count,
            "path_flattened": False,
            "flatten_renamed": renamed
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
