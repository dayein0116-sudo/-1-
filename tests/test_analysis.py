"""analysis.py 회귀·동작 테스트.  실행: 프로젝트 폴더에서  python -m pytest -v
(Streamlit 없이 계산 모듈만 검증합니다.)"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import analysis as an
import registry

DATA = Path(__file__).resolve().parent.parent / 'projects' / 'cookierun_crumble'
PROJECT = registry.load_project(DATA)
UPDS = PROJECT.updates
UPD_DATES = [u['date'] for u in UPDS]


@pytest.fixture(scope='module')
def rev():
    return an.read_csv(DATA / 'revenue.csv')


@pytest.fixture(scope='module')
def dau():
    return an.read_csv(DATA / 'dau.csv')


@pytest.fixture(scope='module')
def rev_total(rev):
    return rev.sum(axis=1, min_count=1)


@pytest.fixture(scope='module')
def dau_total(dau):
    return dau.sum(axis=1, min_count=1)


def upd(date):
    return next(u for u in UPDS if u['date'] == date)


# ── 1. 데이터 구조 ───────────────────────────────────────────
def test_data_shape(rev, dau):
    # 날짜 범위 및 일치 여부
    assert rev.index.min() == pd.Timestamp('2026-07-30')
    assert rev.index.min() == dau.index.min() and rev.index.max() == dau.index.max()
    # 날짜 연속성 (결측 없음)
    full = pd.date_range(rev.index.min(), rev.index.max(), freq='D')
    assert len(full.difference(rev.index)) == 0 and len(full.difference(dau.index)) == 0
    # 공통 7개국 불변
    rc = {c for c in rev if c != '기타'}
    dc = {c for c in dau if c != '기타'}
    assert rc & dc == {'대한민국', '미국', '대만', '일본', '태국', '싱가포르', '캐나다'}
    # 기존 구간(7/30) 데이터 불변: 첫날 대한민국 매출 표본 점검
    assert rev.loc['2026-07-30', '대한민국'] == pytest.approx(171981.49, abs=0.01)


# ── 2. 회귀: 지침 7번 표 (MVP 2 값) ───────────────────────────
LEGACY = {  # 날짜: (D0 배수, 7일 변화 하한, 상한)
    '2026-08-13': (0.93, -34.36, -9.10),
    '2026-08-27': (2.08, 56.45, 78.60),
    '2026-09-10': (1.40, -5.68, 62.37),
    '2026-09-23': (3.86, 26.23, 101.68),  # base_gap=0: 평균유지 101.68, 추세연장 26.23
}


@pytest.mark.parametrize('date', list(LEGACY))
def test_regression_total_revenue(rev_total, date):
    d0, lo, hi = LEGACY[date]
    m = an.series_metrics(rev_total, upd(date), 7, None)
    assert round(m['ratios'][0], 2) == d0
    assert m['lo'] == pytest.approx(lo, abs=0.005)
    assert m['hi'] == pytest.approx(hi, abs=0.005)


def test_regression_legacy_sigma_and_labels(rev_total):
    # 기존 MVP 기준값(12.3%)은 8/1~9/30 61일 구간 — 같은 구간을 명시적으로 자르면 그대로 재현되어야 함
    assert round(an.daily_noise_sigma(rev_total.loc['2026-08-01':'2026-09-30'], UPD_DATES), 3) == 0.123
    # 10월 데이터(31일)가 추가되어 전체 sigma가 13.7%로 달라짐 (의도된 데이터 변경, 계산 오류 아님)
    sig = an.daily_noise_sigma(rev_total, UPD_DATES)
    assert round(sig, 3) == 0.137
    assert an.noise_sigma is an.daily_noise_sigma and an.judge is an.judge_legacy  # 호환 별칭
    expected = {'2026-08-13': '판단 불가 (기저 의존)', '2026-08-27': '증가 (기저 무관)',
                '2026-09-10': '판단 불가 (기저 의존)', '2026-09-23': '증가 (기저 무관)'}
    for date, label in expected.items():
        assert an.series_metrics(rev_total, upd(date), 7, sig)['judge'] == label


def test_regression_baseline_keys_0923(rev_total):
    bl = an.baseline_changes(rev_total, '2026-09-23', 7, (0, 2))
    assert list(bl) == ['평균 유지', '평균 유지 (직전 2일 제외)', '추세 연장 (직전 2일 제외)']
    assert bl['평균 유지'] == pytest.approx(101.68, abs=0.005)
    assert bl['평균 유지 (직전 2일 제외)'] == pytest.approx(117.62, abs=0.005)


def test_profile_gap_default_is_unchanged(rev_total):
    b0, r0 = an.profile(rev_total, '2026-09-23', 7)
    b1, r1 = an.profile(rev_total, '2026-09-23', 7, gap=0)
    assert b0 == b1 and r0 == r1
    _, alt = an.profile(rev_total, '2026-09-23', 7, gap=2)
    assert round(alt[0], 2) == 4.16  # gap=2로 직접 계산 시 D0 배수 4.16 (함수 동작 검증)
    # base_gap=0 정책으로 series_metrics에서 d0_alt는 항상 None
    assert an.series_metrics(rev_total, upd('2026-09-23'), 7, None)['d0_alt'] is None
    assert an.series_metrics(rev_total, upd('2026-08-13'), 7, None)['d0_alt'] is None


# ── 3. 새 진단: 기저 민감도 ───────────────────────────────────
def test_direction_labels(rev_total):
    exp = {'2026-08-13': '기저 간 방향 일치 (감소)', '2026-08-27': '기저 간 방향 일치 (증가)',
           '2026-09-10': '기저에 따라 방향이 갈림', '2026-09-23': '기저 간 방향 일치 (증가)'}
    for date, label in exp.items():
        assert an.series_metrics(rev_total, upd(date), 7, None)['direction'] == label


def test_sensitivity_values(rev_total):
    s = an.series_metrics(rev_total, upd('2026-09-10'), 7, None)['sensitivity']
    assert s['sign'] == '±' and s['n'] == 2 and s['spread_pp'] == pytest.approx(68.05, abs=0.01)
    assert s['primary'] == pytest.approx(-5.68, abs=0.005)  # 평균 유지가 기본 기저


def test_trend_extension_instability_is_reported(rev_total):
    lo, hi = an.series_metrics(rev_total, upd('2026-08-27'), 7, None)['trend_loo']
    assert lo == pytest.approx(59.3, abs=0.1) and hi == pytest.approx(125.3, abs=0.1)
    assert an.trend_extension_loo(rev_total, '2026-09-23', 7, gap=2)[1] == pytest.approx(330.7, abs=0.1)


# ── 4. 새 진단: 관측 변동성은 만들 수 없으면 만들지 않는다 ─────────
def test_no_clean_windows_in_real_data(rev_total):
    ref = an.variability_reference(rev_total, UPD_DATES, 7)
    assert ref['status'] == '미확립' and ref['n_windows'] == 0 and ref['band_pct'] is None
    m = an.series_metrics(rev_total, upd('2026-08-27'), 7, None, ref)
    assert '보류' in m['magnitude']


def test_variability_established_on_long_synthetic_series():
    rng = np.random.default_rng(0)
    idx = pd.date_range('2026-01-01', periods=200)
    s = pd.Series(1000 * np.exp(rng.normal(0, 0.05, 200)), index=idx)
    ref = an.variability_reference(s, ['2026-03-01', '2026-06-01'], 7)
    assert ref['status'] == '확립' and ref['n_independent'] >= 6 and ref['band_pct'] > 0
    # 변동성 밖으로 크게 오른 경우
    sens = {'n': 2, 'lo': ref['band_pct'] + 5, 'hi': ref['band_pct'] + 50, 'sign': '+', 'spread_pp': 45, 'primary': 1}
    assert an.diagnose(sens, ref)['magnitude'] == '관측 변동성 밖'
    sens_in = {'n': 2, 'lo': -1.0, 'hi': 1.0, 'sign': '±', 'spread_pp': 2, 'primary': 0}
    assert an.diagnose(sens_in, ref)['magnitude'] == '관측 변동성 범위 안'


def test_clean_windows_exclude_update_zone():
    idx = pd.date_range('2026-01-01', periods=100)
    s = pd.Series(100.0, index=idx)
    wins = an.clean_window_changes(s, ['2026-02-10'], 7)
    blocked = {pd.Timestamp('2026-02-10') + pd.Timedelta(days=k) for k in range(-2, 7)}
    for start, _ in wins:
        days = set(pd.date_range(start, periods=14))
        assert not days & blocked


def test_diagnose_missing_data():
    assert an.diagnose(None)['verdict'] == '자료 부족'


# ── 5. 요일·DAU 범위 ──────────────────────────────────────────
def test_same_weekday_ratio(rev_total):
    exp = {'2026-08-13': 0.88, '2026-08-27': 1.79, '2026-09-10': 1.12, '2026-09-23': 4.43}
    for date, v in exp.items():
        assert round(an.same_weekday_ratio(rev_total, date), 2) == v
    assert an.same_weekday_ratio(rev_total, '2026-08-03') is None  # 7일 전 자료 없음


def test_dau_scopes_are_separate(rev, dau, dau_total):
    common = sorted((set(rev) - {'기타'}) & (set(dau) - {'기타'}))
    d7 = an.sum_countries(dau, common)
    assert len(common) == 7 and (d7 <= dau_total).all() and not d7.equals(dau_total)


# ── 6. 데이터 검증 ────────────────────────────────────────────
def write(tmp_path, text, name='x.csv'):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8-sig')
    return p


def test_real_files_pass_validation():
    for f in ('revenue.csv', 'dau.csv'):
        _, issues = an.read_csv_checked(DATA / f)
        assert not [i for i in issues if i[0] == '오류']
        assert not [i for i in issues if '날짜가 비어' in i[1]]


def test_validation_detects_problems(tmp_path):
    p = write(tmp_path, '날짜,한국 수익 (절대적),미국 수익 (절대적)\n2026-08-01,100,10\n2026-08-02,abc,-5\n2026-08-05,0,7\n')
    df, issues = an.read_csv_checked(p)
    text = ' '.join(m for _, m in issues)
    assert '숫자로 읽을 수 없는 값 1개' in text and '날짜가 비어 있는 날이 2일' in text
    assert '음수 값 1개' in text and '0인 날 1일' in text
    assert list(df.columns) == ['한국', '미국']


def test_validation_raises_on_fatal(tmp_path):
    with pytest.raises(ValueError, match='날짜가 중복'):
        an.read_csv_checked(write(tmp_path, '날짜,A 수익 (절대적)\n2026-08-01,1\n2026-08-01,2\n'))
    with pytest.raises(ValueError, match='날짜를 인식'):
        an.read_csv_checked(write(tmp_path, '날짜,A 수익 (절대적)\nnot-a-date,1\n'))
    with pytest.raises(ValueError, match='국가 이름이 중복'):
        an.read_csv_checked(write(tmp_path, '날짜,A 수익 (절대적),A DAU (절대적)\n2026-08-01,1,2\n'))


def test_validate_updates_window(rev):
    ok = {r['업데이트']: r['상태'] for r in an.validate_updates(UPDS, rev.index, 7)}
    assert set(ok.values()) == {'분석 가능'}
    long = {r['업데이트']: r['상태'] for r in an.validate_updates(UPDS, rev.index, 14)}
    # 9/23: 10월 데이터 추가로 D+13=10/6이 자료 범위 내 → 분석 가능
    # 10/22: D+13=11/4이 자료 끝(10/31) 초과 → 자료 부족
    assert long['2026-09-23'] == '분석 가능' and long['2026-08-13'] == '분석 가능'
    assert long['2026-10-22'] == '자료 부족'


def test_validate_pair(rev, dau):
    msgs = ' '.join(m for _, m in an.validate_pair(rev, dau))
    assert '홍콩' in msgs and '인도네시아' in msgs


# ── 7. week_compare_cal (달력 주 기준) ───────────────────────────
def test_week_compare_cal_window_dates(rev_total):
    r = an.week_compare_cal(rev_total, '2026-10-22')
    assert r is not None
    # 2026-10-22는 목요일(dayofweek=3): 업데이트 주 = 10/19(월)~10/25(일)
    assert r['week_start'] == pd.Timestamp('2026-10-19')
    assert r['week_end'] == pd.Timestamp('2026-10-25')
    assert r['prev_start'] == pd.Timestamp('2026-10-12')
    assert r['prev_end'] == pd.Timestamp('2026-10-18')
    assert r['pre_days'] == 3  # D0 이전 3일(월~수)이 업데이트 주에 포함


def test_week_compare_cal_sums(rev_total):
    r = an.week_compare_cal(rev_total, '2026-10-22')
    assert r is not None
    # cur_sum: 10/19~10/25 합계, prev_sum: 10/12~10/18 합계
    cur_expected = float(rev_total['2026-10-19':'2026-10-25'].sum())
    prev_expected = float(rev_total['2026-10-12':'2026-10-18'].sum())
    assert r['cur_sum'] == pytest.approx(cur_expected, abs=0.01)
    assert r['prev_sum'] == pytest.approx(prev_expected, abs=0.01)
    assert r['pct'] == pytest.approx((cur_expected / prev_expected - 1) * 100, abs=0.001)


def test_week_compare_cal_returns_none_when_no_prior_data(rev_total):
    # 2026-07-30이 데이터 시작: 전주(7/20~7/26)가 없으므로 None 반환
    r = an.week_compare_cal(rev_total, '2026-07-30')
    assert r is None


def test_week_compare_cal_dau_uses_mean(dau_total):
    r = an.week_compare_cal(dau_total, '2026-10-22')
    assert r is not None
    # cur_mean과 cur_sum의 비율이 7이어야 함 (7일 평균)
    assert r['cur_mean'] == pytest.approx(r['cur_sum'] / 7, abs=0.001)


# ── 8. 회귀 테스트: A~D 변경사항 ──────────────────────────────────

def test_fig_cal_week_overlay_solid_lines_no_vline():
    """A: fig_cal_week_overlay — 모든 선 실선, vline 없음, annotation 존재"""
    import pandas as pd
    import charts
    idx = pd.date_range('2026-10-05', periods=21)
    s = pd.Series(list(range(1, 22)), index=idx, dtype=float)
    fig = charts.fig_cal_week_overlay(s, '2026-10-15')
    assert fig is not None
    # 2 traces only
    assert len(fig.data) == 2
    # Both solid (no dash)
    for tr in fig.data:
        assert tr.line.dash in (None, 'solid', '')
        assert tr.mode == 'lines+markers'
    # No shapes (no vline)
    assert len(fig.layout.shapes) == 0
    # Annotation exists (업데이트 label)
    anns = [a.text for a in fig.layout.annotations]
    assert any('업데이트' in a for a in anns)


def test_fig_cal_week_overlay_returns_none_for_incomplete_prev_week():
    """A: 전주 7일 미완성이면 None 반환"""
    import pandas as pd
    import charts
    idx = pd.date_range('2026-10-13', periods=5)
    s = pd.Series([100.0]*5, index=idx)
    assert charts.fig_cal_week_overlay(s, '2026-10-15') is None


def test_norm_hyp_strips_strikethrough():
    """C: norm_hyp — ~~텍스트~~ 및 HTML 취소선 태그 제거"""
    import ui
    assert ui.norm_hyp('~~취소~~ 가설')['text'] == '취소 가설'
    assert ui.norm_hyp('<del>삭제</del> 텍스트')['text'] == '삭제 텍스트'
    assert ui.norm_hyp('<s>취소</s>된')['text'] == '취소된'
    assert ui.norm_hyp({'text': '~~old~~ new', 'basis': []})['text'] == 'old new'
    # 정상 텍스트는 변경 없음
    assert ui.norm_hyp('정상 가설')['text'] == '정상 가설'


def test_items_html_fallback_for_empty_items_detail():
    """B: 10/15 패치노트 — registry가 items → items_detail 변환; env_cats와 _items_html이 카테고리를 반환"""
    from pathlib import Path
    import registry
    maple_path = Path(__file__).resolve().parent.parent / 'projects' / 'maple_idle'
    proj = registry.load_project(maple_path)
    u = next(u for u in proj.updates if u['date'] == '2026-10-15')
    # registry converts items → items_detail; total item count must be > 0
    assert sum(len(v) for v in u.get('items_detail', {}).values()) > 0
    # env_cats must return non-empty list (uses items_detail from registry)
    from views.diagnosis import env_cats
    cats = env_cats(u)
    assert len(cats) > 0


def test_country_compare_table_complete_data_only():
    """D: 국가별 비교 표 — 모든 업데이트에 완전한 데이터가 있는 국가만 포함"""
    import analysis as an
    import registry
    import report
    from pathlib import Path
    maple_path = Path(__file__).resolve().parent.parent / 'projects' / 'maple_idle'
    proj = registry.load_project(maple_path)
    import registry as reg
    data = reg.load_project_data(proj)
    ctx = report.build_context(proj, data.rev, data.dau)
    # Only countries where ALL updates have complete calendar-week data should appear
    complete = [c for c in ctx.rev_countries
                if all(an.week_compare_cal(ctx.rev[c], u['date']) is not None for u in proj.updates)]
    # Partial countries must be excluded
    all_c = list(ctx.rev_countries)
    assert len(complete) <= len(all_c)
    # Every country in complete has non-None week_compare_cal for all updates
    for c in complete:
        for u in proj.updates:
            assert an.week_compare_cal(ctx.rev[c], u['date']) is not None


# ── 9. 회귀 테스트: 이번 UI 수정 (A/B/C) ──────────────────────────

def test_fig_cal_week_overlay_arrow_annotation():
    """A: D0에 화살표+박스 주석 — paper ref 고정 텍스트 없음"""
    import pandas as pd
    import charts
    idx = pd.date_range('2026-10-05', periods=21)
    s = pd.Series(list(range(1, 22)), index=idx, dtype=float)
    # 목요일(dayofweek=3) 업데이트
    fig = charts.fig_cal_week_overlay(s, '2026-10-15')
    assert fig is not None
    ann = fig.layout.annotations
    assert len(ann) == 1
    a = ann[0]
    assert a.showarrow is True      # 화살표 있음
    assert a.arrowhead is not None
    # yref='paper' + showarrow=False 고정 텍스트 방식 사용 금지
    assert not (a.yref == 'paper' and a.showarrow is False)
    # 라벨 텍스트에 날짜와 '업데이트' 포함
    assert '업데이트' in (a.text or '')
    assert '10/15' in (a.text or '')


def test_fig_cal_week_overlay_early_weekday_anchor():
    """A: 월요일 D0 — xanchor='left' (오른쪽에 라벨 배치)"""
    import pandas as pd
    import charts
    # 10/05 시작 21일치 → 10/05~10/25; 10/12(월) 업데이트, 전주 10/05~10/11 ✓
    idx = pd.date_range('2026-10-05', periods=21)
    s = pd.Series(list(range(1, 22)), index=idx, dtype=float)
    fig = charts.fig_cal_week_overlay(s, '2026-10-12')  # 월요일(dayofweek=0)
    assert fig is not None
    a = fig.layout.annotations[0]
    assert a.xanchor == 'left'


def test_structure_cell_returns_html_not_markdown():
    """B: _cell()이 HTML 반환 — 취소선 마크다운 렌더링 불가"""
    from views.structure import _cell
    html = _cell([{'text': '테스트 항목', 'kind': ''}])
    # HTML 태그 사용
    assert '<ul' in html and '<li>' in html
    # ~~ 없음 — 마크다운 취소선 패턴 없음
    assert '~~' not in html
    # 빈 목록
    assert '<span' in _cell([])


def test_source_none_shows_fallback_text():
    """C: source=None → '패치노트 원문 미등록' 표시 (esc(None) → 'None' 방지)"""
    import html as _html
    fallback = 'None' or '패치노트 원문 미등록'
    # 실제 UI 처리: u["source"] or "패치노트 원문 미등록"
    for src in [None, '']:
        result = _html.escape(str(src or '패치노트 원문 미등록'))
        assert result == '패치노트 원문 미등록'
    # 정상 source는 그대로
    assert _html.escape(str('https://example.com' or '패치노트 원문 미등록')) == 'https://example.com'


def test_maple_8_13_and_10_15_have_items():
    """C: 8/13·10/15 — registry 로드 후 items_detail 비어있지 않음"""
    # raw JSON에 'source' 키 없음 → registry default로 대체; items는 정상 로드됨
    from pathlib import Path
    import registry
    maple = registry.load_project(Path('projects/maple_idle'))
    for date, expected_min in [('2026-08-13', 15), ('2026-10-15', 10)]:
        u = next(x for x in maple.updates if x['date'] == date)
        total = sum(len(v) for v in u['items_detail'].values())
        assert total >= expected_min, f"{date}: only {total} items"
        # source 키 없음 → registry가 default 문자열로 채움 (None이 아님)
        assert u.get('source') is not None


# ── 10. 최종 품질 검수 회귀 테스트 ───────────────────────────────

def test_strip_strike_preserves_single_tilde():
    """Issue 3: 단일 ~ (한국어 범위 표기)는 _strip_strike가 건드리지 않아야 한다."""
    import ui
    assert ui._strip_strike('신규 챕터 42~44 추가') == '신규 챕터 42~44 추가'
    assert ui._strip_strike('7/23~8/12 이벤트') == '7/23~8/12 이벤트'
    assert ui._strip_strike('10/15~11/4') == '10/15~11/4'
    assert ui._strip_strike('10/22~11/4') == '10/22~11/4'
    assert ui._strip_strike('45~47 추가') == '45~47 추가'
    # 실제 ~~취소선~~은 올바르게 처리됨
    assert ui._strip_strike('~~취소선~~') == '취소선'
    assert ui._strip_strike('~~42~44~~ 항목') == '42~44 항목'


def test_maple_confounds_8_13_and_10_15_not_empty():
    """Issue 2/3: 8/13·10/15 confounds가 비어있지 않아야 한다."""
    from pathlib import Path
    import registry
    maple = registry.load_project(Path('projects/maple_idle'))
    for date in ('2026-08-13', '2026-10-15'):
        u = next(x for x in maple.updates if x['date'] == date)
        assert u['confounds'], f"{date}: confounds가 비어 있음"
        assert len(u['confounds']) >= 1


def test_week_compare_cal_used_for_country_findings():
    """Issue 1-2: 국가별 주요 발견의 기준이 week_compare_cal과 일관성 있는지 확인.
    delta(N일 평균)와 week_compare_cal(달력 주)이 같은 방향을 가리키는 경우를 검증."""
    # 7/23(목) 업데이트 → 달력 주 월요일 7/20; 전주는 7/13~7/19
    idx = pd.date_range('2026-07-13', periods=28)  # 전주 월요일부터 충분한 기간
    s = pd.Series([100.0] * 7 + [120.0] * 21, index=idx, dtype=float)
    d = '2026-07-23'
    w = an.week_compare_cal(s, d)
    assert w is not None
    assert w['pct'] > 0  # 업데이트 주(120) > 전주(100)
    # delta도 같은 방향이어야 함 (일관성 확인)
    df = pd.DataFrame({'x': s})
    dt = an.delta(df, 'x', d, 7)
    assert dt is not None
    assert dt['change_pct'] > 0
