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


class TestAnalyzeBackup:
    def test_backup_created(self, fixtures_dir, tmp_path):
        import shutil
        src = str(fixtures_dir / "static_entry.json")
        test_inp = str(tmp_path / "test_static.json")
        shutil.copy2(src, test_inp)
        out = analyze_run(test_inp, str(tmp_path / "out.json"))
        backups = list(Path(tmp_path).glob("test_static.backup_*"))
        assert len(backups) >= 1
