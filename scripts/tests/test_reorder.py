import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.reorder_entries import run as reorder_run, is_boundary_entry, BoundaryPair
from scripts import world_book_utils as wu


class TestFieldModStatic:
    def _reorder_fixture(self, fixture_name, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / fixture_name)
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        return wu.load_world_book(out)

    def test_static_pos4_lt10(self, fixtures_dir, tmp_path):
        wb = self._reorder_fixture("multi_depth.json", fixtures_dir, tmp_path)
        for e in wb["entries"].values():
            if e.get("comment") == "depth_1":
                assert e["position"] == 4
                assert e["depth"] == 0
                assert e["role"] == 1
                assert e["constant"] is True
                assert e["cooldown"] == 0
                assert e["probability"] == 100
                assert e["useProbability"] is False
                assert e["sticky"] == 0
                assert e["delay"] == 0

    def test_static_pos4_gte10(self, fixtures_dir, tmp_path):
        wb = self._reorder_fixture("multi_depth.json", fixtures_dir, tmp_path)
        for e in wb["entries"].values():
            if e.get("comment") == "depth_9999":
                assert e["depth"] == 9999
                assert e["constant"] is True

    def test_static_not_pos4(self, fixtures_dir, tmp_path):
        wb = self._reorder_fixture("multi_position.json", fixtures_dir, tmp_path)
        found_pos0 = False
        for e in wb["entries"].values():
            if e.get("comment") == "pos0_before":
                assert e["position"] == 0
                assert e["constant"] is True
                assert e["cooldown"] == 0
                found_pos0 = True
        assert found_pos0


class TestFieldModDynamic:
    def test_dynamic_to_pos4(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if not wu.determine_static(e["content"]):
                if "[supplement-" not in e.get("comment", "") and "[boundary-copy-" not in e.get("comment", ""):
                    assert e["position"] == 4
                    assert e["depth"] == 0
                    assert e["role"] == 1


class TestOrderAssignment:
    def test_static_before_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        static_orders = []
        dynamic_orders = []
        for e in wb["entries"].values():
            is_s = wu.determine_static(e["content"])
            is_supp = "[supplement-" in e.get("comment", "")
            is_copy = "[boundary-copy-" in e.get("comment", "")
            if is_copy or is_supp:
                dynamic_orders.append(e["order"])
            elif is_s:
                static_orders.append(e["order"])
            else:
                dynamic_orders.append(e["order"])
        if static_orders and dynamic_orders:
            assert max(static_orders) < min(dynamic_orders)

    def test_orders_continuous(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        orders = sorted(e["order"] for e in wb["entries"].values())
        assert orders == list(range(len(orders)))


class TestBoundaryDetection:
    def test_xml_open_pure_tag(self):
        r = is_boundary_entry("<暗部>")
        assert r is not None
        assert r[0] == "xml_open"
        assert r[1] == "暗部"

    def test_xml_close_pure_tag(self):
        r = is_boundary_entry("</暗部>")
        assert r is not None
        assert r[0] == "xml_close"
        assert r[1] == "暗部"

    def test_xml_open_with_text(self):
        r = is_boundary_entry("<暗部>\n暗部组织介绍")
        assert r is not None
        assert r[0] == "xml_open"
        assert r[2] == "<暗部>"

    def test_md_open(self):
        r = is_boundary_entry("# 暗部开始")
        assert r is not None
        assert r[0] == "md_open"

    def test_md_close(self):
        r = is_boundary_entry("## 暗部结束")
        assert r is not None
        assert r[0] == "md_close"

    def test_closed_tag_not_boundary(self):
        r = is_boundary_entry("<暗部>成员设定</暗部>")
        assert r is None

    def test_dynamic_content_not_boundary(self):
        r = is_boundary_entry("<暗部>\n<%= getvar() %>")
        assert r is None


class TestBoundaryPairs:
    def test_simple_pair(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_xml_open.json")
        tmp_inp = str(tmp_path / "b1.json")
        # combine open+close into one book
        open_wb = wu.load_world_book(inp)
        close_wb = wu.load_world_book(str(fixtures_dir / "boundary_xml_close.json"))
        combined = list(open_wb["entries"].values()) + list(close_wb["entries"].values())
        wu.save_world_book(combined, tmp_inp)
        out = str(tmp_path / "out.json")
        reorder_run(tmp_inp, out)
        wb = wu.load_world_book(out)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 0

    def test_nested_pair(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_nested.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        assert len(wb["entries"]) >= 4

    def test_boundary_with_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_with_dynamic.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 2

    def test_boundary_no_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_no_dynamic.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 0

    def test_cross_position_no_pair(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "boundary_cross_pos.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 0


class TestSupplementWrapper:
    def test_supplement_created_with_dynamic(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) == 2

    def test_all_static_no_supplement(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "integration/all_static.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) == 0

    def test_supplement_has_wildcard_key(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if "[supplement-start]" in e.get("comment", ""):
                assert e["key"] == ["/.*/"]
                assert e["constant"] is False


class TestIdempotency:
    def test_double_run_idempotent(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "small_world_book.json")
        out1 = str(tmp_path / "out1.json")
        out2 = str(tmp_path / "out2.json")
        reorder_run(inp, out1)
        reorder_run(out1, out2)
        wb1 = wu.load_world_book(out1)
        wb2 = wu.load_world_book(out2)
        assert len(wb1["entries"]) == len(wb2["entries"])


class TestDepthHandling:
    def test_null_depth(self, fixtures_dir, tmp_path):
        inp = str(fixtures_dir / "multi_depth.json")
        out = str(tmp_path / "out.json")
        reorder_run(inp, out)
        wb = wu.load_world_book(out)
        for e in wb["entries"].values():
            if e.get("comment") == "depth_null":
                assert e["constant"] is True
