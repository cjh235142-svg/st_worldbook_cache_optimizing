import json
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from world_book_utils import load_world_book, determine_static, sort_entries, find_xml_tags


_SUFFIX_RE = re.compile(r'\s*\[(?:split-(?:static|dynamic)|boundary-copy-(?:open|close))\]$')


def strip_comment_suffix(comment: str) -> str:
    return _SUFFIX_RE.sub('', comment).strip()


def is_split_static(entry: dict) -> bool:
    return '[split-static]' in entry.get('comment', '')


def is_split_dynamic(entry: dict) -> bool:
    return '[split-dynamic]' in entry.get('comment', '')


def is_merged_group(entry: dict) -> bool:
    return entry.get('comment', '').startswith('合并:')


def is_boundary_copy(entry: dict) -> bool:
    return '[boundary-copy-' in entry.get('comment', '')


def is_supplement(entry: dict) -> bool:
    return '[supplement-' in entry.get('comment', '')


def entry_short(e: dict) -> str:
    return f'"{e.get("comment","")[:40]}"  uid={e.get("uid")}  order={e.get("order")}  pos={e.get("position")}'


def run(
    original_path: str,
    optimized_path: str,
    fmt: str = "unified",
    output_path: str | None = None,
    max_order_changes: int = 0,
    from_uids: list[int] | None = None,
    from_search: str | None = None,
    to_uids: list[int] | None = None,
    to_search: str | None = None,
) -> str:
    orig = load_world_book(original_path)
    opt = load_world_book(optimized_path)
    raw_orig = list(orig.get("entries", {}).values())
    raw_opt = list(opt.get("entries", {}).values())

    for e in raw_orig:
        e.setdefault('_is_static', determine_static(e.get('content', '')))
    for e in raw_opt:
        e.setdefault('_is_static', determine_static(e.get('content', '')))

    orig_sorted = sort_entries(raw_orig)
    opt_sorted = sort_entries(raw_opt)

    for i, e in enumerate(orig_sorted):
        e['_sorted_pos'] = i
    for i, e in enumerate(opt_sorted):
        e['_sorted_pos'] = i

    opt_index = _build_opt_index(opt_sorted)

    if from_uids or from_search:
        filtered = _filter_entries(orig_sorted, from_uids, from_search)
        text = _format_forward_tracking(filtered, opt_index, original_path, optimized_path)
    elif to_uids or to_search:
        filtered = _filter_entries(opt_sorted, to_uids, to_search)
        text = _format_reverse_tracking(filtered, orig_sorted, opt_index, original_path, optimized_path)
    elif fmt == "json":
        text = _format_json(orig_sorted, opt_sorted, opt_index, orig, original_path, optimized_path)
    else:
        text = _format_full_diff(orig_sorted, opt_sorted, opt_index, orig, original_path, optimized_path)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(text)
    return text


def _build_opt_index(opt_entries: list[dict]) -> dict:
    split_by_base = defaultdict(list)
    merged_groups = []
    normal = []
    created = []

    for e in opt_entries:
        cmt = e.get('comment', '')
        if is_split_static(e):
            split_by_base[strip_comment_suffix(cmt)].append((e, 'split-static'))
        elif is_split_dynamic(e):
            split_by_base[strip_comment_suffix(cmt)].append((e, 'split-dynamic'))
        elif is_merged_group(e):
            merged_groups.append(e)
        elif is_boundary_copy(e) or is_supplement(e):
            created.append(e)
        else:
            normal.append(e)

    return {
        'split_by_base': dict(split_by_base),
        'merged_groups': merged_groups,
        'normal': normal,
        'created': created,
    }


def _find_static_part_in_merged(orig_content: str, orig_comment: str, merged_groups: list[dict]) -> dict | None:
    """Try to locate a split entry's static part within merged groups."""
    # Strategy 1: find by top-level XML tags in original content
    tags = find_xml_tags(orig_content)
    if tags:
        outer_tag = max(tags, key=lambda t: t['close_end'] - t['open_start'])
        tag_name = outer_tag['tag']
        open_str = f'<{tag_name}>'
        close_str = f'</{tag_name}>'
        for mg in merged_groups:
            mgc = mg.get('content', '')
            if open_str in mgc and close_str in mgc:
                return mg

    # Strategy 2: find by unique heading in original content
    lines = orig_content.splitlines()
    for line in lines:
        m = re.match(r'^#{1,2}\s+(.+)', line)
        if m:
            heading = line.strip()
            for mg in merged_groups:
                mgc = mg.get('content', '')
                if heading in mgc:
                    return mg

    # Strategy 3: find by comment text in merged groups
    if orig_comment:
        for mg in merged_groups:
            mgc = mg.get('content', '')
            if orig_comment in mgc:
                return mg

    return None


