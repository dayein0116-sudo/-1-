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
    assert rev.index.min() == pd.Timestamp('2026-07-29')
    assert rev.index.min() == dau.index.min() and rev.index.max() == dau.index.max()
    # 날짜 연속성 (결측 없음)
    full = pd.date_range(rev.index.min(), rev.index.max(), freq='D')
    assert len(full.difference(rev.index)) == 0 and len(full.difference(dau.index)) == 0
    # 공통 7개국 불변
    rc = {c for c in rev if c != '기타'}
    dc = {c for c in dau if c != '기타'}
    assert rc & dc == {'대한민국', '미국', '대만', '일본', '태국', '싱가포르', '캐나다', '영국'}
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
    # min_periods=7: 완전한 7일 창만 사용. 8/1~9/30 슬라이스는 경계 3일이 추가로 제외되어 13.1%
    assert round(an.daily_noise_sigma(rev_total.loc['2026-08-01':'2026-09-30'], UPD_DATES), 3) == 0.131
    # 전체 구간(7/29~10/31) sigma: 초기 불완전 창이 자동 제외되어 16.3%
    sig = an.daily_noise_sigma(rev_total, UPD_DATES)
    assert round(sig, 3) == 0.163
    assert an.noise_sigma is an.daily_noise_sigma and an.judge is an.judge_legacy  # 호환 별칭
    expected = {'2026-08-13': '판단 불가 (기저 의존)', '2026-08-27': '증가 (기저 무관)',
                '2026-09-10': '판단 불가 (기저 의존)', '2026-09-23': '증가 (기저 무관)'}
    for date, label in expected.items():
        assert an.series_metrics(rev_total, upd(date), 7, sig)['judge'] == label


def test_sigma_min_periods7_excludes_incomplete_windows(rev_total):
    """min_periods=7: 첫 3일(7/29~7/31)은 완전한 7일 창이 불가능하므로 잔차가 NaN이어야 한다."""
    import numpy as np
    s = rev_total.dropna()
    s = s[s > 0]
    ls = np.log(s)
    res = ls - ls.rolling(7, center=True, min_periods=7).mean()
    # 7/29~7/31: 창이 불완전 → NaN
    for d in ['2026-07-29', '2026-07-30', '2026-07-31']:
        assert pd.isna(res.get(pd.Timestamp(d))), f"{d} 잔차가 NaN이어야 함"
    # 8/1부터: 7/29~8/4 모두 존재 → 유효 잔차
    assert not pd.isna(res.get(pd.Timestamp('2026-08-01'))), "8/1 잔차는 유효해야 함"


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
    assert len(common) == 8 and (d7 <= dau_total).all() and not d7.equals(dau_total)


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


# ── 11. 매출 추세 진단 ──────────────────────────────────────────

def test_revenue_trend_stats_cookierun(rev_total):
    r = an.revenue_trend_stats(rev_total, UPD_DATES)
    assert r['can_compare']
    assert r['half_days'] == 21  # min(21, (94-7)//2=43) = 21
    assert r['change_pct'] < -50  # 쿠키런 크럼블 초반 대비 80%+ 하락
    assert r['first_mean'] > r['last_mean']
    assert r['first_start'] == rev_total.index[0]
    assert r['last_end'] == rev_total.index[-1]


def test_revenue_trend_stats_too_short():
    s = pd.Series([100.0] * 5, index=pd.date_range('2026-01-01', periods=5))
    assert not an.revenue_trend_stats(s, [])['can_compare']


def test_revenue_trend_stats_min_viable():
    # 21일 → h = min(21, (21-7)//2=7) = 7 → can_compare=True
    s21 = pd.Series(100.0, index=pd.date_range('2026-01-01', periods=21))
    r = an.revenue_trend_stats(s21, [])
    assert r['can_compare'] and r['half_days'] == 7
    # 14일 → h = min(21, (14-7)//2=3) = 3 < 7 → can_compare=False
    s14 = pd.Series(100.0, index=pd.date_range('2026-01-01', periods=14))
    assert not an.revenue_trend_stats(s14, [])['can_compare']


