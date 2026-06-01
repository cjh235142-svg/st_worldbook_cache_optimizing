"""
Stress test: auto-generate various world book configurations and run full pipeline.

Generates mixes of normal + edge-case books automatically. Only requires -n.
Reports coverage rates and overall PASS/FAIL after completion.

Usage:
  python tests/stress_test.py -n 100
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import subprocess
import argparse
import time
import tempfile
import random
import json
import collections
from world_book_utils import atdepth_sort_key

SCRIPT_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
TEST_DIR = os.path.join(os.path.dirname(__file__))

GEN = os.path.join(SCRIPT_DIR, "generate_random_world_book.py")
SPLIT = os.path.join(SCRIPT_DIR, "split_world_book_ejs.py")
REORDER = os.path.join(SCRIPT_DIR, "reorder_world_book.py")
SYNC = os.path.join(SCRIPT_DIR, "sync_original_data.py")

T_SPLIT = os.path.join(TEST_DIR, "test_split.py")
T_REORDER = os.path.join(TEST_DIR, "test_reorder.py")
T_SYNC = os.path.join(TEST_DIR, "test_sync.py")

# Config templates for various scenarios
# Each: (weight, dict-of-gen-args)
CONFIGS = [
    # --- Normal scenarios (90% weight combined) ---
    (30, {"--ejs-prob": 0.4, "--bracket-prob": 0.5, "--deep-prob": 0.2}),
    (20, {"--ejs-prob": 0.6, "--bracket-prob": 0.3, "--deep-prob": 0.1}),
    (15, {"--ejs-prob": 0.2, "--bracket-prob": 0.7, "--deep-prob": 0.3}),
    (15, {"--ejs-prob": 0.5, "--bracket-prob": 0.5, "--deep-prob": 0.4}),
    (10, {"--ejs-prob": 0.3, "--bracket-prob": 0.2, "--deep-prob": 0.15}),
    # --- Edge case scenarios (10% weight combined) ---
    ( 3, {"--ejs-prob": 0.5, "--bracket-prob": 0.5, "--deep-prob": 0.3,
          "--bad-ejs-prob": 0.15, "--undefined-prob": 0.1}),
    ( 2, {"--ejs-prob": 0.4, "--bracket-prob": 0.4, "--deep-prob": 0.3,
          "--order-collision-prob": 0.2}),
    ( 2, {"--ejs-prob": 0.4, "--bracket-prob": 0.5, "--deep-prob": 0.2,
          "--unclosed-bracket-prob": 0.15}),
    ( 2, {"--ejs-prob": 0.5, "--bracket-prob": 0.4, "--deep-prob": 0.3,
          "--bad-ejs-prob": 0.1, "--undefined-prob": 0.1,
          "--order-collision-prob": 0.1, "--unclosed-bracket-prob": 0.1}),
    ( 1, {"--ejs-prob": 0.0, "--bracket-prob": 0.0, "--deep-prob": 0.0,
          "--no-original-data": True}),
]

TOTAL_WEIGHT = sum(w for w, _ in CONFIGS)
ENTRIES_RANGE = (20, 60)


def pick_config():
    """Weighted random pick from CONFIGS."""
    r = random.uniform(0, TOTAL_WEIGHT)
    acc = 0
    for w, cfg in CONFIGS:
        acc += w
        if r <= acc:
            return dict(cfg)  # shallow copy
    return dict(CONFIGS[-1][1])


def _cfg_key(cfg: dict) -> str:
    """Short label for a config."""
    parts = []
    if cfg.get("--bad-ejs-prob", 0) > 0: parts.append("badEJS")
    if cfg.get("--undefined-prob", 0) > 0: parts.append("undef")
    if cfg.get("--order-collision-prob", 0) > 0: parts.append("collision")
    if cfg.get("--unclosed-bracket-prob", 0) > 0: parts.append("unclosed")
    if cfg.get("--no-original-data"): parts.append("noOD")
    has_edge = parts
    ejs = cfg.get("--ejs-prob", 0)
    bracket = cfg.get("--bracket-prob", 0)
    deep = cfg.get("--deep-prob", 0)
    parts = [f"ejs_{ejs:.1f}", f"br_{bracket:.1f}", f"dp_{deep:.1f}"] + (has_edge if has_edge else ["normal"])
    return "_".join(parts)


def run_step(cmd, label, timeout=120):
    """Run a subprocess step, return (ok, stderr)."""
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return proc.returncode == 0, proc.stderr


def main():
    parser = argparse.ArgumentParser(description="Stress test World Book pipeline")
    parser.add_argument("-n", "--iterations", type=int, default=100,
                        help="Number of test iterations (default: 100)")
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--log-level", type=str, default="WARNING",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()

    py = args.python
    start = time.time()
    passed = 0
    failed = 0

    # Coverage counters: how many times each config type was tested
    config_hits = collections.Counter()
    # Coverage: which features appeared in generated data
    feature_hits = collections.Counter()
    # Fail details
    fail_details = []

    for i in range(args.iterations):
        seed = args.seed_start + i
        iteration = i + 1

        # Pick random config and entry count
        cfg = pick_config()
        num_entries = random.randint(*ENTRIES_RANGE)
        cfg_key = _cfg_key(cfg)
        config_hits[cfg_key] += 1

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w", encoding="utf-8") as ftmp:
            tmpdir = os.path.dirname(ftmp.name)
            base = os.path.splitext(os.path.basename(ftmp.name))[0]
            input_file = ftmp.name

        split_file = os.path.join(tmpdir, f"{base}_split.json")
        reorder_file = os.path.join(tmpdir, f"{base}_reordered.json")

        ok = True

        # Step 0: Generate
        gen_cmd = [py, GEN, input_file, "-n", str(num_entries), "--seed", str(seed), "--log-level", "WARNING"]
        for k, v in cfg.items():
            if v is True:
                gen_cmd.append(k)
            elif v is not False and v is not None:
                gen_cmd.extend([k, str(v)])
        gen_ok, gen_stderr = run_step(gen_cmd, "generate")
        if not gen_ok:
            failed += 1
            fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=generate")
            ok = False

        # Step 1: Split
        if ok:
            split_ok, _ = run_step([py, SPLIT, input_file, split_file, "--log-level", args.log_level], "split")
            if not split_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=split")
                ok = False
        if ok:
            test_ok, _ = run_step([py, T_SPLIT, split_file], "test_split", timeout=60)
            if not test_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=test_split")
                ok = False

        # Read split output for coverage stats
        if ok:
            try:
                with open(split_file, "r", encoding="utf-8") as f:
                    split_data = json.load(f)
                se = list(split_data["entries"].values())
                ejs_count = sum(1 for e in se if e.get("comment", "").endswith("-EJS"))
                bracket_count = sum(1 for e in se if e.get("comment", "").endswith("开始") or e.get("comment", "").endswith("结束"))
                deep_count = sum(1 for e in se if e.get("position") == 4 and e.get("depth", 0) >= 10)
                has_od = "originalData" in split_data
                # Feature tracking
                if ejs_count > 0: feature_hits["has_ejs"] += 1
                if bracket_count > 0: feature_hits["has_bracket"] += 1
                if deep_count > 0: feature_hits["has_deep"] += 1
                if has_od: feature_hits["has_originalData"] += 1
                # Check for warning conditions
                warnings_brace = sum(1 for line in gen_stderr.split("\n") if "brace" in line.lower() and "warning" in line.lower())
                warnings_ejs = sum(1 for line in gen_stderr.split("\n") if "无有效EJS" in line)
                warnings_bracket = sum(1 for line in gen_stderr.split("\n") if "bracket未配对" in line or "bracket配对" in line)
                if warnings_brace > 0: feature_hits["edge_brace"] += 1
                if warnings_ejs > 0: feature_hits["edge_undefined"] += 1
                if warnings_bracket > 0: feature_hits["edge_bracket"] += 1
            except Exception:
                pass

        # Step 2: Reorder
        if ok:
            reorder_ok, _ = run_step([py, REORDER, split_file, reorder_file, "--log-level", args.log_level], "reorder")
            if not reorder_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=reorder")
                ok = False
        if ok:
            test_ok, _ = run_step([py, T_REORDER, reorder_file, split_file], "test_reorder", timeout=60)
            if not test_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=test_reorder")
                ok = False

        # Read reorder output for coverage
        if ok:
            try:
                with open(reorder_file, "r", encoding="utf-8") as f:
                    reorder_data = json.load(f)
                re = list(reorder_data["entries"].values())
                supp_count = sum(1 for e in re if "补充" in e.get("comment", ""))
                const_count = sum(1 for e in re if e.get("constant"))
                if supp_count > 0: feature_hits["has_supplements"] += 1
                # Verify sort order: (position, -depth, order)
                sort_ok = True
                for j in range(len(re) - 1):
                    a, b = re[j], re[j + 1]
                    ka = atdepth_sort_key(a)
                    kb = atdepth_sort_key(b)
                    if ka > kb:
                        sort_ok = False
                        break
                if sort_ok: feature_hits["sort_correct"] += 1
                else: feature_hits["sort_wrong"] += 1
            except Exception:
                pass

        # Step 3: Sync
        if ok:
            sync_ok, _ = run_step([py, SYNC, reorder_file, "--log-level", args.log_level], "sync")
            if not sync_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=sync")
                ok = False
        if ok:
            test_ok, _ = run_step([py, T_SYNC, reorder_file], "test_sync", timeout=60)
            if not test_ok:
                failed += 1; fail_details.append(f"iter={iteration} seed={seed} cfg={cfg_key} stage=test_sync")
                ok = False

        # Clean up
        for f in [input_file, split_file, reorder_file]:
            try: os.remove(f)
            except OSError: pass

        if ok:
            passed += 1

        elapsed = time.time() - start
        rate = iteration / elapsed if elapsed > 0 else 0
        tag = "PASS" if ok else "FAIL"
        print(f"    [{tag}] iter {iteration}/{args.iterations}  seed={seed}  cfg={cfg_key}  n={num_entries}  ({rate:.1f}/s)", file=sys.stderr)

    elapsed = time.time() - start

    # ---- Final report ----
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  STRESS TEST RESULTS", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    print(f"  Total:  {args.iterations}", file=sys.stderr)
    print(f"  Passed: {passed}", file=sys.stderr)
    print(f"  Failed: {failed}", file=sys.stderr)
    print(f"  Time:   {elapsed:.1f}s  ({elapsed/args.iterations:.2f}s/iter)", file=sys.stderr)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  CONFIG DISTRIBUTION", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    for k, v in config_hits.most_common():
        print(f"  {v:>4} x {k}", file=sys.stderr)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  FEATURE COVERAGE", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)
    feature_labels = {
        "has_ejs": "EJS 条目",
        "has_bracket": "Bracket 标记",
        "has_deep": "depth>=10",
        "has_supplements": "补充条目",
        "has_originalData": "originalData",
        "sort_correct": "排序正确 (position-depth-order)",
        "sort_wrong": "排序错误",
        "edge_brace": "EJS brace 不对称",
        "edge_undefined": "未定义 EJS 行为",
        "edge_bracket": "Bracket 不闭合",
    }
    total = args.iterations
    for fkey, flabel in feature_labels.items():
        count = feature_hits.get(fkey, 0)
        pct = count / total * 100 if total > 0 else 0
        bar = "#" * int(pct / 2) + "-" * (50 - int(pct / 2))
        print(f"  {flabel:<22s} {count:>4}/{total}  {pct:5.1f}%  {bar}", file=sys.stderr)

    if fail_details:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  FAILURE DETAILS (first 20)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        for d in fail_details[:20]:
            print(f"  {d}", file=sys.stderr)
        if len(fail_details) > 20:
            print(f"  ... and {len(fail_details) - 20} more", file=sys.stderr)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  EXIT: {'PASS' if failed == 0 else 'FAIL'}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