def _match_original_to_opt(orig: dict, opt_index: dict) -> dict:
    orig_cmt = strip_comment_suffix(orig.get('comment', ''))
    orig_content = orig.get('content', '')

    result = {'type': 'unknown', 'targets': []}

    # 1) Comment-match in split entries
    if orig_cmt and orig_cmt in opt_index['split_by_base']:
        subs = opt_index['split_by_base'][orig_cmt]
        for entry, subtype in subs:
            result['targets'].append({'entry': entry, 'role': subtype})

        has_dyn = any(s[1] == 'split-dynamic' for s in subs)
        has_sta = any(s[1] == 'split-static' for s in subs)

        if has_dyn and not has_sta:
            mg = _find_static_part_in_merged(orig_content, orig_cmt, opt_index['merged_groups'])
            if mg:
                result['targets'].append({'entry': mg, 'role': 'merged'})

        result['type'] = 'split'
        return result

    # 2) Comment-match in normal entries
    if orig_cmt:
        for ne in opt_index['normal']:
            if ne.get('comment', '') == orig_cmt:
                result['targets'].append({'entry': ne, 'role': 'kept'})
                result['type'] = 'kept'
                return result

    # 3) Content substring match in merged groups
    oc = orig_content.strip()
    if oc:
        for mg in opt_index['merged_groups']:
            if oc in mg.get('content', ''):
                result['targets'].append({'entry': mg, 'role': 'merged'})
                result['type'] = 'merged'
                return result

    # 3b) Empty/short content: match by position + comment in merged groups
    if not oc:
        orig_pos = orig.get('position')
        for mg in opt_index['merged_groups']:
            if mg.get('position') == orig_pos:
                result['targets'].append({'entry': mg, 'role': 'merged'})
                result['type'] = 'merged'
                return result

    # 4) Content match in normal entries
    if oc:
        for ne in opt_index['normal']:
            if ne.get('content', '').strip() == oc:
                result['targets'].append({'entry': ne, 'role': 'kept'})
                result['type'] = 'kept'
                return result

    return result


def _find_sources_for_opt(opt: dict, orig_entries: list[dict], opt_index: dict) -> list[dict]:
    cmt = opt.get('comment', '')

    if is_split_static(opt) or is_split_dynamic(opt):
        base = strip_comment_suffix(cmt)
        return [oe for oe in orig_entries if strip_comment_suffix(oe.get('comment', '')) == base]

    if is_merged_group(opt):
        mg_content = opt.get('content', '')
        sources = []
        for oe in orig_entries:
            oc = oe.get('content', '').strip()
            if oc and oc in mg_content:
                sources.append(oe)
        if len(sources) > 1:
            def sort_key(e):
                needle = e.get('content', '').strip()
                return mg_content.index(needle) if needle in mg_content else 999999
            sources.sort(key=sort_key)
        return sources

    if is_boundary_copy(opt) or is_supplement(opt):
        return []

    for oe in orig_entries:
        m = _match_original_to_opt(oe, opt_index)
        for t in m['targets']:
            if t['entry'].get('uid') == opt.get('uid'):
                return [oe]
    return []


def _filter_entries(entries: list[dict], uids: list[int] | None, search: str | None) -> list[dict]:
    result = list(entries)
    if uids:
        uid_set = set(uids)
        result = [e for e in result if e.get('uid') in uid_set]
    if search:
        sl = search.lower()
        result = [
            e for e in result
            if sl in e.get('comment', '').lower() or sl in e.get('content', '').lower()
        ]
    return result


def _fmt_header(a: str, b: str) -> list[str]:
    return [
        '═' * 70,
        f'  Diff: {Path(a).name} → {Path(b).name}',
        '═' * 70,
    ]


def _fmt_entry_header(e: dict) -> list[str]:
    return [
        f'  ┌─ {e.get("comment","(unnamed)")}',
        f'  │  uid={e["uid"]}  order={e.get("order")}  pos={e.get("position")}  '
        f'depth={e.get("depth","")}  const={"✓" if e.get("constant") else "✗"}  '
        f'sorted=#{e.get("_sorted_pos","?")}',
    ]


def _grp_targets_by_role(match: dict) -> dict:
    groups = defaultdict(list)
    for t in match['targets']:
        groups[t['role']].append(t['entry'])
    return dict(groups)