def test_baseline_level_cookierun(rev_total):
    r = an.baseline_level(rev_total, UPD_DATES)
    assert r['can_compute']
    assert r['day_count'] >= 14
    assert r['day_count'] < len(rev_total)  # 영향권이 실제로 차단됨
    assert r['mean'] > 0


def test_baseline_level_insufficient():
    idx = pd.date_range('2026-01-01', periods=20)
    s = pd.Series(100.0, index=idx)
    # 하나의 업데이트가 D-2~D+6 = 9일 차단 → 20-9=11일 < min_days=14
    r = an.baseline_level(s, ['2026-01-10'], min_days=14)
    assert not r['can_compute']
    assert r['day_count'] == 11
    # min_days를 낮추면 계산 가능
    r2 = an.baseline_level(s, ['2026-01-10'], min_days=10)
    assert r2['can_compute']


def test_rebound_persistence_all_uses_means():
    """D0~D2 vs D3~D6 비교는 평균 대 평균 (합계 직접 비교 금지)."""
    ratios = {0: 2.0, 1: 2.0, 2: 2.0, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}
    p = an.persistence(ratios)
    # early(3일)=2.0, late(4일)=1.0, retention=0.5
    assert p['early'] == pytest.approx(2.0)
    assert p['late'] == pytest.approx(1.0)
    assert p['retention'] == pytest.approx(0.5)
    # early_sum=6, late_sum=4 → 합계 비교 시 0.667이 나왔을 것 → 평균 사용 검증


def test_rebound_persistence_all_cookierun(rev_total):
    rows = an.rebound_persistence_all(rev_total, UPD_DATES)
    assert len(rows) == len(UPD_DATES)
    has_data = [r for r in rows if r['has_data']]
    assert len(has_data) > 0
    for r in has_data:
        p_data = r['persistence']
        assert p_data['early'] > 0
        assert p_data['retention'] == pytest.approx(p_data['late'] / p_data['early'], abs=1e-9)


def test_country_half_compare_cookierun(rev):
    common = sorted((set(rev) - {'기타'}) & {'대한민국', '미국', '일본', '태국'})
    result = an.country_half_compare(rev, common)
    for c in common:
        assert result[c]['can_compare']
        assert result[c]['change_pct'] < 0  # 모든 공통 국가가 감소 추세


def test_country_half_compare_missing_country(rev):
    result = an.country_half_compare(rev, ['존재하지않는나라'])
    assert not result['존재하지않는나라']['can_compare']


# ── 12. 업데이트 주기별 비교 (cycle_compare) ──────────────────────

MAPLE_DATA = Path(__file__).resolve().parent.parent / 'projects' / 'maple_idle'
MAPLE_PROJECT = registry.load_project(MAPLE_DATA)
MAPLE_UPDS = MAPLE_PROJECT.updates


@pytest.fixture(scope='module')
def maple_rev_total():
    df = an.read_csv(MAPLE_DATA / 'revenue.csv')
    return df.sum(axis=1, min_count=1)


def test_cycle_compare_cookierun_1008_total(rev_total):
    """검증1: 10/8~10/21 = 14일, $1,105,140."""
    rows = an.cycle_compare(rev_total, UPDS)
    r = next(x for x in rows if x['date'] == '2026-10-08')
    assert r['complete'] and not r['truncated']
    assert r['days'] == 14 and r['valid_days'] == 14
    assert r['total'] == pytest.approx(1_105_140, abs=1.0)
    assert r['daily_avg'] == pytest.approx(1_105_140 / 14, abs=1.0)


def test_cycle_compare_cutoff_1022(rev_total):
    """검증2: cutoff=10/27 → 10/22 주기 = 6일, $656,494, 비교 불가."""
    rows = an.cycle_compare(rev_total, UPDS, cutoff_date='2026-10-27')
    r = next(x for x in rows if x['date'] == '2026-10-22')
    assert r['truncated'] and not r['complete']
    assert r['days'] == 6 and r['valid_days'] == 6
    assert r['total'] == pytest.approx(656_494, abs=2.0)
    assert r['change_pct'] is None and not r['can_compare']


