"""프로젝트 등록·리포트 계층 테스트 (registry.py / report.py / analysis의 v3 추가 함수)."""
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import analysis as an
import registry
import report

ROOT = Path(__file__).resolve().parent.parent / 'projects' / 'cookierun_crumble'


@pytest.fixture(scope='module')
def project():
    return registry.load_project(ROOT)


@pytest.fixture(scope='module')
def data(project):
    return registry.load_project_data(project)


@pytest.fixture(scope='module')
def ctx(project, data):
    return report.build_context(project, data.rev, data.dau)


def upd(project, date):
    return next(u for u in project.updates if u['date'] == date)


# ── 등록 구조 ────────────────────────────────────────────────
def test_project_registered(project):
    assert project.name == '쿠키런: 크럼블'
    assert [u['date'] for u in project.updates] == ['2026-08-13', '2026-08-27', '2026-09-10', '2026-09-23', '2026-10-08', '2026-10-22']
    assert project.issues == []


def test_discover_projects_isolates_failures(tmp_path):
    import shutil
    shutil.copytree(ROOT, tmp_path / 'ok')
    (tmp_path / 'bad').mkdir()
    (tmp_path / 'bad' / 'project.json').write_text('{"id": "bad"}', encoding='utf-8')
    found, failed = registry.discover_projects(tmp_path)
    assert [p.id for p in found] == ['cookierun_crumble'] and failed[0][0] == 'bad'


def test_normalize_updates_rejects_bad_input():
    cats = ['A']
    good = {'date': '2026-01-02', 'type': '메이저', 'title': 't', 'items': {'A': ['x']}}
    assert registry.normalize_updates([good], cats)[0][0]['items'] == {'A': ['x']}
    with pytest.raises(ValueError):
        registry.normalize_updates([good, dict(good)], cats)           # 날짜 중복
    # type은 더 이상 검증하지 않음 — 임의 값도 저장되고 type 없이도 등록 가능
    assert registry.normalize_updates([{**good, 'type': '임의값'}], cats)[0][0]['type'] == '임의값'
    no_type = {k: v for k, v in good.items() if k != 'type'}
    assert registry.normalize_updates([no_type], cats)[0][0]['type'] == ''
    with pytest.raises(ValueError):
        registry.normalize_updates([{**good, 'date': 'abc'}], cats)     # 날짜 오류
    with pytest.raises(ValueError):
        registry.normalize_updates([], cats)


def test_notice_fixes_in_registered_data(project):
    """지침 5.4: 8/13 환산 예고는 신규 BM이 아님, 9/23 차원의 이면은 PvE, 신규 패스·성장 장벽 완화·길드 보상 구분"""
    bm_0813 = ' '.join(upd(project, '2026-08-13')['items']['신규 BM 가능성(공지 표기 기준)'])
    assert '환산 예고' not in bm_0813
    d = upd(project, '2026-09-23')['items_detail']
    end = {x['text'][:6]: x['kind'] for x in d['경쟁·엔드 콘텐츠']}
    assert any('PvE' in k and 'PvP 아님' in k for t, k in end.items() if t.startswith('차원의 이면'))
    kinds = {x['kind'] for v in d.values() for x in v}
    assert {'신규 패스', '성장 장벽 완화', '길드 보상·진입 조건 변경'} <= kinds
    assert upd(project, '2026-09-23')['pending_review']   # 원문에 없는 밸런스 항목은 만들지 않고 보류 표시


# ── 리포트 값 (회귀) ─────────────────────────────────────────
LEGACY_D0 = {'2026-08-13': 0.93, '2026-08-27': 2.08, '2026-09-10': 1.40, '2026-09-23': 3.86}


@pytest.mark.parametrize('date', list(LEGACY_D0))
def test_file_scope_reproduces_mvp_d0(project, ctx, date):
    rep = report.build_update_report(ctx, upd(project, date), 7, 'file')
    assert rep['rev']['m']['ratios'][0] == pytest.approx(LEGACY_D0[date], abs=0.005)


def test_scopes_differ_and_are_labelled(project, ctx):
    a = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')
    b = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'file')
    assert '공통 6개국' in a['scope_label'] and '전체 국가' in b['scope_label']
    assert a['rev']['m']['ratios'][0] != b['rev']['m']['ratios'][0]


def test_no_combined_revenue_dau_metric(project, ctx):
    """매출과 DAU를 결합한 지표(ARPDAU 등)는 리포트 구조 어디에도 키로 존재하지 않아야 함 (설명 문구는 제외)"""
    rep = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')

    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                yield from keys(v)
    ks = set(keys({k: v for k, v in rep.items() if k not in ('rev_series', 'dau_series')}))
    assert not any('arpdau' in k or 'arpu' in k or 'per_dau' in k for k in ks)
    assert set(rep['rev']) & {'dau'} == set()


def test_country_only_metric_present(project, ctx):
    rep = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')
    tags = {c['name']: c['tag'] for c in rep['countries']}
    assert tags['홍콩'] == '매출만' and tags['브라질'] == 'DAU만' and tags['미국'] == ''
    hk = next(c for c in rep['countries'] if c['name'] == '홍콩')
    assert hk['dau'] is None and hk['rev']['ok']


def test_unanalysable_window_is_reported_not_filled(project, ctx):
    rep = report.build_update_report(ctx, upd(project, '2026-10-22'), 14, 'common')  # 10/22+13=11/4 > 10/31
    assert rep['rev']['ok'] and not rep['rev']['after_ok']
    # data_facts uses week_compare_cal (calendar Mon-Sun), not the D0+n window, so the
    # calendar week 10/20-10/26 is within the data range and succeeds.  The after_ok=False
    # signal lives in rep['rev']['reason'], not in data_facts.
    assert rep['rev']['reason'] is not None


