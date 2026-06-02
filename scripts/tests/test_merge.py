import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.merge_entries import run as merge_run
from scripts.analyze_entries import run as analyze_run
from scripts.split_entries import run as split_run
from scripts.reorder_entries import run as reorder_run
from scripts import world_book_utils as wu


def _full_pre_merge(fixture_name, fixtures_dir, tmp_path):
    inp = str(fixtures_dir / fixture_name)
    a = analyze_run(inp, str(tmp_path / "a.json"))
    b = split_run(inp, a, str(tmp_path / "b.json"))
    c = reorder_run(b, str(tmp_path / "c.json"))
    return c


class TestMergeBasics:
    def test_groups_merged(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        merged = [e for e in wb["entries"].values()
                   if e.get("comment", "").startswith("合并:")]
        assert len(merged) >= 1

    def test_content_concatenated(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if e.get("comment", "").startswith("合并:"):
                assert "\n\n" in e["content"]

    def test_comment_format(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if e.get("comment", "").startswith("合并:"):
                assert "-" in e["comment"]

    def test_key_cleared(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if e.get("comment", "").startswith("合并:"):
                assert e["key"] == []


class TestMergeExclusions:
    def test_dynamic_entries_preserved(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        dynamic = [e for e in wb["entries"].values()
                    if not wu.determine_static(e["content"])]
        assert len(dynamic) >= 2

    def test_boundary_copy_not_merged(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_with_dynamic.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        b = split_run(inp, a, str(tmp_path / "b.json"))
        c = reorder_run(b, str(tmp_path / "c.json"))
        out = merge_run(c, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) >= 2

    def test_supplement_not_merged(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) >= 2


class TestMergeEdgeCases:
    def test_single_entry_group(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "single_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        b = split_run(inp, a, str(tmp_path / "b.json"))
        c = reorder_run(b, str(tmp_path / "c.json"))
        out = merge_run(c, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 1

    def test_empty_entries(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "empty_entries.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        b = split_run(inp, a, str(tmp_path / "b.json"))
        c = reorder_run(b, str(tmp_path / "c.json"))
        out = merge_run(c, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 0

    def test_uids_continuous(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out = merge_run(pre, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        uids = sorted(e["uid"] for e in wb["entries"].values())
        assert uids == list(range(len(uids)))

    def test_idempotent(self, fixtures_dir, tmp_path):
        pre = _full_pre_merge("small_world_book.json", fixtures_dir, tmp_path)
        out1 = merge_run(pre, str(tmp_path / "out1.json"))
        out2 = merge_run(out1, str(tmp_path / "out2.json"))
        wb1 = wu.load_world_book(out1)
        wb2 = wu.load_world_book(out2)
        assert len(wb1["entries"]) == len(wb2["entries"])