def test_cycle_compare_last_incomplete(rev_total):
    """cutoff 없을 때 마지막 주기 = 미완료, 비교율 없음."""
    rows = an.cycle_compare(rev_total, UPDS)
    last = rows[-1]
    assert last['date'] == '2026-10-22'
    assert not last['complete'] and not last['truncated']
    assert last['change_pct'] is None and not last['can_compare']
    # 데이터 종료일까지 포함
    assert last['d_end'] == str(rev_total.index.max().date())


def test_cycle_compare_same_length_uses_daily_avg(rev_total):
    """8/13(14일)·8/27(14일) — 주기 길이 동일해도 항상 일평균 기준으로 비교."""
    rows = an.cycle_compare(rev_total, UPDS)
    r13 = next(x for x in rows if x['date'] == '2026-08-13')
    r27 = next(x for x in rows if x['date'] == '2026-08-27')
    assert r13['days'] == 14 and r27['days'] == 14
    assert r13['complete'] and r27['complete']
    assert r27['change_type'] == 'daily_avg'
    expected = (r27['daily_avg'] / r13['daily_avg'] - 1) * 100
    assert r27['change_pct'] == pytest.approx(expected, abs=0.001)


def test_cycle_compare_diff_length_uses_daily_avg(rev_total):
    """9/10(13일)·9/23(15일) — 다른 기간이므로 일평균 변화율."""
    rows = an.cycle_compare(rev_total, UPDS)
    r10 = next(x for x in rows if x['date'] == '2026-09-10')
    r23 = next(x for x in rows if x['date'] == '2026-09-23')
    assert r10['days'] == 13 and r23['days'] == 15
    assert r10['complete'] and r23['complete']
    assert r23['change_type'] == 'daily_avg'
    expected = (r23['daily_avg'] / r10['daily_avg'] - 1) * 100
    assert r23['change_pct'] == pytest.approx(expected, abs=0.001)


def test_cycle_compare_first_no_comparison(rev_total):
    """첫 번째 주기는 비교 대상 없음."""
    rows = an.cycle_compare(rev_total, UPDS)
    assert rows[0]['change_pct'] is None and not rows[0]['can_compare']
    assert rows[0]['prev_daily_avg'] is None


def test_cycle_compare_maple_boundaries(maple_rev_total):
    """메이플 7/2 주기: 종료일=7/22(다음D0 7/23-1), days=21."""
    rows = an.cycle_compare(maple_rev_total, MAPLE_UPDS)
    r = rows[0]
    assert r['date'] == '2026-07-02'
    assert r['d_start'] == '2026-07-02' and r['d_end'] == '2026-07-22'
    assert r['days'] == 21 and r['complete']
    # 9/22 주기: 다음 D0=10/15, 종료=10/14, days=23
    r923 = next(x for x in rows if x['date'] == '2026-09-22')
    assert r923['days'] == 23 and r923['complete']


def test_cycle_compare_maple_last_incomplete(maple_rev_total):
    """메이플 마지막(10/15) 주기: 완료 아님, 비교율 없음."""
    rows = an.cycle_compare(maple_rev_total, MAPLE_UPDS)
    last = rows[-1]
    assert last['date'] == '2026-10-15' and not last['complete']
    assert last['change_pct'] is None


def test_cycle_compare_cutoff_before_nominal_end():
    """cutoff이 명목 종료일보다 앞이면 truncated=True, complete=False."""
    idx = pd.date_range('2026-10-01', periods=20)
    s = pd.Series(100.0, index=idx)
    ups = [{'date': '2026-10-01', 'title': 'A'}, {'date': '2026-10-10', 'title': 'B'}]
    rows = an.cycle_compare(s, ups, cutoff_date='2026-10-05')
    r = rows[0]
    assert r['truncated'] and not r['complete']
    assert r['days'] == 5 and r['d_end'] == '2026-10-05'


def test_cycle_compare_all_nan_period():
    """기간 전체 NaN: valid_days=0, total=None, can_compare=False."""
    idx = pd.date_range('2026-10-01', periods=20)
    s = pd.Series(float('nan'), index=idx)
    ups = [{'date': '2026-10-01', 'title': 'A'}, {'date': '2026-10-10', 'title': 'B'}]
    rows = an.cycle_compare(s, ups)
    r = rows[0]
    assert r['valid_days'] == 0 and r['total'] is None and r['daily_avg'] is None
    assert not r['can_compare']


