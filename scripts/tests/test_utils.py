import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts import world_book_utils as wu


class TestDetectMarkers:
    def test_pure_text_static(self):
        assert wu.detect_markers("这是普通描述文本") == []

    def test_xml_static(self):
        assert wu.detect_markers("<角色>设定</角色>") == []

    def test_ejs_block_dynamic(self):
        r = wu.detect_markers("<% if (x) { %>")
        assert len(r) > 0 and r[0] in ("<% if", "<%")

    def test_ejs_output_dynamic(self):
        r = wu.detect_markers("<%= var %>")
        assert "<%=" in r

    def test_ejs_unescaped_dynamic(self):
        r = wu.detect_markers("<%- var %>")
        assert "<%-" in r

    def test_getvar_macro_dynamic(self):
        r = wu.detect_markers("{{getvar::x}}")
        assert "{{getvar::" in r

    def test_setvar_macro_dynamic(self):
        r = wu.detect_markers("{{setvar::x::y}}")
        assert "{{setvar::" in r

    def test_incvar_macro_dynamic(self):
        r = wu.detect_markers("{{incvar::x}}")
        assert "{{incvar::" in r

    def test_xbgetvar_macro_dynamic(self):
        r = wu.detect_markers("{{xbgetvar_yaml_idx::x}}")
        assert "{{xbgetvar_yaml_idx::" in r

    def test_if_macro_dynamic(self):
        r = wu.detect_markers("{{if condition}}")
        assert "{{if" in r

    def test_dot_prefix_dynamic(self):
        r = wu.detect_markers("{{.myvar}}")
        assert "{{." in r

    def test_dollar_prefix_dynamic(self):
        r = wu.detect_markers("{{$global}}")
        assert "{{$" in r

    def test_getvar_func_dynamic(self):
        r = wu.detect_markers("getvar('x')")
        assert "getvar(" in r

    def test_setvar_func_dynamic(self):
        r = wu.detect_markers("setvar('x')")
        assert "setvar(" in r

    def test_variables_ref_dynamic(self):
        r = wu.detect_markers("variables.x")
        assert "variables." in r

    def test_multi_markers(self):
        r = wu.detect_markers("<% ... %> {{getvar::x}}")
        assert len(r) >= 2

    def test_empty_string_static(self):
        assert wu.detect_markers("") == []

    def test_whitespace_static(self):
        assert wu.detect_markers("\n\n") == []

    def test_char_macro_static(self):
        assert wu.detect_markers("{{char}}") == []

    def test_braces_no_macro_static(self):
        assert wu.detect_markers("{ something }") == []

    def test_time_macro_dynamic(self):
        r = wu.detect_markers("{{time}}")
        assert "{{time}}" in r

    def test_date_macro_dynamic(self):
        r = wu.detect_markers("{{date}}")
        assert "{{date}}" in r

    def test_idleDuration_macro_dynamic(self):
        r = wu.detect_markers("{{idleDuration}}")
        assert "{{idleDuration}}" in r


class TestDetermineStatic:
    def test_pure_static(self):
        assert wu.determine_static("普通文本") is True

    def test_dynamic(self):
        assert wu.determine_static("{{getvar::x}}") is False

    def test_empty(self):
        assert wu.determine_static("") is True


class TestClassifyEntry:
    def test_pure_static(self):
        s, m = wu.classify_entry("普通文本")
        assert (s, m) == (True, False)

    def test_pure_dynamic_ejs_full(self):
        s, m = wu.classify_entry("<% if (x) { %>\nA\n<% } else { %>\nB\n<% } %>")
        assert s == False
        assert m == False

    def test_mixed(self):
        s, m = wu.classify_entry("静态文本\n<%= getvar('x') %>")
        assert (s, m) == (False, True)

    def test_empty(self):
        s, m = wu.classify_entry("")
        assert (s, m) == (True, False)


class TestFindXmlTags:
    def test_single_pair(self):
        r = wu.find_xml_tags("<角色>内容</角色>")
        assert len(r) == 1 and r[0]["tag"] == "角色"

    def test_no_tag(self):
        assert wu.find_xml_tags("纯文本") == []

    def test_nested(self):
        r = wu.find_xml_tags("<A><B>x</B></A>")
        assert len(r) >= 1

    def test_multiple_siblings(self):
        r = wu.find_xml_tags("<X>x</X><Y>y</Y>")
        assert len(r) == 2

    def test_unclosed(self):
        r = wu.find_xml_tags("<X>内容")
        assert len(r) == 0

    def test_self_closing(self):
        r = wu.find_xml_tags("<X/>")
        assert len(r) == 0


class TestSplitByHeadings:
    def test_h1(self):
        r = wu.split_by_headings("# A\nx\n# B\ny")
        assert len(r) >= 2

    def test_h2(self):
        r = wu.split_by_headings("## A\nx\n## B\ny")
        assert len(r) >= 2

    def test_mixed(self):
        r = wu.split_by_headings("# H1\nx\n## H2\ny\n# H1\nz")
        assert len(r) >= 3

    def test_no_headings(self):
        r = wu.split_by_headings("纯文本")
        assert len(r) == 1

    def test_headings_only(self):
        r = wu.split_by_headings("# A\n# B")
        assert len(r) >= 1


