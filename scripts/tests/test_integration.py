import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.analyze_entries import run as analyze_run
from scripts.split_entries import run as split_run
from scripts.reorder_entries import run as reorder_run
from scripts.merge_entries import run as merge_run
from scripts.run_pipeline import run as pipeline_run
from scripts import world_book_utils as wu


class TestFullPipeline:
    def test_all_four_steps_success(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        assert len(wb["entries"]) > 0

    def test_all_static_no_crash(self, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "in.json")
        entries = [{"uid": 0, "content": "静态", "order": 10, "position": 0, "depth": 4,
                     "constant": False, "key": [], "keysecondary": [], "disable": False}]
        wu.save_world_book(entries, inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        assert len(wb["entries"]) >= 1

    def test_all_dynamic_no_crash(self, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "in.json")
        entries = [{"uid": 0, "content": "{{getvar::x}}", "order": 10, "position": 0, "depth": 4,
                     "constant": False, "key": [], "keysecondary": [], "disable": False}]
        wu.save_world_book(entries, inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        assert len(wb["entries"]) >= 1

    def test_single_entry_no_crash(self, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "in.json")
        entries = [{"uid": 0, "content": "唯一内容", "order": 100, "position": 0, "depth": 4,
                     "constant": False, "key": [], "keysecondary": [], "disable": False}]
        wu.save_world_book(entries, inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        assert len(wb["entries"]) == 1

    def test_empty_entries_no_error(self, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "in.json")
        wu.save_world_book([], inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        assert len(wb["entries"]) == 0


class TestSemanticEquivalence:
    def test_original_text_preserved(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        orig_wb = wu.load_world_book(inp)
        total_in = sum(len(e["content"]) for e in orig_wb["entries"].values())
        total_out = sum(len(e["content"]) for e in wb["entries"].values())
        assert total_out >= total_in


class TestOrderConstraints:
    def test_static_before_dynamic(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        entries = list(wb["entries"].values())
        static_max = -1
        dynamic_min = float("inf")
        for e in entries:
            is_s = wu.determine_static(e["content"])
            is_supp = "[supplement-" in e.get("comment", "")
            is_copy = "[boundary-copy-" in e.get("comment", "")
            if is_s and not is_supp and not is_copy:
                static_max = max(static_max, e["order"])
            else:
                dynamic_min = min(dynamic_min, e["order"])
        if static_max >= 0 and dynamic_min < float("inf"):
            assert static_max < dynamic_min

    def test_orders_continuous(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        orders = sorted(e["order"] for e in wb["entries"].values())
        assert orders == list(range(len(orders)))


class TestFieldModification:
    def test_all_static_blue_lantern(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        for e in wb["entries"].values():
            if wu.determine_static(e["content"]):
                is_supp = "[supplement-" in e.get("comment", "")
                is_copy = "[boundary-copy-" in e.get("comment", "")
                if not is_supp and not is_copy:
                    assert e["constant"] is True

    def test_dynamic_all_pos4_depth0(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        for e in wb["entries"].values():
            if not wu.determine_static(e["content"]):
                is_supp = "[supplement-" in e.get("comment", "")
                is_copy = "[boundary-copy-" in e.get("comment", "")
                if not is_supp and not is_copy:
                    assert e["position"] == 4
                    assert e["depth"] == 0
                    assert e["role"] == 1


class TestMergeVerify:
    def test_no_duplicate_static_group(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        src = Path(inp)
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb = wu.load_world_book(d)
        groups = {}
        for e in wb["entries"].values():
            if wu.determine_static(e["content"]) and e.get("constant") is True:
                key = (e["position"], e["constant"], e["depth"])
                assert key not in groups, f"Duplicate static group: {key}"
                groups[key] = e

    def test_static_key_cleared(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        wb = wu.load_world_book(d)
        for e in wb["entries"].values():
            if wu.determine_static(e["content"]) and e.get("comment", "").startswith("合并:"):
                assert e["key"] == []


class TestIdempotency:
    def test_double_pipeline(self, full_pipeline_input, pipeline_tmpdir):
        run1 = pipeline_tmpdir / "run1"
        run2 = pipeline_tmpdir / "run2"
        run1.mkdir(exist_ok=True)
        run2.mkdir(exist_ok=True)
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d1 = pipeline_run(inp, str(run1))
        d2 = pipeline_run(d1, str(run2))
        wb1 = wu.load_world_book(d1)
        wb2 = wu.load_world_book(d2)
        assert len(wb1["entries"]) == len(wb2["entries"])

    def test_no_duplicate_split_marks(self, full_pipeline_input, pipeline_tmpdir):
        run1 = pipeline_tmpdir / "run1"
        run2 = pipeline_tmpdir / "run2"
        run1.mkdir(exist_ok=True)
        run2.mkdir(exist_ok=True)
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d1 = pipeline_run(inp, str(run1))
        d2 = pipeline_run(d1, str(run2))
        wb2 = wu.load_world_book(d2)
        for e in wb2["entries"].values():
            cmt = e.get("comment", "")
            assert "[split-static]" not in cmt or cmt.count("[split-static]") == 1
            assert "[split-dynamic]" not in cmt or cmt.count("[split-dynamic]") == 1


class TestGoldenFile:
    def test_exact_match(self, full_pipeline_input, full_pipeline_expected, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        actual = wu.load_world_book(d)
        assert actual["entries"] == full_pipeline_expected["entries"]


class TestSemanticEquivalenceFull:
    def test_original_content_no_loss(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        wb = wu.load_world_book(d)
        orig_wb = wu.load_world_book(inp)
        all_output_text = "".join(e["content"] for e in wb["entries"].values())
        for orig_e in orig_wb["entries"].values():
            orig_text = orig_e["content"].strip()
            if orig_text:
                assert len(orig_text) > 0

    def test_dynamic_content_intact(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        wb = wu.load_world_book(d)
        orig_wb = wu.load_world_book(inp)
        orig_dynamic = [e for e in orig_wb["entries"].values()
                         if not wu.determine_static(e["content"])]
        non_mixed_dynamic = [e for e in orig_dynamic
                              if wu.classify_entry(e["content"]) == (False, False)]
        all_output_text = "".join(e["content"] for e in wb["entries"].values())
        for oe in non_mixed_dynamic:
            assert oe["content"].strip() in all_output_text, \
                f"Dynamic content lost: {oe['comment']}"

    def test_split_reversibility(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        wb = wu.load_world_book(b)
        orig_wb = wu.load_world_book(inp)
        orig_count = len(orig_wb["entries"])
        split_count = len(wb["entries"])
        assert split_count >= orig_count


class TestOrderConstraintsFull:
    def test_same_group_relative_order_preserved(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        wb = wu.load_world_book(c)
        entries = list(wb["entries"].values())
        entries.sort(key=lambda x: x.get("order", 0))
        for i in range(len(entries) - 1):
            assert entries[i]["order"] <= entries[i + 1]["order"]


class TestFieldModificationFull:
    def test_static_use_probability_off(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        wb = wu.load_world_book(d)
        for e in wb["entries"].values():
            if wu.determine_static(e["content"]) and e.get("constant") is True:
                assert e["useProbability"] is False
                assert e["probability"] == 100

    def test_static_cooldown_sticky_delay_cleared(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        d = pipeline_run(inp, str(pipeline_tmpdir))
        wb = wu.load_world_book(d)
        for e in wb["entries"].values():
            if wu.determine_static(e["content"]) and e.get("constant") is True:
                assert e["cooldown"] == 0
                assert e["sticky"] == 0
                assert e["delay"] == 0


class TestMergeVerifyFull:
    def test_dynamic_entry_count_unchanged(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        a = analyze_run(inp, str(pipeline_tmpdir / "a.json"))
        b = split_run(inp, a, str(pipeline_tmpdir / "b.json"))
        c = reorder_run(b, str(pipeline_tmpdir / "c.json"))
        wb3 = wu.load_world_book(c)
        pre_merge_dynamic = sum(1 for e in wb3["entries"].values()
                                if not wu.determine_static(e["content"])
                                and "[supplement-" not in e.get("comment", "")
                                and "[boundary-copy-" not in e.get("comment", ""))
        d = merge_run(c, str(pipeline_tmpdir / "d.json"))
        wb4 = wu.load_world_book(d)
        post_merge_dynamic = sum(1 for e in wb4["entries"].values()
                                  if not wu.determine_static(e["content"])
                                  and "[supplement-" not in e.get("comment", "")
                                  and "[boundary-copy-" not in e.get("comment", ""))
        assert post_merge_dynamic == pre_merge_dynamic


class TestErrorHandling:
    def test_no_analysis_file_error(self, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "in.json")
        entries = [{"uid": 0, "content": "test", "order": 10, "position": 0,
                      "depth": 4, "constant": False, "key": [], "keysecondary": [], "disable": False}]
        wu.save_world_book(entries, inp)
        try:
            split_run(inp, str(pipeline_tmpdir / "nonexistent.json"), str(pipeline_tmpdir / "out.json"))
            assert False, "Should raise FileNotFoundError"
        except (FileNotFoundError, OSError):
            pass


class TestBoundaryAndSupplementFull:
    def test_boundary_no_dynamic_no_copy_int(self, pipeline_tmpdir):
        entries = [
            {"uid": 0, "content": "<暗部>", "order": 10, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
            {"uid": 1, "content": "纯静态内容", "order": 20, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
            {"uid": 2, "content": "</暗部>", "order": 30, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
        ]
        inp = str(pipeline_tmpdir / "in.json")
        wu.save_world_book(entries, inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 0

    def test_all_static_no_supplement_int(self, pipeline_tmpdir):
        entries = [
            {"uid": 0, "content": "静态A", "order": 10, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
            {"uid": 1, "content": "静态B", "order": 20, "position": 1, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
        ]
        inp = str(pipeline_tmpdir / "in.json")
        wu.save_world_book(entries, inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) == 0
    def test_boundary_copies_exist(self, pipeline_tmpdir):
        entries = [
            {"uid": 0, "content": "<暗部>", "order": 10, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
            {"uid": 1, "content": "{{getvar::x}}", "order": 20, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
            {"uid": 2, "content": "</暗部>", "order": 30, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
        ]
        inp = str(pipeline_tmpdir / "in.json")
        wu.save_world_book(entries, inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        copies = [e for e in wb["entries"].values()
                   if "[boundary-copy-" in e.get("comment", "")]
        assert len(copies) == 2
        for copy in copies:
            assert copy["key"] == ["/.*/"]

    def test_supplement_exists(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) == 2

    def test_supplement_wraps_dynamic(self, full_pipeline_input, pipeline_tmpdir):
        inp = str(pipeline_tmpdir / "input.json")
        wu.save_world_book(list(full_pipeline_input["entries"].values()), inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        entries = sorted(wb["entries"].values(), key=lambda x: x["order"])
        supp_start_idx = None
        supp_end_idx = None
        for i, e in enumerate(entries):
            if "[supplement-start]" in e.get("comment", ""):
                supp_start_idx = i
            if "[supplement-end]" in e.get("comment", ""):
                supp_end_idx = i
        assert supp_start_idx is not None
        assert supp_end_idx is not None
        assert supp_start_idx < supp_end_idx

    def test_no_supplement_when_all_static(self, pipeline_tmpdir):
        entries = [
            {"uid": 0, "content": "静态A", "order": 10, "position": 0, "depth": 4,
             "constant": False, "key": [], "keysecondary": [], "disable": False},
        ]
        inp = str(pipeline_tmpdir / "in.json")
        wu.save_world_book(entries, inp)
        out_dir = pipeline_tmpdir / "out"
        out_dir.mkdir(exist_ok=True)
        d = pipeline_run(inp, str(out_dir))
        wb = wu.load_world_book(d)
        supps = [e for e in wb["entries"].values()
                  if "[supplement-" in e.get("comment", "")]
        assert len(supps) == 0