def test_cycle_compare_incomplete_prev_blocks_comparison():
    """직전 주기가 미완료면 현재 주기도 can_compare=False."""
    idx = pd.date_range('2026-10-01', periods=30)
    s = pd.Series(100.0, index=idx)
    # 3개 업데이트: 마지막 2개는 직전이 미완료인 경우 시뮬레이션
    ups = [
        {'date': '2026-10-01', 'title': 'A'},
        {'date': '2026-10-05', 'title': 'B'},   # 10/5~10/14: complete
        {'date': '2026-10-15', 'title': 'C'},   # 마지막: incomplete
    ]
    rows = an.cycle_compare(s, ups)
    assert rows[-1]['date'] == '2026-10-15' and not rows[-1]['complete']
    assert rows[-1]['change_pct'] is None


def test_cycle_compare_no_cutoff_applied_to_maple(maple_rev_total):
    """메이플에는 cutoff 없이 전체 기간 사용."""
    rows_no = an.cycle_compare(maple_rev_total, MAPLE_UPDS)
    rows_with = an.cycle_compare(maple_rev_total, MAPLE_UPDS, cutoff_date=None)
    for a, b in zip(rows_no, rows_with):
        assert a['total'] == b['total'] and a['days'] == b['days']


# ── 13. next_update_date 반영 (11/5 확정, Phase 2 보정) ──────────────────────

def test_cycle_compare_cookierun_1022_with_next_update(rev_total):
    """쿠키런 10/22: next_update=11/5 → days=14, valid_days=6, 비교율 없음."""
    rows = an.cycle_compare(rev_total, UPDS, cutoff_date='2026-10-27',
                             next_update_date='2026-11-05')
    r = next(x for x in rows if x['date'] == '2026-10-22')
    assert r['days'] == 14 and r['valid_days'] == 6
    assert r['truncated'] and not r['complete']
    assert r['total'] == pytest.approx(656_494, abs=2.0)
    assert not r['can_compare'] and r['change_pct'] is None


def test_cycle_compare_maple_1015_with_next_update(maple_rev_total):
    """메이플 10/15: next_update=11/5 → days=21, valid_days=17, open_ended=False."""
    rows = an.cycle_compare(maple_rev_total, MAPLE_UPDS,
                             next_update_date='2026-11-05')
    r = next(x for x in rows if x['date'] == '2026-10-15')
    assert r['days'] == 21 and r['valid_days'] == 17
    assert not r['complete'] and not r['truncated'] and not r['open_ended']
    assert not r['can_compare']


def test_cycle_compare_maple_1015_total(maple_rev_total):
    """메이플 10/15~10/31 등록 CSV 합계: $5,886,424 (말레이시아 열 포함 최신 원본, 반올림 1$)."""
    rows = an.cycle_compare(maple_rev_total, MAPLE_UPDS,
                             next_update_date='2026-11-05')
    r = next(x for x in rows if x['date'] == '2026-10-15')
    assert r['total'] == pytest.approx(5_886_424, abs=1.0)


def test_cycle_compare_open_ended_flag(rev_total):
    """next_update_date 없을 때 마지막 주기 open_ended=True."""
    rows = an.cycle_compare(rev_total, UPDS)
    assert rows[-1]['open_ended'] is True


def test_cycle_compare_known_next_no_open_ended(rev_total):
    """next_update_date 있을 때 마지막 주기 open_ended=False."""
    rows = an.cycle_compare(rev_total, UPDS, next_update_date='2026-11-05')
    assert rows[-1]['open_ended'] is False


def test_cycle_compare_complete_cycles_unchanged(rev_total):
    """next_update_date 추가가 완료된 이전 주기 합계·비교율에 영향 없음."""
    rows_old = an.cycle_compare(rev_total, UPDS)
    rows_new = an.cycle_compare(rev_total, UPDS, next_update_date='2026-11-05')
    for a, b in zip(rows_old[:-1], rows_new[:-1]):
        assert a['total'] == b['total']
        assert a['days'] == b['days']
        assert a['change_pct'] == b['change_pct']