class TestReassignUids:
    def test_normal(self):
        entries = [{"uid": 5}, {"uid": 12}, {"uid": 3}]
        r = wu.reassign_uids(entries)
        assert [e["uid"] for e in r] == [0, 1, 2]

    def test_empty(self):
        assert wu.reassign_uids([]) == []

    def test_single(self):
        r = wu.reassign_uids([{"uid": 99}])
        assert r[0]["uid"] == 0


class TestSortEntries:
    def test_static_before_dynamic(self):
        entries = [
            {"content": "{{getvar::x}}", "order": 10, "position": 0, "depth": 4, "_original_order": 10},
            {"content": "静态", "order": 20, "position": 0, "depth": 4, "_original_order": 20},
        ]
        r = wu.sort_entries(entries)
        assert r[0]["content"] == "静态"

    def test_same_static_pos_order(self):
        entries = [
            {"content": "B", "order": 10, "position": 1, "depth": 4, "_original_order": 10},
            {"content": "A", "order": 20, "position": 0, "depth": 4, "_original_order": 20},
        ]
        r = wu.sort_entries(entries)
        assert r[0]["position"] <= r[1]["position"]

    def test_deep_entries_first(self):
        entries = [
            {"content": "A", "order": 10, "position": 4, "depth": 5, "_original_order": 10},
            {"content": "B", "order": 20, "position": 4, "depth": 9999, "_original_order": 20},
        ]
        r = wu.sort_entries(entries)
        assert r[0]["depth"] == 9999


class TestHasSpecialPlugin:
    def test_generate_before(self):
        assert wu.has_special_plugin("", "[GENERATE:BEFORE] 标题") is True

    def test_initial_variables(self):
        assert wu.has_special_plugin("", "[InitialVariables]数据") is True

    def test_preprocessing_decorator(self):
        assert wu.has_special_plugin("@@preprocessing\ncontent", "") is True

    def test_normal_text(self):
        assert wu.has_special_plugin("普通内容", "普通标题") is False

    def test_inject_title(self):
        assert wu.has_special_plugin("", "@INJECT pos=0") is True


class TestCountNetBraces:
    def test_simple_if(self):
        r = wu.count_net_braces("if (x) {")
        assert r == 1

    def test_balanced(self):
        r = wu.count_net_braces("if (x) { a(); }")
        assert r == 0

    def test_nested(self):
        r = wu.count_net_braces("if (x) { if (y) { a(); } b(); }")
        assert r == 0

    def test_string_literal_braces(self):
        r = wu.count_net_braces("'foo{bar}'")
        assert r == 0


class TestFindEjsCompoundRanges:
    def test_simple_compound(self):
        content = "# 标题\n<% if (cond) { %>\n文本\n<% } else { %>\n文本2\n<% } %>\n# 末尾"
        ranges = wu.find_ejs_compound_ranges(content)
        assert len(ranges) == 1

    def test_no_compound(self):
        content = "<%= var %>"
        ranges = wu.find_ejs_compound_ranges(content)
        assert ranges == []


class TestIsOutletEntry:
    def test_outlet_pos(self):
        assert wu.is_outlet_entry({"position": 7}) is True

    def test_non_outlet(self):
        assert wu.is_outlet_entry({"position": 0}) is False

    def test_no_position(self):
        assert wu.is_outlet_entry({}) is False


class TestFindOutermostXmlTag:
    def test_simple(self):
        assert wu.find_outermost_xml_tag("<角色>内容</角色>") == "角色"

    def test_nested(self):
        assert wu.find_outermost_xml_tag("<A><B>x</B></A>") == "A"

    def test_no_tag(self):
        assert wu.find_outermost_xml_tag("普通文本") is None


class TestLoadSaveWorldBook:
    def test_load_valid(self, fixtures_dir):
        wb = wu.load_world_book(str(fixtures_dir / "static_entry.json"))
        assert "entries" in wb

    def test_load_invalid_path(self):
        try:
            wu.load_world_book("nonexistent.json")
            assert False, "Should raise"
        except FileNotFoundError:
            pass

    def test_save_and_load(self, tmp_path):
        entries = [{"uid": 0, "content": "test", "comment": "t"}]
        p = str(tmp_path / "test.json")
        wu.save_world_book(entries, p)
        wb = wu.load_world_book(p)
        assert len(wb["entries"]) == 1


class TestBackupFile:
    def test_backup_created(self, fixtures_dir):
        src = str(fixtures_dir / "static_entry.json")
        backup = wu.backup_file(src)
        assert Path(backup).exists()


class TestIsEmptyOrHeadingOnly:
    def test_heading_only(self):
        assert wu._is_empty_or_heading_only("## 人物介绍\n") is True

    def test_xml_tag_only(self):
        assert wu._is_empty_or_heading_only("<角色></角色>") is True

    def test_with_content(self):
        assert wu._is_empty_or_heading_only("## 介绍\n有内容") is False

    def test_whitespace_only(self):
        assert wu._is_empty_or_heading_only("\n\n") is True
