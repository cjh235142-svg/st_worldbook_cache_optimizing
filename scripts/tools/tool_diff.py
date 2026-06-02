import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static


def run(
    original_path: str,
    optimized_path: str,
    fmt: str = "unified",
    output_path: str | None = None,
    max_order_changes: int = 0,
) -> str:
    orig = load_world_book(original_path)
    opt = load_world_book(optimized_path)

    orig_entries = list(orig.get("entries", {}).values())
    opt_entries = list(opt.get("entries", {}).values())

    orig_by_uid = {e.get("uid"): e for e in orig_entries}
    opt_by_uid = {e.get("uid"): e for e in opt_entries}

    if fmt == "json":
        result = _diff_json(
            orig, original_path, optimized_path,
            orig_entries, opt_entries,
            orig_by_uid, opt_by_uid,
        )
        text = json.dumps(result, ensure_ascii=False, indent=2)
    else:
        text = _diff_unified(
            orig, original_path, optimized_path,
            orig_entries, opt_entries,
            orig_by_uid, opt_by_uid,
            max_order_changes,
        )

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
    return text


def _diff_unified(orig_data, orig_name, opt_name, orig_entries, opt_entries,
                  orig_by_uid, opt_by_uid, max_order_changes):
    lines = []
    lines.append("═" * 60)
    lines.append(f"  Diff: {orig_name} → {opt_name}")
    lines.append("═" * 60)

    lines.append(f"\n--- Entry Count")
    lines.append(f"  原始: {len(orig_entries)}")
    lines.append(f"  优化: {len(opt_entries)}")
    lines.append(f"  Δ: {len(opt_entries) - len(orig_entries):+d}")

    order_changes = []
    for e in orig_entries:
        uid = e.get("uid")
        if uid in opt_by_uid:
            old_order = e.get("order", 0)
            new_order = opt_by_uid[uid].get("order", 0)
            if old_order != new_order:
                order_changes.append((uid, e.get("comment", ""), old_order, new_order))

    if order_changes:
        order_changes.sort(key=lambda x: abs(x[2] - x[3]), reverse=True)
        display = order_changes[:max_order_changes] if max_order_changes > 0 else order_changes
        lines.append(f"\n--- Order Changes ({len(order_changes)} 条重排)")
        for uid, cmt, old, new in display:
            lines.append(f"  uid={uid:<4} {cmt:<30} {old:>4} → {new:<4}  Δ: {new - old:+d}")

    field_changes = []
    for uid in set(list(orig_by_uid.keys()) + list(opt_by_uid.keys())):
        if uid not in orig_by_uid or uid not in opt_by_uid:
            continue
        orig_e = orig_by_uid[uid]
        opt_e = opt_by_uid[uid]
        for field in orig_e:
            if field in ("content", "comment", "uid"):
                continue
            old_val = orig_e.get(field)
            new_val = opt_e.get(field)
            if old_val != new_val:
                field_changes.append((uid, orig_e.get("comment", ""), field, old_val, new_val))

    if field_changes:
        by_uid = {}
        for uid, cmt, field, old, new in field_changes:
            if uid not in by_uid:
                by_uid[uid] = []
            by_uid[uid].append((field, old, new))
        for uid, changes in by_uid.items():
            cmt = orig_by_uid.get(uid, {}).get("comment", "")
            lines.append(f"\n--- Field Changes: uid={uid} ---")
            for field, old, new in changes:
                lines.append(f"  {field:<20}: {str(old):<10} → {str(new):<10}")

    merged_comments = [e.get("comment", "") for e in opt_entries
                       if e.get("comment", "").startswith("合并:")]
    if merged_comments:
        lines.append(f"\n--- Merged Entries ({len(merged_comments)} groups) ---")
        for cmt in merged_comments:
            lines.append(f"  {cmt}")

    if "originalData" in orig_data:
        lines.append(f"\n--- Removed ---")
        lines.append(f"  originalData: (removed)")

    lines.append(f"\n--- Summary ---")
    lines.append(f"  Entries:     {len(orig_entries)} → {len(opt_entries)} ({len(opt_entries) - len(orig_entries):+d})")
    lines.append("═" * 60)

    return "\n".join(lines)


def _diff_json(orig_data, orig_name, opt_name, orig_entries, opt_entries,
               orig_by_uid, opt_by_uid):
    order_changes = []
    for e in orig_entries:
        uid = e.get("uid")
        if uid in opt_by_uid:
            old_order = e.get("order", 0)
            new_order = opt_by_uid[uid].get("order", 0)
            if old_order != new_order:
                order_changes.append({
                    "uid": uid, "comment": e.get("comment", ""),
                    "old": old_order, "new": new_order,
                })

    field_changes = []
    for uid in set(list(orig_by_uid.keys()) + list(opt_by_uid.keys())):
        if uid not in orig_by_uid or uid not in opt_by_uid:
            continue
        orig_e = orig_by_uid[uid]
        opt_e = opt_by_uid[uid]
        for field in orig_e:
            if field in ("content", "comment", "uid"):
                continue
            old_val = orig_e.get(field)
            new_val = opt_e.get(field)
            if old_val != new_val:
                field_changes.append({
                    "uid": uid, "field": field,
                    "old": old_val, "new": new_val,
                })

    return {
        "original": orig_name,
        "optimized": opt_name,
        "entry_count": {"before": len(orig_entries), "after": len(opt_entries)},
        "order_changes": order_changes,
        "field_changes": field_changes,
        "removed": ["originalData"] if "originalData" in orig_data else [],
    }


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--original", required=True)
    p.add_argument("--optimized", required=True)
    p.add_argument("--format", default="unified", choices=["unified", "json"])
    p.add_argument("--output", default=None)
    p.add_argument("--max-order-changes", type=int, default=0)
    args = p.parse_args()
    print(run(args.original, args.optimized, args.format, args.output, args.max_order_changes))