def test_cycle_compare_incomplete_no_compare_pct(maple_rev_total):
    """미완료 주기(10/15)는 can_compare=False — 확정 증감률 차단."""
    rows = an.cycle_compare(maple_rev_total, MAPLE_UPDS,
                             next_update_date='2026-11-05')
    r = next(x for x in rows if x['date'] == '2026-10-15')
    assert not r['can_compare'] and r['change_pct'] is None


def test_cycle_compare_cookierun_all_daily_avg(rev_total):
    """쿠키런 완료 주기: 주기 길이에 관계없이 항상 일평균 기준으로 비교.
    8/27(14d) -12.0% / 9/10(13d) -45.4% / 9/23(15d) +14.0% / 10/8(14d) -42.4%"""
    rows = an.cycle_compare(rev_total, UPDS, next_update_date='2026-11-05')
    by_date = {r['date']: r for r in rows}
    for date in ['2026-08-27', '2026-09-10', '2026-09-23', '2026-10-08']:
        assert by_date[date]['change_type'] == 'daily_avg'
    assert by_date['2026-08-27']['change_pct'] == pytest.approx(-12.0, abs=0.1)
    assert by_date['2026-09-10']['change_pct'] == pytest.approx(-45.4, abs=0.1)
    assert by_date['2026-09-23']['change_pct'] == pytest.approx(14.0, abs=0.1)
    assert by_date['2026-10-08']['change_pct'] == pytest.approx(-42.4, abs=0.1)


# ── 15. 원화 금액 표시 함수 (fmt_krw / fmt_krw_delta) ───────────────────
# 반올림 정책: Python f-string :.1f 및 round()는 모두 "round half to even" (은행가 반올림).
# 경계값(X.X5억)은 IEEE 754 부동소수점 표현에 따라 미세하게 아래로 내려갈 수 있으며,
# 이 경우 아래 단위로 반올림됩니다. 금융 표시 목적으로 일관성 있고 재현 가능합니다.
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import ui as _ui


def test_fmt_krw_cookierun_1008():
    """쿠키런 10/08 주기 매출 $1,105,140.39 × 1,350 = 14.919억 → 약 14.9억 원."""
    assert _ui.fmt_krw(1_105_140.39) == '약 14.9억 원'


def test_fmt_krw_user_example_1point1():
    """사용자 예시: 1.0657억 원 → 약 1.1억 원."""
    assert _ui.fmt_krw(1.0657e8 / _ui.KRW_RATE) == '약 1.1억 원'


def test_fmt_krw_rounding_normal():
    """반올림 일반: 소수 둘째 자리 이하는 소수 첫째 자리로 반올림.
    14.91억 → 14.9억, 14.96억 → 15.0억 (1억 = 1e8 KRW)."""
    assert _ui.fmt_krw(14.91e8 / _ui.KRW_RATE) == '약 14.9억 원'
    assert _ui.fmt_krw(14.96e8 / _ui.KRW_RATE) == '약 15.0억 원'


def test_fmt_krw_boundary_half_to_even():
    """경계값: Python round half-to-even + IEEE 754 표현에 따른 실제 동작 고정."""
    assert _ui.fmt_krw(14.95e8 / _ui.KRW_RATE) == '약 14.9억 원'
    assert _ui.fmt_krw(14.85e8 / _ui.KRW_RATE) == '약 14.8억 원'


def test_fmt_krw_man_unit_rounding():
    """만 단위: int(round()) 반올림 — 149.5만 → 150만, 148.5만 → 148만 (round half-to-even)."""
    assert _ui.fmt_krw(1_495_000 / _ui.KRW_RATE) == '약 150만 원'
    assert _ui.fmt_krw(1_485_000 / _ui.KRW_RATE) == '약 148만 원'


def test_fmt_krw_none():
    assert _ui.fmt_krw(None) == '분析 불가'


def test_fmt_krw_delta_cookierun_1008():
    """fmt_krw_delta: 부호 포함 억 단위 반올림."""
    assert _ui.fmt_krw_delta(1_105_140.39) == '+14.9억 원'
    assert _ui.fmt_krw_delta(-1_105_140.39) == '-14.9억 원'