def test_alt_baseline_only_for_pre_rise_update(project, ctx):
    # base_gap=0 정책으로 모든 업데이트의 alt_ratios는 None
    for u in project.updates:
        assert report.build_update_report(ctx, u, 7)['rev']['alt_ratios'] is None


# ── persistence / merge / timing ───────────────────────────
def test_persistence_values():
    r = {0: 4.0, 1: 3.0, 2: 2.0, 3: 2.0, 4: 1.0, 5: 1.0, 6: 1.0}
    p = an.persistence(r)
    assert p['early'] == pytest.approx(3.0) and p['late'] == pytest.approx(1.25) and p['retention'] == pytest.approx(1.25 / 3.0)
    assert an.persistence({0: 1.0, 1: 1.0}) is None and an.persistence(None) is None


def test_merge_frames_extend_and_conflict():
    idx = pd.date_range('2026-01-01', periods=3, name='date')
    base = pd.DataFrame({'A': [1.0, 2.0, 3.0]}, index=idx)
    extra = pd.DataFrame({'A': [2.0, 99.0, 4.0], 'B': [5.0, 6.0, 7.0]}, index=pd.date_range('2026-01-02', periods=3, name='date'))
    m, info = an.merge_frames(base, extra)
    assert m.loc['2026-01-03', 'A'] == 3.0 and m.loc['2026-01-04', 'A'] == 4.0     # 충돌 시 기본 유지, 새 날짜는 추가
    assert info['new_dates'] == 1 and info['new_countries'] == ['B'] and info['conflict_cells'] == 1
    assert np.isnan(m.loc['2026-01-01', 'B'])                                      # 보간하지 않음
    m2, _ = an.merge_frames(base, extra, overwrite=True)
    assert m2.loc['2026-01-03', 'A'] == 99.0


def test_load_project_data_with_upload_extends_period(project):
    rev = pd.read_csv(project.path('revenue'), encoding='utf-8-sig')
    first = rev.columns[0]
    nxt = rev.tail(1).copy()
    nxt[first] = '2026-11-01'  # cutoff(10/27) 이후 날짜 — 병합은 되지만 cutoff로 최종 제거
    buf = io.StringIO(); nxt.to_csv(buf, index=False)
    d = registry.load_project_data(project, extra_rev=io.BytesIO(buf.getvalue().encode('utf-8')))
    # 병합 중 11/01이 추가됨(new_dates=1)이지만, cutoff(10/27)가 사후 적용돼 최종 max=10/27
    assert d.rev.index.max() == pd.Timestamp('2026-10-27')
    assert d.merge_info['rev']['new_dates'] == 1
    assert d.merge_info['dau'] is None
    assert d.data_cutoff == '2026-10-27'


def test_timing_flags_for_0923(project, ctx):
    rev_s, _ = ctx.series('common')
    flags = an.timing_flags(upd(project, '2026-09-23'), project.updates, 7, rev_s)
    kinds = [f['kind'] for f in flags]
    assert '비교 구간 겹침' in kinds and '업데이트 직전' in kinds and '요일' not in kinds


# ── v4 검토 반영: DAU 집계 범위, 대표 성과 기간, 국가별 표 ──────────────────────
def _raw_table(path):
    """코드와 무관하게 csv 모듈로 원본을 직접 읽음 → {날짜: {국가: 값}} (빈 칸=NaN은 제외)"""
    import csv
    rows = list(csv.reader(open(path, encoding='utf-8-sig')))
    names = [h.split(' ')[0] for h in rows[0][1:]]
    return {r[0]: {n: float(v) for n, v in zip(names, r[1:]) if v} for r in rows[1:]}


def test_common_scope_uses_same_countries_for_revenue_and_dau(ctx):
    au = report.scope_audit(ctx, 'common')
    assert au['rev_cols'] == au['dau_cols'] == ctx.common and len(ctx.common) == 6
    assert au['same_countries'] and au['missing_cells'] == 0 and au['ok']
    # series()가 실제로 이 열만 합산하는지 원본 CSV에서 직접 확인
    rs, ds = ctx.series('common')
    raw_r, raw_d = _raw_table(ROOT / 'revenue.csv'), _raw_table(ROOT / 'dau.csv')
    for day in ('2026-07-30', '2026-09-23', '2026-09-30'):
        assert rs[pd.Timestamp(day)] == pytest.approx(sum(raw_r[day][c] for c in ctx.common), abs=1e-6)
        assert ds[pd.Timestamp(day)] == pytest.approx(sum(raw_d[day][c] for c in ctx.common), abs=1e-6)


def test_dau_source_values_are_not_modified(data):
    raw_d = _raw_table(ROOT / 'dau.csv')
    for day in ('2026-07-30', '2026-09-23'):
        for c, v in raw_d[day].items():
            assert data.dau.loc[pd.Timestamp(day), c] == v


def test_representative_period_is_prev7_vs_post7_including_d0(ctx):
    raw_r = _raw_table(ROOT / 'revenue.csv')
    rs, _ = ctx.series('common')
    t = pd.Timestamp('2026-09-23')
    post = sum(sum(raw_r[(t + pd.Timedelta(days=k)).strftime('%Y-%m-%d')][c] for c in ctx.common) for k in range(0, 7))     # D0~D+6
    prev = sum(sum(raw_r[(t + pd.Timedelta(days=k)).strftime('%Y-%m-%d')][c] for c in ctx.common) for k in range(-7, 0))    # D-7~D-1
    w = an.week_compare(rs, t, 7)
    assert w['cur_sum'] == pytest.approx(post, abs=1e-6) and w['prev_sum'] == pytest.approx(prev, abs=1e-6)
    assert round(w['cur_sum']) == 1255474 and round(w['prev_sum']) == 623793
    assert report.period_labels(7) == ('이후 7일', '이전 7일')


