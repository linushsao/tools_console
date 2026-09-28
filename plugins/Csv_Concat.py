# ==============================================================================
# plugins/csv_concat.py
# 外掛：文字檔接合 (CSV/文字檔)
# Version: V1.0-001
# 更新日期: 2026-09-29
# 描述: 接合多個文字檔/CSV，檢查欄位數、支援排序、選擇性刪除表頭
# ==============================================================================
import os
import csv
import re
from datetime import datetime
from pathlib import Path

__plugin_command__ = "CONCAT"
__plugin_aliases__ = ["TC", "CSVJOIN"]
__plugin_name__ = "文字檔接合"
__plugin_description__ = "接合多個CSV/文字檔，檢查欄位數一致性並支援排序"
__plugin_usage__ = "CONCAT -> 啟動文字檔接合精靈 (需先選取2個以上檔案)"

# 支援的編碼嘗試順序 (台灣環境常見)
ENCODINGS_TO_TRY = ['utf-8-sig', 'utf-8', 'cp950', 'big5', 'ms950', 'gbk', 'iso-8859-1']
COMMON_DELIMITERS = [',', '\t', ';', '|']

def detect_encoding_and_delimiter(file_path):
    """偵測檔案編碼與分隔符，回傳 (encoding, delimiter, col_count, sample_lines, error)"""
    content_lines = None
    used_encoding = None
    for enc in ENCODINGS_TO_TRY:
        try:
            with open(file_path, 'r', encoding=enc, errors='strict') as f:
                # 只讀前5行非空行來判斷
                lines = []
                for _ in range(10):
                    line = f.readline()
                    if not line:
                        break
                    if line.strip():
                        lines.append(line)
                    if len(lines) >= 5:
                        break
                if not lines:
                    return enc, ',', 0, [], None
                content_lines = lines
                used_encoding = enc
                break
        except Exception:
            continue
    
    if content_lines is None:
        return None, None, 0, [], f"無法解碼 (嘗試 {ENCODINGS_TO_TRY})"

    # 偵測 delimiter：用 csv.Sniffer 為主，失敗則用計數
    delimiter = ','
    try:
        sample = ''.join(content_lines[:3])
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample, delimiters=',\t;|')
        delimiter = dialect.delimiter
    except Exception:
        # 備援：計算哪個分隔符號最穩定
        best_score = -1
        for d in COMMON_DELIMITERS:
            counts = [line.count(d) for line in content_lines]
            if len(counts) > 1 and len(set(counts)) == 1 and counts[0] > 0:
                # 所有行數量一致，優先
                if counts[0] > best_score:
                    best_score = counts[0]
                    delimiter = d
            elif max(counts) > best_score and max(counts) > 0:
                # 取最大者
                best_score = max(counts)
                delimiter = d

    # 計算 col 數 - 以第一行非空行為準
    first_line = content_lines[0].strip()
    # 使用 csv 解析更準確處理引號
    try:
        reader = csv.reader([first_line], delimiter=delimiter)
        cols = next(reader)
        col_count = len(cols)
    except Exception:
        col_count = len(first_line.split(delimiter))

    return used_encoding, delimiter, col_count, content_lines, None


def read_file_info_list(work_path, rel_paths):
    """回傳 [{rel, full, encoding, delimiter, col_count, error}]"""
    infos = []
    for rel in rel_paths:
        full = os.path.normpath(os.path.join(work_path, rel))
        if not os.path.isfile(full):
            infos.append({"rel": rel, "full": full, "col_count": 0, "error": "不是檔案或不存在"})
            continue
        enc, delim, col_cnt, samples, err = detect_encoding_and_delimiter(full)
        infos.append({
            "rel": rel,
            "full": full,
            "encoding": enc,
            "delimiter": delim,
            "col_count": col_cnt,
            "samples": samples,
            "error": err
        })
    return infos


def print_file_table(infos):
    print(f"\n{'='*10} 已選檔案資訊 ({len(infos)} 個) {'='*10}")
    for i, info in enumerate(infos, 1):
        if info.get("error"):
            print(f" [{i}] {info['rel']} -> ❌ {info['error']}")
        else:
            print(f" [{i}] {info['rel']}")
            print(f"     編碼:{info['encoding']}  分隔:'{info['delimiter']}'  欄位數:{info['col_count']}")


