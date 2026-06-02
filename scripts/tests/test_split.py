import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.analyze_entries import run as analyze_run
from scripts.split_entries import run as split_run
from scripts import world_book_utils as wu


class TestSplit:
    def test_split_mixed_by_heading(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        entries = list(wb["entries"].values())
        assert len(entries) > 1

    def test_xml_tag_preserved(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if "split-static" in e.get("comment", ""):
                assert "<御坂美琴>" in e["content"]
                assert "</御坂美琴>" in e["content"]

    def test_pure_static_no_split(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "static_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 2

    def test_pure_dynamic_no_split(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "dynamic_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 3

    def test_comment_suffix_static(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        comments = [e["comment"] for e in wb["entries"].values()]
        assert any("[split-static]" in c for c in comments)

    def test_comment_suffix_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        comments = [e["comment"] for e in wb["entries"].values()]
        assert any("[split-dynamic]" in c for c in comments)

    def test_uid_continuous(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        uids = [e["uid"] for e in wb["entries"].values()]
        assert uids == list(range(len(uids)))

    def test_key_inherited(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if "split-static" in e.get("comment", ""):
                assert "御坂美琴" in e["key"]

    def test_empty_entries_no_error(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "empty_entries.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 0

    def test_suggested_split_skipped(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_unsplittable.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) == 1

    def test_split_semantic_equivalence(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        orig_wb = wu.load_world_book(inp)
        original_entries = list(orig_wb["entries"].values())
        split_entries = list(wb["entries"].values())
        assert len(split_entries) >= len(original_entries)

    def test_ejs_full_coverage_no_split(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_unsplittable.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        comments = [e.get("comment", "") for e in wb["entries"].values()]
        assert not any("[split-" in c for c in comments)

    def test_keysecondary_inherited(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        orig_wb = wu.load_world_book(inp)
        orig_entry = list(orig_wb["entries"].values())[0]
        for e in wb["entries"].values():
            if "split-static" in e.get("comment", ""):
                assert "keysecondary" in e
                assert e["keysecondary"] == orig_entry.get("keysecondary", [])

    def test_no_duplicate_closing_tags(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        a = analyze_run(inp, str(tmp_path / "a.json"))
        out = split_run(inp, a, str(tmp_path / "out.json"))
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            content = e.get("content", "")
            tags = re.findall(r"<([\u4e00-\u9fff\w]+)>", content)
            closes = re.findall(r"</([\u4e00-\u9fff\w]+)>", content)
            from collections import Counter
            oc = Counter(tags)
            cc = Counter(closes)
            for tag in oc:
                if tag in cc:
                    pass
            assert all(oc[t] == cc.get(t, 0) for t in oc | cc), \
                f"Tag mismatch in {e.get('comment','')}: opens={dict(oc)}, closes={dict(cc)}"
