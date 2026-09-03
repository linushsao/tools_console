# ==============================================================================
# plugins/archive_unpack.py
# 外掛：解包選取的 JSON 檔案並還原至同目錄結構
# ==============================================================================

import os
import re
import json
import base64

__plugin_command__ = "UA"
__plugin_name__ = "解包還原 JSON"
__plugin_description__ = "解包選取的 JSON 檔案並還原至同目錄結構"
__plugin_usage__ = "UA  -> 將選取的封存 JSON 檔案還原為實體檔案結構"


def run(fm, args):
    json_targets = [p for p in fm.selected_items if p.lower().endswith('.json')]
    if not json_targets:
        print("❌ 未選取任何封存 JSON 檔案進行解包。")
        input("按 Enter 繼續...")
        return

    print(f"發現 {len(json_targets)} 個選取的 JSON 封存檔，開始解包還原...")
    for rel_json_path in json_targets:
        full_json_path = os.path.normpath(os.path.join(fm.work_path, rel_json_path))
        if not os.path.isfile(full_json_path):
            print(f"⚠️ 找不到實體檔案: {rel_json_path}")
            continue

        json_dir = os.path.dirname(full_json_path)
        print(f"\n正在解包處理: {rel_json_path} -> 還原至目錄: {json_dir}")

        try:
            with open(full_json_path, 'r', encoding='utf-8') as f:
                archive_data = json.load(f)

            files_dict = archive_data.get("files", archive_data)

            if "__metadata" not in archive_data and "files" not in archive_data:
                print(f"⚠️ 檔案 {rel_json_path} 不包含合法的封存特徵，跳過。")
                continue

            unpack_count = 0
            for file_key, content in files_dict.items():
                if file_key in ("__metadata", "project_name"):
                    continue

                local_rel_path = file_key.replace('/', os.path.sep)

                clean_rel_path = local_rel_path
                sep_str = os.path.sep
                parent_prefix = '..' + sep_str

                while clean_rel_path.startswith(parent_prefix) or clean_rel_path == '..':
                    if clean_rel_path == '..':
                        clean_rel_path = ''
                        break
                    clean_rel_path = clean_rel_path[len(parent_prefix):]

                clean_rel_path = clean_rel_path.lstrip(sep_str)

                full_dest_path = os.path.normpath(os.path.join(json_dir, clean_rel_path))

                dest_dir = os.path.dirname(full_dest_path)
                if dest_dir and not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)

                is_base64 = False
                if isinstance(content, str) and not any(c in content for c in " \t\n\r{},;:\"'()[]<>#-_!@$%^&*=|\\~`"):
                    if len(content) % 4 == 0 and re.match(r'^[A-Za-z0-9+/]*={0,2}$', content):
                        try:
                            decoded_bytes = base64.b64decode(content)
                            ext = os.path.splitext(file_key)[1].lower()
                            if ext in ['.py', '.json', '.lua', '.md', '.txt', '.html', '.css', '.js', '.yaml', '.yml', '.sh', '.conf', '.mod']:
                                is_base64 = False
                            elif ext in ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.zip', '.tar', '.gz', '.7z', '.rar']:
                                is_base64 = True
                            else:
                                if b'\x00' in decoded_bytes or len([b for b in decoded_bytes if b < 32 and b not in (9, 10, 13)]) > len(decoded_bytes) * 0.1:
                                    is_base64 = True
                                else:
                                    is_base64 = False
                        except:
                            is_base64 = False

                if is_base64:
                    with open(full_dest_path, 'wb') as out_f:
                        out_f.write(base64.b64decode(content))
                else:
                    with open(full_dest_path, 'w', encoding='utf-8') as out_f:
                        out_f.write(content)

                print(f"  [DEBUG] 還原檔案: {file_key} -> {full_dest_path}")
                unpack_count += 1

            print(f"✅ 成功還原該包內共 {unpack_count} 個檔案結構。")
        except Exception as e:
            print(f"❌ 解包檔案 {rel_json_path} 失敗: {e}")

    fm.scan_directory()
    input("\n還原完畢，按 Enter 繼續...")