def _fmt_one_line(orig_e: dict, match: dict, idx: int) -> list[str]:
    """Format one original entry and its destination into compact lines."""
    lines = []
    sp = orig_e.get('_sorted_pos', '?')
    cmt = orig_e.get('comment', '(unnamed)')
    uid = orig_e['uid']
    order = orig_e.get('order', 0)
    pos = orig_e.get('position', 0)
    const = '✓' if orig_e.get('constant') else '✗'
    lines.append(f'  #{sp:<4} {cmt:<40} uid={uid:<3} order={order:<3} pos={pos}  const={const}')

    targets = match.get('targets', [])
    if match['type'] == 'split':
        for t in targets:
            te = t['entry']
            role_label = {'split-dynamic': '拆分→[动态]', 'split-static': '拆分→[静态]',
                          'merged': '拆分→[静态已合并]'}.get(t['role'], t['role'])
            extra = f'  "{te.get("comment","")}"' if te.get('comment') else ''
            lines.append(f'         └─ {role_label}  uid={te["uid"]}  order={te.get("order")}  '
                         f'pos={te.get("position")}  sorted=#{te.get("_sorted_pos","?")}{extra}')
    elif match['type'] == 'merged':
        for t in targets:
            te = t['entry']
            lines.append(f'         → 合并入  uid={te["uid"]}  order={te.get("order")}  '
                         f'pos={te.get("position")}  sorted=#{te.get("_sorted_pos","?")}'
                         f'  "{te.get("comment","")}"')
    elif match['type'] == 'kept':
        te = targets[0]['entry']
        old_ord = orig_e.get('order', 0)
        new_ord = te.get('order', 0)
        old_sp = orig_e.get('_sorted_pos', '?')
        new_sp = te.get('_sorted_pos', '?')
        changes = []
        for f in ('position', 'constant', 'useProbability', 'depth', 'role'):
            ov = orig_e.get(f)
            nv = te.get(f)
            if ov != nv:
                changes.append(f'{f}: {ov} → {nv}')
        if old_ord != new_ord:
            changes.append(f'order: {old_ord} → {new_ord}')
        line = f'         → 保持  uid={te["uid"]}  sorted: #{old_sp} → #{new_sp}'
        if changes:
            line += '  |  ' + '; '.join(changes[:3])
        lines.append(line)
    elif match['type'] == 'unknown':
        lines.append(f'         → ? 未知去向')
    else:
        lines.append(f'         → (无变化)')

    return lines


def _format_full_diff(orig_entries, opt_entries, opt_index, orig_data, orig_path, opt_path) -> str:
    lines = []
    lines.extend(_fmt_header(orig_path, opt_path))
    lines.append(f'\n  {len(orig_entries)} 条原始条目, 按 6 键排序\n')

    # Counts for summary
    n_split = n_merged = n_kept = n_unknown = 0
    sub_count = 0
    merge_targets = set()

    for i, orig_e in enumerate(orig_entries):
        match = _match_original_to_opt(orig_e, opt_index)
        lines.extend(_fmt_one_line(orig_e, match, i))

        if match['type'] == 'split':
            n_split += 1
            sub_count += len(match['targets'])
        elif match['type'] == 'merged':
            n_merged += 1
            for t in match['targets']:
                merge_targets.add(t['entry']['uid'])
        elif match['type'] == 'kept':
            n_kept += 1
        elif match['type'] == 'unknown':
            n_unknown += 1

    # Created entries at the end
    if opt_index['created']:
        bc = [e for e in opt_index['created'] if is_boundary_copy(e)]
        sp = [e for e in opt_index['created'] if is_supplement(e)]
        lines.append('')
        if bc:
            lines.append(f'  ── 边界副本 ({len(bc)} 条, 管线自动生成) ──')
            for e in bc:
                lines.append(f'    → {entry_short(e)}')
            lines.append('')
        if sp:
            lines.append(f'  ── 补充包裹 ({len(sp)} 条, 管线自动生成) ──')
            for e in sp:
                lines.append(f'    → {entry_short(e)}')
            lines.append('')

    # Summary
    total_created = len(opt_index['created'])
    lines.append(f'\n  ── 汇总 ──')
    lines.append(f'  拆分: {n_split} 条 → {sub_count} 子条')
    lines.append(f'  合并: {n_merged} 条 → {len(merge_targets)} 组')
    lines.append(f'  保持: {n_kept} 条')
    lines.append(f'  新建: {total_created} 条')
    if n_unknown:
        lines.append(f'  未知: {n_unknown} 条')
    if 'originalData' in orig_data:
        lines.append(f'\n  originalData: (已移除)')
    lines.append('\n' + '═' * 70)
    return '\n'.join(lines)