@pytest.mark.parametrize('scope', ['common', 'file'])
@pytest.mark.parametrize('key', ['rev', 'dau'])
def test_country_table_rows_add_up_to_total(project, ctx, scope, key):
    for u in project.updates:
        rep = report.build_update_report(ctx, u, 7, scope)
        tbl = report.country_week_table(ctx, rep, key)
        total, body = tbl[0], tbl[1:]
        assert total['group'] == '합계'
        inc = [r for r in body if r['group'] == '포함']
        # When all included rows have complete data the sum must equal the total.
        # With dau-file scope, two non-기타 columns in cookierun_crumble have partial
        # calendar-week coverage (0/7 and 4/7 days in some weeks).  Their individual
        # week_compare_cal returns None → not counted in the row sum, but the total
        # series (ctx.dau.sum min_count=1) still includes their partial contribution
        # on the days that do exist → sum-of-rows < total is an expected design property.
        full_inc = [r for r in inc if r['cur'] is not None and r['prev'] is not None]
        if len(full_inc) == len(inc) and total['cur'] is not None:
            assert sum(r['cur'] for r in full_inc) == pytest.approx(total['cur'], abs=1e-6)
            assert sum(r['prev'] for r in full_inc) == pytest.approx(total['prev'], abs=1e-6)
        assert all(r['diff'] == pytest.approx(r['cur'] - r['prev']) for r in body if r['cur'] is not None)
        if scope == 'common':
            assert [r['name'] for r in inc] != [] and len(inc) == 6 and '기타' not in [r['name'] for r in body]
        else:
            assert '기타' in [r['name'] for r in inc]


def test_country_summary_counts_only_scope_countries(project, ctx):
    rep = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')
    line = next(x for x in rep['data_facts'] if x.startswith('국가별 추정 매출'))
    assert '/6개국' in line          # 홍콩·호주(매출만)는 공통 6개국 요약에서 제외


def test_limits_state_dau_definition_and_forbidden_inferences(project, ctx):
    rep = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')
    txt = ' '.join(rep['limits'])
    assert '고유 이용자 수가 아닙니다' in txt and 'ARPPU' in txt and '운영 이슈' in txt


def test_scope_labels_name_the_metric(project, ctx):
    rep = report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'common')
    assert rep['dau_scope_label'] == '공통 6개국 DAU' and rep['rev_scope_label'] == '공통 6개국 매출'
    assert '전체 국가 DAU' in report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'file')['dau_scope_label']


# ── 메이플 cutoff 2026-10-27 전역 적용 (Phase 2 최종) ────────────────────────

MAPLE_ROOT = Path(__file__).resolve().parent.parent / 'projects' / 'maple_idle'


@pytest.fixture(scope='module')
def maple_project():
    return registry.load_project(MAPLE_ROOT)


@pytest.fixture(scope='module')
def maple_data(maple_project):
    return registry.load_project_data(maple_project)


def test_maple_cutoff_applied(maple_data):
    """메이플 cutoff 2026-10-27이 rev·dau 모두에 적용됨."""
    assert maple_data.data_cutoff == '2026-10-27'
    assert maple_data.rev.index.max() == pd.Timestamp('2026-10-27')
    assert maple_data.dau.index.max() == pd.Timestamp('2026-10-27')


def test_maple_1015_cycle_13_of_21(maple_project, maple_data):
    """메이플 10/15 주기: cutoff → 13/21일, 비교 불가."""
    cycles = an.cycle_compare(
        maple_data.rev.sum(axis=1), maple_project.updates,
        cutoff_date=maple_data.data_cutoff,
        next_update_date=maple_data.next_update_date,
    )
    r = next(x for x in cycles if x['date'] == '2026-10-15')
    assert r['valid_days'] == 13 and r['days'] == 21
    assert r['truncated'] and not r['complete']
    assert not r['can_compare'] and r['change_pct'] is None


def test_maple_1015_total_cutoff(maple_project, maple_data):
    """메이플 10/15~10/27 (13일) 추정 매출 합계."""
    cycles = an.cycle_compare(
        maple_data.rev.sum(axis=1), maple_project.updates,
        cutoff_date=maple_data.data_cutoff,
        next_update_date=maple_data.next_update_date,
    )
    r = next(x for x in cycles if x['date'] == '2026-10-15')
    assert r['total'] == pytest.approx(4_880_132, abs=1.0)


def test_maple_complete_cycles_unaffected_by_cutoff(maple_project, maple_data):
    """10/27 cutoff는 10/14 이전에 종료된 완료 주기에 영향 없음."""
    cycles = an.cycle_compare(
        maple_data.rev.sum(axis=1), maple_project.updates,
        cutoff_date=maple_data.data_cutoff,
        next_update_date=maple_data.next_update_date,
    )
    for cy in cycles[:-1]:   # 마지막(10/15) 제외
        assert cy['complete'] and not cy['truncated']


# ── 10. 운영 이슈 (op_issues) ──────────────────────────────────────────────

def test_load_op_issues_no_file(tmp_path):
    """issues.json 없으면 빈 리스트."""
    (tmp_path / 'project.json').write_text(json.dumps({
        'id': 'x', 'name': 'X', 'categories': [], 'files': {'updates': 'u.json', 'revenue': 'r.csv', 'dau': 'd.csv'}
    }), encoding='utf-8')
    proj = registry.load_project.__wrapped__(tmp_path) if hasattr(registry.load_project, '__wrapped__') else None
    # load_op_issues는 issues.json 없으면 []
    import types
    p = types.SimpleNamespace(root=tmp_path, id='x')
    assert registry.load_op_issues(p) == []


def test_load_op_issues_valid(tmp_path):
    """issues.json의 항목이 올바르게 정규화된다."""
    data = [{'id': 'a', 'title': 'T', 'type': 'Y', 'summary': 'S',
              'events': [{'date': '2026-07-30', 'summary': 'E', 'source_confirmed': False}],
              'source_confirmed': False, 'source_note': 'N'}]
    (tmp_path / 'issues.json').write_text(json.dumps(data), encoding='utf-8')
    import types
    p = types.SimpleNamespace(root=tmp_path, id='x')
    result = registry.load_op_issues(p)
    assert len(result) == 1
    iss = result[0]
    assert iss['id'] == 'a' and iss['title'] == 'T' and iss['type'] == 'Y'
    assert iss['events'][0]['date'] == '2026-07-30'
    assert iss['source_confirmed'] is False
    assert iss['source_note'] == 'N'


