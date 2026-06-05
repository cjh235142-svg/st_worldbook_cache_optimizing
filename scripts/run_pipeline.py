import sys
from pathlib import Path

from . import analyze_entries, split_entries, reorder_entries, merge_entries
from . import world_book_utils as wu


def run(input_path: str, output_dir: str | None = None,
        wrapper_name: str = "补充内容") -> str:
    src = Path(input_path).resolve()
    out_dir = Path(output_dir) if output_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    is_pipeline_product = any(
        src.stem.endswith(suffix)
        for suffix in ("_analysis", "_split", "_reordered", "_merged")
    )
    if not is_pipeline_product:
        wu.backup_file(input_path)

    print(f"[1/4] Analyzing: {src.name}")
    analysis_path = analyze_entries.run(str(src),
                                        str(out_dir / f"{src.stem}_analysis.json"))
    print(f"  -> {Path(analysis_path).name}")

    print(f"[2/4] Splitting entries...")
    split_path = split_entries.run(str(src), analysis_path,
                                   str(out_dir / f"{src.stem}_split.json"))
    print(f"  -> {Path(split_path).name}")

    print(f"[3/4] Reordering entries...")
    reordered_path = reorder_entries.run(split_path,
                                         str(out_dir / f"{src.stem}_reordered.json"),
                                         wrapper_name)
    print(f"  -> {Path(reordered_path).name}")

    print(f"[4/4] Merging static entries...")
    merged_path = merge_entries.run(reordered_path,
                                    str(out_dir / f"{src.stem}_merged.json"))
    print(f"  -> {Path(merged_path).name}")

    print(f"\nPipeline complete. Final output: {merged_path}")
    return merged_path


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="World book cache optimization pipeline")
    p.add_argument("-i", "--input", required=True, help="Input world book JSON")
    p.add_argument("-d", "--output-dir", default=None, help="Output directory")
    p.add_argument("-w", "--wrapper-name", default="补充内容", help="Wrapper content name")
    args = p.parse_args()
    run(args.input, args.output_dir, args.wrapper_name)
