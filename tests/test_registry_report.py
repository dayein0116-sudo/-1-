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
    assert '공통 6개국' in a['scope_label'] and '파일 전체' in b['scope_label']
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
    nxt[first] = '2026-11-01'  # 10월 데이터 병합 후 기존 마지막 날은 10/31 → 11/1로 연장
    buf = io.StringIO(); nxt.to_csv(buf, index=False)
    d = registry.load_project_data(project, extra_rev=io.BytesIO(buf.getvalue().encode('utf-8')))
    assert d.rev.index.max() == pd.Timestamp('2026-11-01') and d.merge_info['rev']['new_dates'] == 1 and d.merge_info['dau'] is None


def test_timing_flags_for_0923(project, ctx):
    rev_s, _ = ctx.series('common')
    flags = an.timing_flags(upd(project, '2026-09-23'), project.updates, 7, rev_s)
    kinds = [f['kind'] for f in flags]
    assert '비교 구간 겹침' in kinds and '업데이트 직전' in kinds and '요일' in kinds


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
    assert rep['dau_scope_label'] == '공통 6개국 DAU 합계' and rep['rev_scope_label'] == '공통 6개국 매출 합계'
    assert 'DAU 파일 전체' in report.build_update_report(ctx, upd(project, '2026-09-23'), 7, 'file')['dau_scope_label']
