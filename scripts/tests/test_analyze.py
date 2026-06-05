import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.analyze_entries import run as analyze_run


class TestAnalyzeStatic:
    def test_all_static(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "static_entry.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        for e in d["entries"]:
            assert e["is_static"] is True
            assert e["is_mixed"] is False


class TestAnalyzeDynamic:
    def test_all_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "dynamic_entry.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        for e in d["entries"]:
            assert e["is_static"] is False


class TestAnalyzeMixed:
    def test_mixed_splittable(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        e = d["entries"][0]
        assert e["is_static"] is False
        assert e["is_mixed"] is True
        assert e["suggested_split"] is True

    def test_mixed_unsplittable(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_unsplittable.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        e = d["entries"][0]
        assert e["suggested_split"] is False


class TestAnalyzeStructure:
    def test_output_structure(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        assert "source" in d
        assert "generated_at" in d
        assert "entries" in d
        assert "summary" in d

    def test_summary_counts(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        s = d["summary"]
        assert s["total"] == s["static"] + s["dynamic"] + s["mixed"]


class TestAnalyzeDisabled:
    def test_disabled_analyzed(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        assert len(d["entries"]) == 6


class TestAnalyzeEmpty:
    def test_empty_entries(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "empty_entries.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        assert d["entries"] == []
        assert d["summary"]["total"] == 0


class TestUnclosedEjs:
    def test_unclosed_mixed_not_splittable(self, fixtures_dir, tmp_path):
        import shutil, json
        src = str(fixtures_dir / "static_entry.json")
        test_inp = str(tmp_path / "test_unclosed.json")
        with open(src) as f:
            wb = json.load(f)
        wb["entries"]["0"]["content"] = (
            "## 静态标题\n静态内容\n"
            "<% if (x) { %>\n动态内容<% getvar('y') %>"
        )
        with open(test_inp, "w") as f:
            json.dump(wb, f)
        out = analyze_run(test_inp, str(tmp_path / "out.json"))
        with open(out) as f:
            d = json.load(f)
        e = d["entries"][0]
        assert e["suggested_split"] is False, \
            "Unclosed EJS with mixed content should not be suggested for split"

    def test_unclosed_all_dynamic(self, fixtures_dir, tmp_path):
        import shutil, json
        src = str(fixtures_dir / "static_entry.json")
        test_inp = str(tmp_path / "test_unclosed_all.json")
        with open(src) as f:
            wb = json.load(f)
        wb["entries"]["0"]["content"] = "<% if (x) { %>\n<%- getvar('y') %>"
        with open(test_inp, "w") as f:
            json.dump(wb, f)
        out = analyze_run(test_inp, str(tmp_path / "out.json"))
        with open(out) as f:
            d = json.load(f)
        e = d["entries"][0]
        assert e["is_static"] is False
        assert e["is_mixed"] is False

    def test_closed_mixed_still_splittable(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "mixed_entry.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out) as f:
            d = json.load(f)
        e = d["entries"][0]
        assert e["is_mixed"] is True
        assert e["suggested_split"] is True


class TestSuggestedSplitConsistency:
    def test_no_contradictory_suggested_split(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out) as f:
            d = json.load(f)
        for e in d["entries"]:
            if e["suggested_split"]:
                assert e["split_boundaries"] is not None, \
                    f"uid={e['uid']}: suggested_split=true but split_boundaries=null"


class TestWrapTag:
    def test_wrap_tag_in_boundaries(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "closed_tag_split.json")
        out = analyze_run(inp, str(tmp_path / "out.json"))
        with open(out, "r", encoding="utf-8") as f:
            d = json.load(f)
        boundaries = d["entries"][0].get("split_boundaries", [])
        assert len(boundaries) >= 2
        assert any(b.get("wrap_tag") == "A" and b["start_line"] == 0 for b in boundaries)
        assert any(b.get("wrap_tag") is None for b in boundaries)