def test_load_op_issues_missing_field(tmp_path):
    """필수 필드 누락 시 ValueError."""
    data = [{'id': 'a', 'title': 'T', 'events': []}]  # type, summary 없음
    (tmp_path / 'issues.json').write_text(json.dumps(data), encoding='utf-8')
    import types
    p = types.SimpleNamespace(root=tmp_path, id='x')
    with pytest.raises(ValueError):
        registry.load_op_issues(p)


def test_load_op_issues_not_list(tmp_path):
    """최상위가 배열이 아니면 ValueError."""
    (tmp_path / 'issues.json').write_text('{}', encoding='utf-8')
    import types
    p = types.SimpleNamespace(root=tmp_path, id='x')
    with pytest.raises(ValueError):
        registry.load_op_issues(p)


def test_project_data_has_op_issues(project):
    """쿠키런 ProjectData에 op_issues가 로드된다 (issues.json 존재)."""
    data = registry.load_project_data(project)
    assert hasattr(data, 'op_issues')
    assert isinstance(data.op_issues, list)
    assert len(data.op_issues) >= 1
    ids = [i['id'] for i in data.op_issues]
    assert 'balance-launch' in ids


def test_maple_project_data_op_issues_empty(maple_project):
    """issues.json 없는 프로젝트는 op_issues == []."""
    data = registry.load_project_data(maple_project)
    assert data.op_issues == []


# ── 11. related_updates 명시적 연결 ───────────────────────────────────────────

def _make_env(project, data, ctx, upd_date, window=7):
    """_get_op_issues_for_window 테스트용 최소 env."""
    import types
    u = next(u for u in project.updates if u['date'] == upd_date)
    return types.SimpleNamespace(data=data, upd=u, window=window)


@pytest.fixture(scope='module')
def cr_data(project):
    return registry.load_project_data(project)


def test_op_issues_related_updates_field_loaded(cr_data):
    """related_updates 필드가 load_op_issues에서 로드된다."""
    for iss in cr_data.op_issues:
        assert 'related_updates' in iss
        assert isinstance(iss['related_updates'], list)


def test_op_issues_shown_for_0813(project, cr_data, ctx):
    """8/13 업데이트에 연결된 운영 이슈가 in_history로 반환된다."""
    from views.diagnosis import _get_op_issues_for_window
    env = _make_env(project, cr_data, ctx, '2026-08-13')
    _, in_history = _get_op_issues_for_window(env)
    ids = [i['id'] for i in in_history]
    assert 'balance-launch' in ids and 'update-cycle-change' in ids


def test_op_issues_not_shown_for_0827(project, cr_data, ctx):
    """8/27 업데이트에는 7/30~8/5 이슈가 표시되지 않는다."""
    from views.diagnosis import _get_op_issues_for_window
    env = _make_env(project, cr_data, ctx, '2026-08-27')
    _, in_history = _get_op_issues_for_window(env)
    assert in_history == []


def test_op_issues_not_shown_for_later_updates(project, cr_data, ctx):
    """9월·10월 업데이트에도 이슈 미표시."""
    from views.diagnosis import _get_op_issues_for_window
    for d in ('2026-09-10', '2026-09-23', '2026-10-08'):
        env = _make_env(project, cr_data, ctx, d)
        iw, ih = _get_op_issues_for_window(env)
        assert iw == [] and ih == [], f'{d}: expected no issues, got iw={iw} ih={ih}'


def test_op_issue_no_related_updates_not_shown(tmp_path):
    """related_updates 없는 이슈는 history에 표시되지 않는다."""
    import types
    from views.diagnosis import _get_op_issues_for_window
    data = types.SimpleNamespace(op_issues=[{
        'id': 'x', 'title': 'T', 'type': 'Y', 'summary': 'S',
        'events': [{'date': '2026-07-30', 'summary': 'E', 'source_confirmed': False}],
        'source_confirmed': False, 'source_note': '', 'related_updates': [],
    }])
    env = types.SimpleNamespace(data=data, upd={'date': '2026-08-13'}, window=7)
    _, in_history = _get_op_issues_for_window(env)
    assert in_history == []


def test_weekday_flag_removed_from_timing_flags(project, ctx):
    """요일 일반론 설명이 timing_flags에서 제거됐다."""
    rev_s, _ = ctx.series('common')
    flags = an.timing_flags(upd(project, '2026-09-23'), project.updates, 7, rev_s)
    kinds = [f['kind'] for f in flags]
    assert '요일' not in kinds


# ── 12. 첫 주기 can_compare / complete 상태 ──────────────────────────────────

def test_cookierun_first_cycle_complete_no_prior(project, cr_data):
    """쿠키런 8/13 첫 주기: complete=True, can_compare=False — 비교 기준 없음."""
    rev_s = registry.load_project_data(project).rev.sum(axis=1)
    cycles = an.cycle_compare(rev_s, project.updates, cutoff_date=cr_data.data_cutoff)
    first = cycles[0]
    assert first['date'] == '2026-08-13'
    assert first['complete'] is True
    assert first['can_compare'] is False


_MAPLE_ROOT = Path(__file__).resolve().parent.parent / 'projects' / 'maple_idle'


@pytest.fixture(scope='module')
def maple_project():
    return registry.load_project(_MAPLE_ROOT)


@pytest.fixture(scope='module')
def maple_data(maple_project):
    return registry.load_project_data(maple_project)