def _format_forward_tracking(orig_filtered, opt_index, orig_path, opt_path) -> str:
    lines = []
    lines.extend(_fmt_header(orig_path, opt_path))
    lines.append(f'\n  向前追踪: {len(orig_filtered)} 条原始条目\n')

    if not orig_filtered:
        lines.append('  (无匹配条目)\n')
        lines.append('═' * 70)
        return '\n'.join(lines)

    for orig_e in orig_filtered:
        match = _match_original_to_opt(orig_e, opt_index)

        lines.append('  ' + '─' * 60)
        lines.extend(_fmt_entry_header(orig_e))
        type_label = {'split': '拆分', 'merged': '合并', 'kept': '保持', 'unknown': '未知'}.get(match['type'], match['type'])
        lines.append(f'  │  → {type_label}')

        by_role = _grp_targets_by_role(match)
        for role in ('split-static', 'split-dynamic', 'merged', 'kept'):
            if role not in by_role:
                continue
            rlabel = {'split-static': '[静态部分]', 'split-dynamic': '[动态部分]',
                       'merged': '[合并入]', 'kept': '[保持]'}[role]
            for te in by_role[role]:
                lines.append(f'  │')
                lines.append(f'  ├─ {rlabel}')
                lines.append(f'  │    uid={te["uid"]}  order={te.get("order")}  pos={te.get("position")}  '
                             f'depth={te.get("depth","")}  const={"✓" if te.get("constant") else "✗"}  '
                             f'sorted=#{te.get("_sorted_pos","?")}')
                if te.get('comment') and te['comment'] != orig_e.get('comment'):
                    lines.append(f'  │    comment: {te["comment"][:60]}')
        lines.append('  └──\n')

    lines.append('═' * 70)
    return '\n'.join(lines)


def _format_reverse_tracking(opt_filtered, orig_entries, opt_index, orig_path, opt_path) -> str:
    lines = []
    lines.extend(_fmt_header(orig_path, opt_path))
    lines.append(f'\n  反向追踪: {len(opt_filtered)} 条优化后条目\n')

    if not opt_filtered:
        lines.append('  (无匹配条目)\n')
        lines.append('═' * 70)
        return '\n'.join(lines)

    for opt_e in opt_filtered:
        lines.append('  ' + '─' * 60)
        lines.extend(_fmt_entry_header(opt_e))

        sources = _find_sources_for_opt(opt_e, orig_entries, opt_index)

        if is_merged_group(opt_e):
            lines.append(f'  │  ← {len(sources)} 条原始条目合并而来')
        elif is_split_static(opt_e) or is_split_dynamic(opt_e):
            lines.append(f'  │  ← 拆分自原始条目')
        elif is_boundary_copy(opt_e) or is_supplement(opt_e):
            lines.append(f'  │  ← 新建（管线自动生成）')
        elif sources:
            lines.append(f'  │  ← 1 条原始条目')
        else:
            lines.append(f'  │  ← 无原始对应')

        for src in sources:
            lines.append(f'  │    ← {entry_short(src)}')
        lines.append('  └──\n')

    lines.append('═' * 70)
    return '\n'.join(lines)


def _format_json(orig_entries, opt_entries, opt_index, orig_data, orig_path, opt_path) -> str:
    matched = []
    for e in orig_entries:
        m = _match_original_to_opt(e, opt_index)
        matched.append({
            'uid': e['uid'],
            'comment': e.get('comment', ''),
            'type': m['type'],
            'targets': [{'uid': t['entry']['uid'], 'role': t['role']} for t in m['targets']],
        })

    return json.dumps({
        'original': orig_path,
        'optimized': opt_path,
        'entry_count': {'before': len(orig_entries), 'after': len(opt_entries)},
        'matches': matched,
        'created': [
            {'uid': e['uid'], 'comment': e.get('comment', ''),
             'type': 'boundary_copy' if is_boundary_copy(e) else 'supplement'}
            for e in opt_index['created']
        ],
        'removed': ['originalData'] if 'originalData' in orig_data else [],
    }, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="World book diff tool (sorted comparison with entry tracking)")
    p.add_argument("--original", required=True)
    p.add_argument("--optimized", required=True)
    p.add_argument("-f", "--format", default="unified", choices=["unified", "json"])
    p.add_argument("--output", default=None)
    p.add_argument("--max-order-changes", type=int, default=0)
    p.add_argument("--from-uid", type=int, action="append", default=None)
    p.add_argument("--from-search", default=None)
    p.add_argument("--to-uid", type=int, action="append", default=None)
    p.add_argument("--to-search", default=None)
    args = p.parse_args()
    print(run(
        args.original, args.optimized, args.format, args.output,
        args.max_order_changes, args.from_uid, args.from_search,
        args.to_uid, args.to_search,
    ))
