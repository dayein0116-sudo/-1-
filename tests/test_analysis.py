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