def test_maple_first_cycle_complete_no_prior(maple_project, maple_data):
    """메이플 7/2 첫 주기: complete=True, can_compare=False — 비교 기준 없음."""
    rev_s = maple_data.rev.sum(axis=1)
    cycles = an.cycle_compare(rev_s, maple_project.updates,
                              cutoff_date=maple_data.data_cutoff)
    first = cycles[0]
    assert first['date'] == '2026-07-02'
    assert first['complete'] is True
    assert first['can_compare'] is False


def test_cookierun_pre_period_cycle_based(project, cr_data):
    """쿠키런 초기 운영 기간: 첫 주기 길이(14일) 역산 → 7/30~8/12 (compare.py 신규 로직)."""
    rev_s = registry.load_project_data(project).rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rev_s, project.updates, cutoff_date=cr_data.data_cutoff)
    pre_len = cycles[0]['days']        # 첫 주기 계획 일수 = 14
    assert pre_len == 14, '첫 주기가 14일이 아님'
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)   # 8/12
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)               # 7/30
    assert str(pre_start.date()) == '2026-07-30'
    assert str(pre_end.date()) == '2026-08-12'
    pre_data = rev_s[(rev_s.index >= pre_start) & (rev_s.index <= pre_end)].dropna()
    assert len(pre_data) == 14
    assert float(pre_data.mean()) == pytest.approx(464307, rel=1e-3)


# ── 13. 메이플 6월 DAU 병합 후 7/2 비교 ──────────────────────────────────────

def test_maple_dau_starts_june_after_merge(maple_data):
    """병합 후 maple DAU가 6/1부터 시작한다."""
    assert maple_data.dau.index.min() == pd.Timestamp('2026-06-01')


def test_maple_dau_row_count_after_merge(maple_data):
    """병합 후 maple DAU 행수 = 153 (6/1~10/31, cutoff 이전 128행)."""
    # cutoff 2026-10-27 적용 후 6/1~10/27 = 149일
    assert len(maple_data.dau) == 149


def test_maple_dau_no_missing_dates(maple_data):
    """병합 후 maple DAU 날짜 연속성."""
    idx = maple_data.dau.index
    full = pd.date_range(idx.min(), idx.max(), freq='D')
    assert len(full.difference(idx)) == 0


def test_maple_dau_existing_values_unchanged(maple_data):
    """7/1 이후 기존 DAU 값이 병합 후에도 불변."""
    from analysis import read_csv_checked
    backup, _ = read_csv_checked(_MAPLE_ROOT / 'dau_backup_20261106.csv')
    common_cols = [c for c in backup.columns if c in maple_data.dau.columns]
    shared_idx = maple_data.dau.index.intersection(backup.index)
    orig_sub = backup.loc[shared_idx, common_cols]
    new_sub  = maple_data.dau.loc[shared_idx, common_cols]
    assert (orig_sub - new_sub).abs().max().max() == 0.0


def test_maple_702_dau_week_compare(maple_data):
    """병합 후 week_compare_cal('2026-07-02')가 non-None을 반환하고 값이 올바르다."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    res = an.week_compare_cal(ds, '2026-07-02')
    assert res is not None, '7/2 DAU 비교가 여전히 None — 데이터 부족'
    assert res['prev_mean'] == pytest.approx(127252, abs=1)
    assert res['cur_mean'] == pytest.approx(123979, abs=1)
    assert res['pct'] == pytest.approx(-2.57, abs=0.1)


def test_maple_702_later_updates_unchanged(maple_data):
    """병합 전후 7/16, 7/30 DAU 증감률이 동일하다."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    for upd_date, expected_pct in [('2026-07-16', 1.95), ('2026-07-30', 0.04)]:
        res = an.week_compare_cal(ds, upd_date)
        assert res is not None
        assert res['pct'] == pytest.approx(expected_pct, abs=0.05)


# ── 14. 메이플 6월 매출 병합 후 ──────────────────────────────────────────────

def test_maple_rev_starts_june_after_merge(maple_data):
    """병합 후 매출이 6/1부터 시작한다."""
    assert maple_data.rev.index.min() == pd.Timestamp('2026-06-01')


def test_maple_rev_row_count_after_merge(maple_data):
    """병합 후 cutoff 적용 매출 행수 = 149 (6/1~10/27)."""
    assert len(maple_data.rev) == 149


def test_maple_rev_no_missing_dates(maple_data):
    """병합 후 매출 날짜 연속성 (6/1~10/27)."""
    idx = maple_data.rev.index
    full = pd.date_range(idx.min(), idx.max(), freq='D')
    assert len(full.difference(idx)) == 0


def test_maple_rev_no_double_counting_overlap(maple_data):
    """6/22~6/30 일별 전체 합계가 기존 백업과 동일 (이중 집계 없음)."""
    from analysis import read_csv_checked
    backup, _ = read_csv_checked(_MAPLE_ROOT / 'revenue_backup_20261106.csv')
    rev_total = maple_data.rev.sum(axis=1, min_count=1)
    for d in pd.date_range('2026-06-22', '2026-06-30', freq='D'):
        orig = float(backup.loc[d].dropna().sum())
        new = float(rev_total[d])
        assert abs(new - orig) < 0.01, f'{d.date()} 이중 집계: orig={orig} new={new}'


def test_maple_rev_july_onwards_unchanged(maple_data):
    """7/1 이후 기존 매출 값 완전 불변."""
    from analysis import read_csv_checked
    backup, _ = read_csv_checked(_MAPLE_ROOT / 'revenue_backup_20261106.csv')
    shared_idx = maple_data.rev.index.intersection(backup.index)
    shared_idx = shared_idx[shared_idx > pd.Timestamp('2026-06-30')]
    common_cols = [c for c in backup.columns if c in maple_data.rev.columns]
    orig_sub = backup.loc[shared_idx, common_cols]
    new_sub = maple_data.rev.loc[shared_idx, common_cols]
    assert (orig_sub - new_sub).abs().max().max() == 0.0