def interactive_order(infos):
    """讓使用者排序，支援 u/d/sw 指令"""
    ordered = infos[:]  # copy
    while True:
        print(f"\n{'-'*10} 目前接合順序 (共{len(ordered)}檔) {'-'*10}")
        for idx, info in enumerate(ordered, 1):
            print(f"  [{idx}] {info['rel']} ({info['col_count']} cols)")
        print("\n指令: u <編號> 上移 | d <編號> 下移 | sw <a> <b> 交換 | ok 確認 | q 離開")
        cmd = input("排序指令> ").strip().lower()
        if not cmd:
            continue
        if cmd in ('ok', 'o', 'yes', 'y', ''):
            return ordered
        if cmd in ('q', 'quit', 'exit', 'n'):
            return None
        parts = cmd.split()
        try:
            if parts[0] == 'u' and len(parts) >= 2:
                n = int(parts[1])
                if 2 <= n <= len(ordered):
                    item = ordered.pop(n-1)
                    ordered.insert(n-2, item)
                else:
                    print("⚠️ 編號超出範圍或已在最上")
            elif parts[0] == 'd' and len(parts) >= 2:
                n = int(parts[1])
                if 1 <= n < len(ordered):
                    item = ordered.pop(n-1)
                    ordered.insert(n, item)
                else:
                    print("⚠️ 編號超出範圍或已在最下")
            elif parts[0] == 'sw' and len(parts) >= 3:
                a = int(parts[1]); b = int(parts[2])
                if 1 <= a <= len(ordered) and 1 <= b <= len(ordered):
                    ordered[a-1], ordered[b-1] = ordered[b-1], ordered[a-1]
                else:
                    print("⚠️ 編號超出範圍")
            elif cmd.isdigit():
                # 直接輸入兩個數字交換的簡寫 e.g. "1 3"
                print("提示: 交換請用 sw 1 3，上移用 u 2")
            else:
                print("❓ 不支援指令")
        except ValueError:
            print("❓ 參數必須是數字")
        except Exception as e:
            print(f"錯誤: {e}")


def do_concat(ordered_infos, target_path, skip_header_from_second):
    """執行接合"""
    total_lines = 0
    total_written = 0
    try:
        with open(target_path, 'w', encoding='utf-8-sig', newline='') as out_f:
            for idx, info in enumerate(ordered_infos):
                enc = info['encoding'] or 'utf-8'
                skip_first = (idx > 0 and skip_header_from_second)
                line_no = 0
                file_written = 0
                try:
                    with open(info['full'], 'r', encoding=enc, errors='ignore') as in_f:
                        for line in in_f:
                            line_no += 1
                            if line_no == 1 and skip_first:
                                continue
                            out_f.write(line)
                            file_written += 1
                            total_written += 1
                        total_lines += line_no
                except Exception as e:
                    print(f"⚠️ 讀取 {info['rel']} 失敗: {e}")
                    continue
                print(f"  -> {info['rel']}: 讀取 {line_no} 行, 寫入 {file_written} 行")
        return True, total_lines, total_written
    except Exception as e:
        return False, 0, str(e)


