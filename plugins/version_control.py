# ==============================================================================
# plugins/version_control.py
# 外掛：更新版本標籤（VC）
# ==============================================================================

import os
import re
from datetime import datetime

__plugin_command__ = "VC"
__plugin_name__ = "版本標籤更新"
__plugin_description__ = "為選取檔案更新版本標籤 (Version Header)"
__plugin_usage__ = "VC  -> 為目前選取的檔案套用新版本號與日誌"

MAX_HEADER_LINES = 15


class VersionParser:
    VERSION_PATTERN = r'(V\d+\.\d+-\d{3})'
    VERSION_REGEX = re.compile(r'#\s*Version:\s*(' + VERSION_PATTERN + r'(.*?))\s*(\((.*?)\))?$')

    def __init__(self, file_path):
        self.file_path = file_path
        self.relative_path = ""
        self.version_full = None
        self.error = None

    def analyze(self, root_dir):
        self.relative_path = os.path.relpath(self.file_path, root_dir)
        try:
            if not os.path.isfile(self.file_path): return
            with open(self.file_path, 'r', encoding='utf-8') as f:
                lines = [f.readline() for _ in range(MAX_HEADER_LINES)]
            for line in lines:
                if not line: break
                mv = self.VERSION_REGEX.search(line)
                if mv:
                    self.version_full = mv.group(1)
                    return
            self.error = "找不到標籤"
        except Exception as e:
            self.error = str(e)

    def generate_new_header(self, new_v, new_log):
        new_date = datetime.now().strftime('%Y-%m-%d')
        return [f"# Version: {new_v}\n", f"# 更新日期: {new_date}\n", f"# {new_v}: {new_log}\n"]


def run(fm, args):
    parsers = []
    for rel in fm.selected_items:
        p = VersionParser(os.path.join(fm.work_path, rel))
        p.analyze(fm.work_path)
        parsers.append(p)
    for p in parsers:
        print(f" - {p.relative_path}: {p.version_full or p.error}")
    v = input("新版本號: ")
    log = input("日誌: ")
    if v:
        for p in parsers:
            if p.error and p.error != "找不到標籤": continue
            new_h = p.generate_new_header(v, log)
            with open(p.file_path, 'r', encoding='utf-8') as f: content = f.readlines()
            with open(p.file_path, 'w', encoding='utf-8') as f: f.writelines(new_h + content)
        input("✅ 版本更新完成")