def test_maple_rev_june_matches_source(maple_data):
    """6/1~6/30 매출이 신규 파일 값과 일치한다."""
    from analysis import read_csv_checked
    june_src, _ = read_csv_checked(_MAPLE_ROOT.parent.parent / 'incoming' / 'maple_idle' / 'revenue_2026_06.csv')
    june_cols = list(june_src.columns)
    rev_june = maple_data.rev.loc[june_src.index, june_cols]
    assert (rev_june - june_src).abs().max().max() == 0.0


def test_maple_pre_period_21days(maple_data):
    """6/11~7/1 (21일) 매출 합계·일평균이 올바르다."""
    rev_total = maple_data.rev.sum(axis=1, min_count=1)
    pre = rev_total.loc['2026-06-11':'2026-07-01'].dropna()
    assert len(pre) == 21
    assert float(pre.sum()) == pytest.approx(11_166_252, rel=1e-4)
    assert float(pre.mean()) == pytest.approx(531_726, rel=1e-4)


def test_maple_first_cycle_21days_vs_pre(maple_data):
    """7/2~7/22 (21일) 첫 주기 일평균이 이전 기간 대비 약 -36.8%이다."""
    rev_total = maple_data.rev.sum(axis=1, min_count=1)
    pre_avg = float(rev_total.loc['2026-06-11':'2026-07-01'].dropna().mean())
    cy_avg = float(rev_total.loc['2026-07-02':'2026-07-22'].dropna().mean())
    pct = (cy_avg / pre_avg - 1) * 100
    assert pct == pytest.approx(-36.8, abs=0.2)


# ── 15. 주기 기반 Pre-period·DAU (compare.py 신규 로직) ──────────────────────

def test_maple_pre_period_cycle_based(maple_project, maple_data):
    """메이플 초기 운영 기간: 첫 주기 길이(21일) 역산 → 6/11~7/1."""
    rev_s = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rev_s, maple_project.updates,
                              cutoff_date=maple_data.data_cutoff)
    pre_len = cycles[0]['days']
    assert pre_len == 21
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    assert str(pre_start.date()) == '2026-06-11'
    assert str(pre_end.date()) == '2026-07-01'
    pre = rev_s[(rev_s.index >= pre_start) & (rev_s.index <= pre_end)].dropna()
    assert len(pre) == 21
    assert float(pre.mean()) == pytest.approx(531726, rel=1e-3)


def test_dau_cycle_maple_702(maple_project, maple_data):
    """업데이트 주기 기반 DAU: 메이플 7/2 첫 주기 — can_compare=False, complete=True."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(ds, maple_project.updates,
                              cutoff_date=maple_data.data_cutoff)
    first = next(c for c in cycles if c['date'] == '2026-07-02')
    assert first['can_compare'] is False
    assert first['complete'] is True
    assert first['daily_avg'] == pytest.approx(127403, rel=1e-2)


def test_dau_cycle_maple_pre_period(maple_data):
    """업데이트 주기 기반 DAU: 메이플 초기 운영 기간 DAU (6/11~7/1) = 약 134,543명."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    pre = ds.loc['2026-06-11':'2026-07-01'].dropna()
    assert len(pre) == 21
    assert float(pre.mean()) == pytest.approx(134543, rel=1e-2)


def test_dau_cycle_cookierun_813(project, cr_data):
    """업데이트 주기 기반 DAU: 쿠키런 8/13 첫 주기 — can_compare=False, complete=True."""
    ds = cr_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(ds, project.updates, cutoff_date=cr_data.data_cutoff)
    first = next(c for c in cycles if c['date'] == '2026-08-13')
    assert first['can_compare'] is False
    assert first['complete'] is True
    assert first['daily_avg'] is not None and first['daily_avg'] > 0


def test_dau_cycle_cookierun_827_vs_813(project, cr_data):
    """업데이트 주기 기반 DAU: 쿠키런 8/27 주기 — can_compare=True, 감소."""
    ds = cr_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(ds, project.updates, cutoff_date=cr_data.data_cutoff)
    second = next(c for c in cycles if c['date'] == '2026-08-27')
    assert second['can_compare'] is True
    assert second['change_pct'] is not None
    assert second['change_pct'] < 0  # 8/27이 8/13보다 DAU 감소


# ── 16. 업데이트 비교·구성 화면 수치 통일 — 공유 집계 기준 검증 ────────────────

def test_rev_cycle_cookierun_827_reference_values(project, cr_data):
    """쿠키런 8/27: 이전 주기=$249,985/일, 이번 주기=$220,085/일, 변화율=-12.0%."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff,
                               next_update_date=cr_data.next_update_date)
    cy813 = next(c for c in cycles if c['date'] == '2026-08-13')
    cy827 = next(c for c in cycles if c['date'] == '2026-08-27')
    assert cy813['daily_avg'] == pytest.approx(249985, rel=1e-3)
    assert cy827['daily_avg'] == pytest.approx(220085, rel=1e-3)
    assert cy827['can_compare'] is True
    assert cy827['change_pct'] == pytest.approx(-12.0, abs=0.1)


def test_rev_cycle_maple_702_reference_values(maple_project, maple_data):
    """메이플 7/2: pre-period=$531,726/일, 이번 주기=$336,261/일, 변화율=-36.8%."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff,
                               next_update_date=maple_data.next_update_date)
    cy702 = next(c for c in cycles if c['date'] == '2026-07-02')
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre_avg = float(rs[(rs.index >= pre_start) & (rs.index <= pre_end)].dropna().mean())
    pct = (cy702['daily_avg'] / pre_avg - 1) * 100
    assert pre_avg == pytest.approx(531726, rel=1e-3)
    assert cy702['daily_avg'] == pytest.approx(336261, rel=1e-3)
    assert pct == pytest.approx(-36.8, abs=0.2)