def run(fm, args):
    print(f"\n{'='*20} 🔌 {__plugin_name__} {'='*20}")
    print(f"目前位置: {fm.current_path}")
    print(f"工作根目錄: {fm.work_path}")

    # 1. 取得選取檔案
    selected = sorted(list(fm.selected_items)) if fm.selected_items else []

    if len(selected) < 2:
        print("\n⚠️ 需至少選擇2個文字檔才可接合。")
        print(f"目前已選: {len(selected)} 個")
        # 嘗試列出目前目錄下的文字檔供快速選取
        try:
            all_files = []
            for entry in os.listdir(fm.current_path):
                fp = os.path.join(fm.current_path, entry)
                if os.path.isfile(fp) and (entry.lower().endswith('.csv') or entry.lower().endswith('.txt') or entry.lower().endswith('.tsv')):
                    rel = os.path.relpath(fp, fm.work_path)
                    all_files.append(rel)
            if all_files:
                print("\n目前目錄下的文字檔:")
                for i, f in enumerate(all_files[:20], 1):
                    print(f"  [{i}] {f}")
                ans = input("\n是否要輸入編號多選? (e.g. 1,2,3) 或直接按 Enter 取消: ").strip()
                if ans:
                    try:
                        # 解析 1,2,3 或 1-3
                        chosen = set()
                        for part in re.split(r'[,\s]+', ans):
                            if '-' in part:
                                s, e = part.split('-')
                                for n in range(int(s), int(e)+1):
                                    if 1 <= n <= len(all_files):
                                        chosen.add(all_files[n-1])
                            else:
                                n = int(part)
                                if 1 <= n <= len(all_files):
                                    chosen.add(all_files[n-1])
                        selected = sorted(list(chosen))
                    except Exception as e:
                        print(f"解析失敗: {e}")
        except Exception:
            pass

    if len(selected) < 2:
        print("❌ 已取消：未選取足夠檔案")
        input("按 Enter 返回...")
        return

    # 2. 檢查欄位數
    print(f"\n正在檢查 {len(selected)} 個檔案的欄位數...")
    infos = read_file_info_list(fm.work_path, selected)
    print_file_table(infos)

    # 檢查是否有錯誤
    has_error = any(i.get("error") for i in infos)
    if has_error:
        print("\n❌ 有檔案無法讀取，請檢查後再試")
        input("按 Enter 返回...")
        return

    col_counts = set(i['col_count'] for i in infos)
    if len(col_counts) > 1:
        print("\n❌ 欄位數不一致，停止執行！")
        print("各檔案欄位數明細:")
        for i in infos:
            print(f"  - {i['rel']}: {i['col_count']} 欄 (分隔符='{i['delimiter']}')")
        input("\n按 Enter 返回...")
        return

    print(f"\n✅ 欄位數檢查通過：全部為 {list(col_counts)[0]} 欄")

    # 3. 排序
    print("\n--- 步驟 2: 檔案先後順序排列 ---")
    ordered = interactive_order(infos)
    if ordered is None:
        print("❌ 已取消排序")
        input("按 Enter 返回...")
        return

    # 4. 詢問是否刪除表頭
    print(f"\n--- 步驟 3: 表頭處理 ---")
    print("接合時，是否從第二個檔案開始刪除第一行(通常是表頭)？")
    ans = input("從第二個檔案開始刪除第一行？ (Y/n, 預設Y): ").strip().lower()
    skip_header = True if ans in ('', 'y', 'yes', '是') else False
    print(f"設定: {'是，從第2檔起刪除首行' if skip_header else '否，全部保留'}")

    # 5. 目標檔名
    print(f"\n--- 步驟 4: 執行接合 ---")
    default_name = f"concat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    # 如果第一個檔案是 .txt 則預設 .txt
    if ordered[0]['rel'].lower().endswith('.txt'):
        default_name = default_name.replace('.csv', '.txt')

    target_input = input(f"請輸入目標檔名 (預設 {default_name}，儲存在目前位置): ").strip()
    if not target_input:
        target_input = default_name
    
    # 確保檔名合法，不允許路徑跳脫，強制存在目前位置
    target_filename = os.path.basename(target_input)
    target_path = os.path.join(fm.current_path, target_filename)

    if os.path.exists(target_path):
        ow = input(f"⚠️ 檔案 {target_filename} 已存在，是否覆蓋？ (y/N): ").strip().lower()
        if ow not in ('y', 'yes'):
            print("❌ 已取消")
            input("按 Enter 返回...")
            return

    print(f"\n正在接合到 {target_path} ...")
    print(f"來源順序:")
    for i, inf in enumerate(ordered, 1):
        print(f"  {i}. {inf['rel']}")

    success, total_read, total_written_or_err = do_concat(ordered, target_path, skip_header)

    if success:
        size_kb = os.path.getsize(target_path) / 1024
        print(f"\n✅ 接合完成！")
        print(f"  輸出檔案: {target_path}")
        print(f"  總讀取行數: {total_read}")
        print(f"  總寫入行數: {total_written_or_err}")
        print(f"  檔案大小: {size_kb:.1f} KB")
        try:
            fm.scan_directory()
        except Exception:
            pass
    else:
        print(f"\n❌ 接合失敗: {total_written_or_err}")

    input("\n按 Enter 返回...")
