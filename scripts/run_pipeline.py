import sys
from pathlib import Path

from . import analyze_entries, split_entries, reorder_entries, merge_entries
from . import world_book_utils as wu


def run(input_path: str, output_dir: str | None = None,
        wrapper_name: str = "补充内容") -> str:
    """一键执行完整优化管线：分析 → 拆分 → 重排序 → 合并。

    四步串联执行，每步输出到指定目录或输入文件所在目录。
    仅在输入为原始世界书（非管线中间产物）时创建备份。

    Args:
        input_path: 原始世界书 JSON 路径。
        output_dir: 输出目录。None 时使用输入文件所在目录。
        wrapper_name: 补充包裹的名称（默认"补充内容"）。

    Returns:
        最终产物 `_merged.json` 的路径。

    Notes:
        每个步骤的输出独立保存，便于分步调试。
        仅备份原始文件，不备份管线中间产物。
    """
    assert input_path is not None
    assert Path(input_path).exists()
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