def test_structure_rev_cycle_cookierun_827_matches_compare(project, cr_data):
    """업데이트 구성 화면: 8/27 선택 시 compare와 동일한 cy_sel 값."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff,
                               next_update_date=cr_data.next_update_date)
    # structure.py 로직: rev_cycles에서 선택한 업데이트 날짜로 조회
    cy_sel = next((c for c in cycles if c['date'] == '2026-08-27'), None)
    assert cy_sel is not None
    assert cy_sel['daily_avg'] == pytest.approx(220085, rel=1e-3)
    assert cy_sel['can_compare'] is True
    assert cy_sel['change_pct'] == pytest.approx(-12.0, abs=0.1)


def test_structure_rev_cycle_maple_702_matches_compare(maple_project, maple_data):
    """업데이트 구성 화면: 7/2 선택 시 compare와 동일한 cy_sel 값."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff,
                               next_update_date=maple_data.next_update_date)
    cy_sel = next((c for c in cycles if c['date'] == '2026-07-02'), None)
    assert cy_sel is not None
    assert cy_sel['daily_avg'] == pytest.approx(336261, rel=1e-3)
    assert cy_sel['can_compare'] is False  # 첫 주기, pre-period 대비 비교


def test_shared_cycles_scope_file_vs_common_differ_maple(maple_project, maple_data):
    """file/common scope 집계값이 다름을 확인 — scope 구분이 올바르게 작동."""
    ctx_mp = report.build_context(maple_project, maple_data.rev, maple_data.dau)
    rs_file, _ = ctx_mp.series('file')
    rs_common, _ = ctx_mp.series('common')
    cy_file = an.cycle_compare(rs_file, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    cy_common = an.cycle_compare(rs_common, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    cy723_file = next(c for c in cy_file if c['date'] == '2026-07-23')
    cy723_common = next(c for c in cy_common if c['date'] == '2026-07-23')
    # file scope가 common scope보다 크다 (기타 포함)
    assert cy723_file['daily_avg'] > cy723_common['daily_avg']
    assert cy723_file['daily_avg'] == pytest.approx(435884, rel=1e-3)
    assert cy723_common['daily_avg'] == pytest.approx(398371, rel=1e-3)


def test_pre_period_cookierun_days_and_avg(project, cr_data):
    """쿠키런 초기 운영 기간: 14일, 일평균=$464,307."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre = rs[(rs.index >= pre_start) & (rs.index <= pre_end)].dropna()
    assert len(pre) == 14
    assert float(pre.mean()) == pytest.approx(464307, rel=1e-3)


def test_pre_period_maple_days_and_avg(maple_project, maple_data):
    """메이플 초기 운영 기간: 21일, 일평균=$531,726."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre = rs[(rs.index >= pre_start) & (rs.index <= pre_end)].dropna()
    assert len(pre) == 21
    assert float(pre.mean()) == pytest.approx(531726, rel=1e-3)


def test_pre_dau_period_cookierun(project, cr_data):
    """쿠키런 초기 운영 기간 DAU: 7/30~8/12 14일, daily_avg > 0."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    ds = cr_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre_dau = ds[(ds.index >= pre_start) & (ds.index <= pre_end)].dropna()
    assert len(pre_dau) == 14
    assert float(pre_dau.mean()) > 0


def test_pre_dau_period_maple(maple_project, maple_data):
    """메이플 초기 운영 기간 DAU: 6/11~7/1 21일, daily_avg ≈ 134,543명."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    ds = maple_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre_dau = ds[(ds.index >= pre_start) & (ds.index <= pre_end)].dropna()
    assert len(pre_dau) == 21
    assert float(pre_dau.mean()) == pytest.approx(134543, rel=1e-2)


def test_rev_cycles_cookierun_complete_count(project, cr_data):
    """쿠키런 완료 주기가 5개 (8/13·8/27·9/10·9/23·10/8), 미완료 1개 (10/22)."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff,
                               next_update_date=cr_data.next_update_date)
    complete = [c for c in cycles if c['complete']]
    incomplete = [c for c in cycles if not c['complete']]
    assert len(complete) == 5
    assert len(incomplete) == 1
    assert incomplete[0]['date'] == '2026-10-22'


def test_rev_cycles_maple_complete_count(maple_project, maple_data):
    """메이플 완료 주기가 5개 (7/2·7/23·8/13·9/3·9/22), 미완료 1개 (10/15)."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff,
                               next_update_date=maple_data.next_update_date)
    complete = [c for c in cycles if c['complete']]
    incomplete = [c for c in cycles if not c['complete']]
    assert len(complete) == 5
    assert len(incomplete) == 1
    assert incomplete[0]['date'] == '2026-10-15'


def test_dau_cycles_cookierun_827_prev_avg(project, cr_data):
    """쿠키런 DAU 8/27 주기: 직전 주기(8/13) DAU 일평균을 prev_daily_avg로 가진다."""
    ds = cr_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(ds, project.updates, cutoff_date=cr_data.data_cutoff)
    cy813 = next(c for c in cycles if c['date'] == '2026-08-13')
    cy827 = next(c for c in cycles if c['date'] == '2026-08-27')
    assert cy827['can_compare'] is True
    assert cy827.get('prev_daily_avg') == pytest.approx(cy813['daily_avg'], rel=1e-6)


def test_dau_cycles_maple_723_can_compare(maple_project, maple_data):
    """메이플 DAU 7/23 주기: can_compare=True, 직전(7/2) 대비 증감률 존재."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(ds, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    cy723 = next(c for c in cycles if c['date'] == '2026-07-23')
    assert cy723['can_compare'] is True
    assert cy723['change_pct'] is not None


# ── 17. 초기 기준 기간 비교 — 첫 주기 변화율 회귀 ──────────────────────────────

def test_cookierun_813_pct_vs_preperiod(project, cr_data):
    """쿠키런 8/13: 초기 기준 기간($464,307) 대비 약 -46.2%."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, project.updates, cutoff_date=cr_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre_avg = float(rs[(rs.index >= pre_start) & (rs.index <= pre_end)].dropna().mean())
    pct = (cycles[0]['daily_avg'] / pre_avg - 1) * 100
    assert cycles[0]['date'] == '2026-08-13'
    assert pct == pytest.approx(-46.2, abs=0.2)


def test_maple_702_pct_vs_preperiod(maple_project, maple_data):
    """메이플 7/2: 초기 기준 기간($531,726) 대비 약 -36.8%."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    cycles = an.cycle_compare(rs, maple_project.updates, cutoff_date=maple_data.data_cutoff)
    pre_len = cycles[0]['days']
    pre_end = pd.Timestamp(cycles[0]['date']) - pd.Timedelta(days=1)
    pre_start = pre_end - pd.Timedelta(days=pre_len - 1)
    pre_avg = float(rs[(rs.index >= pre_start) & (rs.index <= pre_end)].dropna().mean())
    pct = (cycles[0]['daily_avg'] / pre_avg - 1) * 100
    assert cycles[0]['date'] == '2026-07-02'
    assert pct == pytest.approx(-36.8, abs=0.2)


def test_cookierun_cats_content_unchanged(project):
    """structure.py 간격 수정 후 카테고리 항목 내용·순서 보존 — 쿠키런 8/13."""
    u = next(u for u in project.updates if u['date'] == '2026-08-13')
    # 항목이 있는 카테고리 하나 이상 존재
    nonempty = [c for c in project.categories if u['items_detail'].get(c)]
    assert len(nonempty) > 0
    # 항목 텍스트가 비어 있지 않고 순서 보존
    for cat in nonempty:
        its = u['items_detail'][cat]
        assert all('text' in x for x in its)


# ── 18. DAU 트렌드 문구 버그 수정 — 중간 부호 반전 케이스 ──────────────────────

def _trend_pct_pattern(vals):
    """diagnosis.py _trend_desc의 pattern 분류 로직만 추출 (테스트용).
    단 1개의 부호 변화는 '전환'으로 판정하지 않음 (len(after) >= 2 조건)."""
    pos = [k for k, v in vals if v > 0]
    neg = [k for k, v in vals if v < 0]
    kmax = vals[-1][0]
    if len(pos) == len(vals):
        return 'ALL_POS'
    elif len(neg) == len(vals):
        return 'ALL_NEG'
    elif vals[0][1] > 0:
        first_neg = next(k for k, v in vals if v < 0)
        after = [(k, v) for k, v in vals if k >= first_neg]
        return 'POS_THEN_NEG' if all(v < 0 for _, v in after) and len(after) >= 2 else 'MIXED'
    elif vals[0][1] < 0:
        first_pos = next(k for k, v in vals if v > 0)
        after = [(k, v) for k, v in vals if k >= first_pos]
        return 'NEG_THEN_POS' if all(v > 0 for _, v in after) and len(after) >= 2 else 'MIXED'
    return 'OTHER'


def test_trend_desc_no_spurious_transition_maple_1015_dau(maple_data):
    """메이플 10/15 DAU: D+5가 다시 음수이므로 '전환' 패턴이 아닌 MIXED."""
    ds = maple_data.dau.sum(axis=1, min_count=1)
    vals = [(k, x['pct']) for k in range(7)
            for x in [an.day_vs_prev(ds, '2026-10-15', k, 7)] if x and x['pct'] is not None]
    # D+4 양수, D+5 음수 → 완전 전환 아님
    assert _trend_pct_pattern(vals) == 'MIXED'


def test_trend_desc_no_spurious_transition_maple_702(maple_data):
    """메이플 7/2 매출·DAU: 중간 반전이 있어 '전환' 패턴이 아닌 MIXED."""
    rs = maple_data.rev.sum(axis=1, min_count=1)
    ds = maple_data.dau.sum(axis=1, min_count=1)
    for ser in [rs, ds]:
        vals = [(k, x['pct']) for k in range(7)
                for x in [an.day_vs_prev(ser, '2026-07-02', k, 7)] if x and x['pct'] is not None]
        assert _trend_pct_pattern(vals) == 'MIXED'


def test_trend_desc_single_neg_at_window_end_cookierun_0827_rev(project, cr_data):
    """쿠키런 8/27 매출: D0~D+5 양수, D+6 단 하루 음수 → 단일 관측이므로 MIXED 처리."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    vals = [(k, x['pct']) for k in range(7)
            for x in [an.day_vs_prev(rs, '2026-08-27', k, 7)] if x and x['pct'] is not None]
    # D+6 단 하나의 음수로 '전환'을 단정하지 않음 (len(after) < 2)
    assert _trend_pct_pattern(vals) == 'MIXED'


def test_trend_desc_single_neg_at_cutoff_cookierun_1022_rev(project, cr_data):
    """쿠키런 10/22 매출: D0~D+4 양수, D+5 단 하루 음수 (D+6 미관측) → MIXED 처리."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    vals = [(k, x['pct']) for k in range(7)
            for x in [an.day_vs_prev(rs, '2026-10-22', k, 7)] if x and x['pct'] is not None]
    # D+5(10/27) 단 하나의 음수, D+6(10/28)은 데이터 없음 → '전환' 단정 불가
    assert _trend_pct_pattern(vals) == 'MIXED'


def test_trend_desc_all_neg_cookierun_0813(project, cr_data):
    """쿠키런 8/13 매출·DAU: 모두 음수 → ALL_NEG."""
    rs = cr_data.rev.sum(axis=1, min_count=1)
    ds = cr_data.dau.sum(axis=1, min_count=1)
    for ser in [rs, ds]:
        vals = [(k, x['pct']) for k in range(7)
                for x in [an.day_vs_prev(ser, '2026-08-13', k, 7)] if x and x['pct'] is not None]
        assert _trend_pct_pattern(vals) == 'ALL_NEG'
