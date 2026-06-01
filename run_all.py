"""
Orchestration script: run Script 1 -> 2 -> 3, then all tests.
Backs up original file before optimization.
"""

import sys
import os
import shutil
import subprocess
import argparse
from datetime import datetime

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
TESTS_DIR = os.path.join(os.path.dirname(__file__), "tests")


def run_step(python_exe, script_path, args_list, label, log_level="INFO"):
    base_cmd = [python_exe, script_path] + args_list
    # Check if script already has --log-level in args
    if not any("--log-level" in a for a in args_list):
        base_cmd += ["--log-level", log_level]
    cmd = base_cmd
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n>>> FAIL: {label} (exit code {result.returncode})")
        sys.exit(1)


def run_test(python_exe, test_path, args_list, label):
    cmd = [python_exe, test_path] + args_list
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  {' '.join(cmd)}")
    print(f"{'='*60}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n>>> FAIL: {label} (exit code {result.returncode})")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="World Book optimization pipeline")
    parser.add_argument("input", help="Input JSON file path")
    parser.add_argument("--keep-intermediate", action="store_true",
                        help="Keep intermediate output files")
    parser.add_argument("--skip-tests", action="store_true",
                        help="Skip all tests")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip backing up the original file")
    parser.add_argument("--strip-original-data", action="store_true",
                        help="Strip originalData from output (for standalone world book import)")
    parser.add_argument("--python", default=sys.executable,
                        help="Python executable (default: current)")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG","INFO","WARNING","ERROR"],
                        help="Log level for subprocesses (default: INFO)")
    args = parser.parse_args()

    python_exe = args.python
    base = os.path.splitext(args.input)[0]
    internal_dir = os.path.join(os.path.dirname(args.input), "_internal")

    split_output = os.path.join(internal_dir, os.path.basename(base) + "_split.json")
    reorder_output = os.path.join(internal_dir, os.path.basename(base) + "_reordered.json")
    synced_output = args.input  # Script 3 overwrites in-place? Actually it uses its arg.

    # Create _internal directory
    os.makedirs(internal_dir, exist_ok=True)

    # === Backup: save original to _internal ===
    if not args.no_backup:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = os.path.basename(base) + f"_backup_{ts}.json"
        backup_path = os.path.join(internal_dir, backup_name)
        shutil.copy2(args.input, backup_path)
        print(f"\n[INFO] 原始文件已备份: {backup_path}")
    else:
        print(f"\n[INFO] 跳过备份 (--no-backup)")

    log_level = args.log_level

    # === Step 1: Split ===
    run_step(python_exe,
             os.path.join(SCRIPTS_DIR, "split_world_book_ejs.py"),
             [args.input, split_output],
             "Script 1: Split EJS entries", log_level)

    if not args.skip_tests:
        run_test(python_exe,
                 os.path.join(TESTS_DIR, "test_split.py"),
                 [split_output],
                 "Test 1: Validate split output")

    # === Step 2: Reorder ===
    run_step(python_exe,
             os.path.join(SCRIPTS_DIR, "reorder_world_book.py"),
             [split_output, reorder_output],
             "Script 2: Reorder & optimize", log_level)

    if not args.skip_tests:
        run_test(python_exe,
                 os.path.join(TESTS_DIR, "test_reorder.py"),
                 [reorder_output, split_output],
                 "Test 2&3: Validate reorder output")

    # === Step 3: Sync originalData (overwrites reorder_output) ===
    run_step(python_exe,
             os.path.join(SCRIPTS_DIR, "sync_original_data.py"),
             [reorder_output],
             "Script 3: Sync originalData", log_level)

    # Strip originalData if requested
    if args.strip_original_data:
        import json
        with open(reorder_output, "r", encoding="utf-8") as f:
            stripped_data = json.load(f)
        if "originalData" in stripped_data:
            del stripped_data["originalData"]
            print("[INFO] 已从输出中移除 originalData")
        with open(reorder_output, "w", encoding="utf-8") as f:
            json.dump(stripped_data, f, ensure_ascii=False, indent=2)

    # Copy result back to original location
    shutil.copy2(reorder_output, args.input)
    print(f"\n[INFO] 结果已覆盖写入: {args.input}")

    if not args.skip_tests:
        run_test(python_exe,
                 os.path.join(TESTS_DIR, "test_sync.py"),
                 [args.input],
                 "Test 4: Validate synced output")

    # Cleanup
    if not args.keep_intermediate:
        for f in [split_output, reorder_output]:
            if os.path.exists(f):
                os.remove(f)
        try:
            os.rmdir(internal_dir)
        except OSError:
            pass
        print("[INFO] 中间产物已清理")
    else:
        print(f"[INFO] 中间产物保留在: {internal_dir}")

    print("\n=== ALL DONE ===")


if __name__ == "__main__":
    main()
