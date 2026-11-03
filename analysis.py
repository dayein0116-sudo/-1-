"""Game Update Intelligence — 분석 계산 모듈 (Streamlit 의존 없음).

모든 숫자는 이 파일의 함수가 Python으로 계산합니다. app.py는 화면 표시만 담당합니다.

[이름 규칙]
- legacy_*  : MVP 2의 '일별 변동 기준' 판정. 회귀 검증을 위해 값은 그대로 보존합니다.
              (judge = judge_legacy, noise_sigma = daily_noise_sigma 는 호환용 별칭)
- 새 진단   : baseline_sensitivity / variability_reference / diagnose
              '기저 민감도'(비교 방식에 따라 결과가 얼마나 달라지는가)와
              '관측 변동성'(업데이트 없는 구간에서 7일 집계가 얼마나 움직이는가)을 분리합니다.
"""
import re

import numpy as np
import pandas as pd

BASE_MEAN = '평균 유지'
BASE_TREND = '추세 연장'


# ─────────────────────────────────────────────────────────────
# 1. 데이터 읽기·검증
# ─────────────────────────────────────────────────────────────
def read_csv_checked(source):
    """CSV를 읽고 (DataFrame, 점검 결과 목록)을 돌려줍니다. 치명적 문제는 ValueError."""
    df = pd.read_csv(source, encoding='utf-8-sig')
    issues = []
    if df.empty or df.shape[1] < 2:
        raise ValueError('날짜 열과 값 열이 있는 CSV가 아닙니다.')
    date_col = '날짜' if '날짜' in df.columns else df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    if df[date_col].isna().any():
        raise ValueError('날짜를 인식할 수 없는 행이 있습니다.')
    renamed = {}
    for c in df.columns:
        if c == date_col:
            continue
        renamed[c] = re.sub(r'\s+(수익|DAU)\s*\(절대적\)\s*$', '', str(c)).strip()
    df = df.rename(columns={date_col: 'date', **renamed})
    if df.columns.duplicated().any():
        dup = sorted(set(df.columns[df.columns.duplicated()]))
        raise ValueError(f'국가 이름이 중복되었습니다: {", ".join(map(str, dup))}')
    for c in df.columns:
        if c == 'date':
            continue
        raw = df[c]
        conv = pd.to_numeric(raw, errors='coerce')
        coerced = int((raw.notna() & conv.isna()).sum())
        if coerced:
            issues.append(('경고', f'{c}: 숫자로 읽을 수 없는 값 {coerced}개가 빈 값으로 처리되었습니다.'))
        df[c] = conv
    if df.date.duplicated().any():
        raise ValueError('날짜가 중복되었습니다.')
    df = df.sort_values('date').set_index('date')
    issues += validate_frame(df)
    return df, issues


def read_csv(source, metric=None):
    """MVP 2 호환 함수: DataFrame만 돌려줍니다 (metric 인자는 사용하지 않음)."""
    return read_csv_checked(source)[0]


def validate_frame(df):
    """읽은 표의 품질 점검. [(수준, 메시지)] — 수준은 '오류' 또는 '경고'."""
    issues = []
    full = pd.date_range(df.index.min(), df.index.max(), freq='D')
    missing = full.difference(df.index)
    if len(missing):
        shown = ', '.join(d.strftime('%m/%d') for d in missing[:5]) + (' 외' if len(missing) > 5 else '')
        issues.append(('경고', f'날짜가 비어 있는 날이 {len(missing)}일 있습니다 ({shown}). 해당 구간이 걸린 비교는 "자료 부족"이 됩니다.'))
    for c in df.columns:
        s = df[c]
        if s.notna().sum() == 0:
            issues.append(('경고', f'{c}: 값이 전부 비어 있습니다.'))
            continue
        n_na = int(s.isna().sum())
        if n_na:
            issues.append(('경고', f'{c}: 빈 값 {n_na}개.'))
        n_neg = int((s < 0).sum())
        if n_neg:
            issues.append(('경고', f'{c}: 음수 값 {n_neg}개 (환불 등이 아니라면 확인 필요).'))
        n_zero = int((s == 0).sum())
        if n_zero:
            issues.append(('경고', f'{c}: 0인 날 {n_zero}일. 0은 변화율 계산 기준에서 제외될 수 있습니다.'))
    return issues


def validate_pair(rev, dau):
    """매출·DAU 두 표의 기간·국가 구성 차이 점검."""
    issues = []
    if rev.index.min() != dau.index.min() or rev.index.max() != dau.index.max():
        issues.append(('경고', f'매출({rev.index.min():%m/%d}~{rev.index.max():%m/%d})과 DAU({dau.index.min():%m/%d}~{dau.index.max():%m/%d})의 기간이 다릅니다.'))
    rc = {c for c in rev if c != '기타'}
    dc = {c for c in dau if c != '기타'}
    if rc - dc:
        issues.append(('안내', f'매출 파일에만 있는 국가: {", ".join(sorted(rc - dc))} (DAU 분석 없음)'))
    if dc - rc:
        issues.append(('안내', f'DAU 파일에만 있는 국가: {", ".join(sorted(dc - rc))} (매출 분석 없음)'))
    return issues


def validate_updates(updates, index, n=7):
    """업데이트별로 D-n ~ D+n-1 구간이 자료 안에 있는지 점검. [{업데이트, 상태, 사유}]"""
    rows = []
    first, last = index.min(), index.max()
    for u in updates:
        d = pd.Timestamp(u['date'])
        g = u.get('base_gap', 0) or 0
        need_start, need_end = d - pd.Timedelta(days=n + g), d + pd.Timedelta(days=n - 1)
        if d < first or d > last:
            status, why = '분석 불가', '업데이트 날짜가 자료 기간 밖입니다.'
        elif need_start < first:
            status, why = '자료 부족', f'직전 {n}일 기저 구간이 자료 시작({first:%m/%d}) 이전입니다.'
        elif need_end > last:
            status, why = '자료 부족', f'이후 {n}일 구간({need_end:%m/%d})이 자료 끝({last:%m/%d})을 넘습니다.'
        else:
            status, why = '분석 가능', f'{need_start:%m/%d}~{need_end:%m/%d} 사용'
        rows.append({'업데이트': u['date'], '상태': status, '사유': why})
    return rows


def sum_countries(df, countries):
    """지정한 국가들만 합산 (집계 범위를 명시해야 할 때 사용)."""
    cols = [c for c in countries if c in df.columns]
    return df[cols].sum(axis=1, min_count=1)


# ─────────────────────────────────────────────────────────────
# 2. 기본 비교 (MVP 2와 동일한 계산)
# ─────────────────────────────────────────────────────────────
def delta(df, col, date, n=7):
    """업데이트 당일 포함 이후 N일 평균 vs 직전 N일 평균"""
    d = pd.Timestamp(date)
    before = df.loc[(df.index >= d - pd.Timedelta(days=n)) & (df.index < d), col].dropna()
    after = df.loc[(df.index >= d) & (df.index < d + pd.Timedelta(days=n)), col].dropna()
    if len(before) != n or len(after) != n or before.mean() == 0:
        return None
    return {'before': before.mean(), 'after': after.mean(), 'change_pct': (after.mean() / before.mean() - 1) * 100}


def prior_mean(s, date, n, gap=0):
    d = pd.Timestamp(date)
    b = s[(s.index >= d - pd.Timedelta(days=n + gap)) & (s.index < d - pd.Timedelta(days=gap))].dropna()
    return float(b.mean()) if len(b) == n else None


def profile(s, date, n, offsets=range(-2, 7), gap=0):
    """업데이트일 기준 D-2~D+6의 일별 값을 '직전 N일 평균 대비 배수'로 계산.
    gap>0이면 직전 gap일을 건너뛴 N일 평균을 기저로 씁니다 (기본 0 = MVP 2와 동일)."""
    base = prior_mean(s, date, n, gap)
    if base is None or base <= 0:
        return None, None
    d = pd.Timestamp(date)
    return base, {k: float(s.get(d + pd.Timedelta(days=k), np.nan)) / base for k in offsets}


def same_weekday_ratio(s, date, k=0):
    """D+k 값을 7일 전 같은 요일 값으로 나눈 배수. 단일일 비교의 요일 효과를 줄이기 위한 보조 지표."""
    d = pd.Timestamp(date) + pd.Timedelta(days=k)
    cur, prev = s.get(d, np.nan), s.get(d - pd.Timedelta(days=7), np.nan)
    if pd.isna(cur) or pd.isna(prev) or prev <= 0:
        return None
    return float(cur) / float(prev)


# ─────────────────────────────────────────────────────────────
# 3. 기저 방식별 변화율
# ─────────────────────────────────────────────────────────────
def baseline_changes(s, date, n, gaps=(0,)):
    """이후 N일 합계를 여러 기저와 비교한 변화율(%). 평균 유지(기본) / 직전 추세 연장(보조).
    MVP 2와 동일하게 계산합니다. 사전 상승이 있는 업데이트(gaps에 0과 양수가 함께 있음)는
    상승분이 섞인 직전 구간의 추세 연장을 계산하지 않습니다."""
    d = pd.Timestamp(date)
    after = s[(s.index >= d) & (s.index < d + pd.Timedelta(days=n))].dropna()
    if len(after) != n:
        return {}
    out = {}
    for g in gaps:
        b = s[(s.index >= d - pd.Timedelta(days=n + g)) & (s.index < d - pd.Timedelta(days=g))].dropna()
        if len(b) != n or b.mean() <= 0:
            continue
        tag = '' if g == 0 else f' (직전 {g}일 제외)'
        out[BASE_MEAN + tag] = (after.mean() / b.mean() - 1) * 100
        if g == 0 and len(gaps) > 1:
            continue
        if (b > 0).all() and n >= 3:
            k, c = np.polyfit(np.arange(n), np.log(b.values), 1)
            exp = np.exp(c + k * np.arange(n + g, n + g + n))
            out[BASE_TREND + tag] = (after.sum() / exp.sum() - 1) * 100
    return out


def trend_extension_loo(s, date, n, gap=0):
    """추세 연장 기저의 안정성 점검: 직전 N점 중 1점씩 빼고 다시 계산한 변화율의 (최소, 최대)."""
    d = pd.Timestamp(date)
    after = s[(s.index >= d) & (s.index < d + pd.Timedelta(days=n))].dropna()
    b = s[(s.index >= d - pd.Timedelta(days=n + gap)) & (s.index < d - pd.Timedelta(days=gap))].dropna()
    if len(after) != n or len(b) != n or n < 4 or not (b > 0).all():
        return None
    x, y = np.arange(n), np.log(b.values)
    vals = []
    for i in range(n):
        keep = np.arange(n) != i
        k, c = np.polyfit(x[keep], y[keep], 1)
        vals.append((after.sum() / np.exp(c + k * np.arange(n + gap, n + gap + n)).sum() - 1) * 100)
    return min(vals), max(vals)


def baseline_sensitivity(baselines):
    """기저 민감도: 기저 방식에 따라 결과가 얼마나 달라지는가. (잡음 기준과 무관)"""
    if not baselines:
        return None
    vals = list(baselines.values())
    lo, hi = min(vals), max(vals)
    sign = '+' if lo > 0 else '-' if hi < 0 else '±'
    return {'n': len(vals), 'lo': lo, 'hi': hi, 'spread_pp': hi - lo, 'sign': sign,
            'primary': next((v for k, v in baselines.items() if k == BASE_MEAN), None)}


# ─────────────────────────────────────────────────────────────
# 4. 관측 변동성 (업데이트 없는 구간의 7일 집계 변동)
# ─────────────────────────────────────────────────────────────
def clean_window_changes(s, upd_dates, n, pre=2, post=6):
    """업데이트 영향권(D-pre ~ D+post)과 겹치지 않는 '직전 N일 / 이후 N일' 구간의 평균 변화율(%) 목록.
    [(시작일, 변화율%)] — 시작일이 하루씩 밀린 구간은 서로 많이 겹칩니다."""
    s = s.dropna()
    if s.empty:
        return []
    days = pd.date_range(s.index.min(), s.index.max(), freq='D')
    vals = s.reindex(days).to_numpy(dtype=float)
    blocked = np.zeros(len(days), dtype=bool)
    for u in upd_dates:
        i = days.get_indexer([pd.Timestamp(u)])[0]
        if i < 0:
            continue
        blocked[max(0, i - pre):i + post + 1] = True
    out = []
    for i in range(len(days) - 2 * n + 1):
        if blocked[i:i + 2 * n].any():
            continue
        a, b = vals[i:i + n], vals[i + n:i + 2 * n]
        if np.isnan(a).any() or np.isnan(b).any() or a.mean() <= 0:
            continue
        out.append((days[i], (b.mean() / a.mean() - 1) * 100))
    return out


def variability_reference(s, upd_dates, n, min_independent=6):
    """7일 집계(N일 평균 대 N일 평균)에 맞는 경험적 변동 기준.
    서로 겹치지 않는 깨끗한 비교 구간이 min_independent개 미만이면 기준을 만들지 않습니다
    (일별 표준편차를 √N 등으로 환산해 대체하지 않음)."""
    wins = clean_window_changes(s, upd_dates, n)
    picked, last = [], None
    for start, pct in wins:
        if last is None or (start - last).days >= 2 * n:
            picked.append((start, pct))
            last = start
    ref = {'status': '미확립', 'n_windows': len(wins), 'n_independent': len(picked), 'min_independent': min_independent,
           'band_pct': None}
    if len(picked) >= min_independent:
        ref['status'] = '확립'
        ref['band_pct'] = float(max(abs(p) for _, p in picked))  # 관측된 최대 변화폭 (기술 통계, 추론 아님)
    else:
        ref['reason'] = (f'업데이트 영향권(D-2~D+6)과 겹치지 않고 서로 겹치지도 않는 {n}일 대 {n}일 비교 구간이 '
                         f'{len(picked)}개뿐입니다 (필요 {min_independent}개 이상).')
    return ref


def diagnose(sens, variability=None):
    """기저 민감도와 (확립된 경우) 관측 변동성을 합친 진단. 판정 이름은 기존 판정과 구분합니다."""
    if sens is None:
        return {'direction': '자료 부족', 'magnitude': '자료 부족', 'verdict': '자료 부족'}
    if sens['n'] < 2:
        direction = '기저 1개뿐 (민감도 확인 불가)'
    elif sens['sign'] == '+':
        direction = '기저 간 방향 일치 (증가)'
    elif sens['sign'] == '-':
        direction = '기저 간 방향 일치 (감소)'
    else:
        direction = '기저에 따라 방향이 갈림'
    if variability and variability.get('status') == '확립':
        band = variability['band_pct']
        lo, hi = sens['lo'], sens['hi']
        if lo > band:
            magnitude = '관측 변동성 밖'
        elif hi < -band:
            magnitude = '관측 변동성 밖'
        elif lo > -band and hi < band:
            magnitude = '관측 변동성 범위 안'
        else:
            magnitude = '기저에 따라 변동성 안팎이 갈림'
    else:
        magnitude = '크기 판정 보류 (변동성 기준 미확립)'
    return {'direction': direction, 'magnitude': magnitude, 'verdict': f'{direction} · {magnitude}'}


# ─────────────────────────────────────────────────────────────
# 5. 기존(MVP 2) 일별 변동 기준 판정 — 비교·회귀 검증용으로 보존
# ─────────────────────────────────────────────────────────────
def daily_noise_sigma(s, upd_dates, pre=2, post=6, min_obs=12):
    """[기존 기준] 업데이트 영향권(D-2~D+6)을 뺀 날의 '일별' 변동 크기(로그 잔차 표준편차).
    일별 값의 흩어짐이며 7일 집계 변화율의 변동성이 아닙니다 (요일 효과 포함, 잔차끼리 자기상관 있음)."""
    s = s.dropna()
    s = s[s > 0]
    if len(s) < 14:
        return None
    ls = np.log(s)
    res = ls - ls.rolling(7, center=True, min_periods=4).mean()
    mask = pd.Series(True, index=res.index)
    for u in upd_dates:
        t = pd.Timestamp(u)
        mask[(res.index >= t - pd.Timedelta(days=pre)) & (res.index <= t + pd.Timedelta(days=post))] = False
    res = res[mask].dropna()
    if len(res) < min_obs:
        return None
    return float(res.std())


noise_sigma = daily_noise_sigma


def judge_legacy(lo, hi, sigma, single=False):
    """[기존 판정] 변화율 범위를 일별 변동 크기(sigma×100%)와 비교. 7일 변화율에는 부적절할 수 있어 참고용."""
    if lo is None or sigma is None:
        return '기준 부족'
    th = sigma * 100
    if lo > th:
        return '증가 신호' if single else '증가 (기저 무관)'
    if hi < -th:
        return '감소 신호' if single else '감소 (기저 무관)'
    if lo > -th and hi < th:
        return '잡음 범위'
    return '판단 불가' if single else '판단 불가 (기저 의존)'


judge = judge_legacy


# ─────────────────────────────────────────────────────────────
# 6. 업데이트 1건 × 지표 1개의 종합 계산
# ─────────────────────────────────────────────────────────────
def series_metrics(s, upd, n, sigma, variability=None):
    """기존 키(base, ratios, baselines, d02, lo, hi, judge, d0_judge)는 MVP 2와 같은 값입니다.
    새 키: sensitivity, direction, verdict, primary_change, trend_loo, d0_alt, d0_same_weekday"""
    base, ratios = profile(s, upd['date'], n)
    gap = upd.get('base_gap') or 0
    gaps = (0,) if not gap else (0, gap)
    bl = baseline_changes(s, upd['date'], n, gaps)
    m = {'base': base, 'ratios': ratios, 'baselines': bl, 'd02': None, 'lo': None, 'hi': None,
         'judge': '자료 부족', 'd0_judge': '자료 부족'}
    if ratios:
        d02 = [ratios[0], ratios[1], ratios[2]]
        if not any(np.isnan(d02)):
            m['d02'] = float(np.mean(d02))
        if not np.isnan(ratios[0]):
            p0 = (ratios[0] - 1) * 100
            m['d0_judge'] = judge_legacy(p0, p0, sigma, single=True)
    if bl:
        vals = list(bl.values())
        m['lo'], m['hi'] = min(vals), max(vals)
        m['judge'] = judge_legacy(m['lo'], m['hi'], sigma)
    # ── 새 진단 ──
    sens = baseline_sensitivity(bl)
    diag = diagnose(sens, variability)
    # 추세 연장이 계산된 경우에만 안정성 점검 (사전 상승 업데이트는 gap을 건너뛴 추세만 계산됨)
    trend_loo = trend_extension_loo(s, upd['date'], n, gap) if any(k.startswith(BASE_TREND) for k in bl) else None
    m.update({'sensitivity': sens, 'direction': diag['direction'], 'magnitude': diag['magnitude'], 'verdict': diag['verdict'],
              'primary_change': sens['primary'] if sens else None, 'trend_loo': trend_loo,
              'd0_same_weekday': same_weekday_ratio(s, upd['date'], 0), 'd0_alt': None})
    if gap:
        _, alt = profile(s, upd['date'], n, gap=gap)
        if alt and not np.isnan(alt[0]):
            m['d0_alt'] = alt[0]
    return m


# ─────────────────────────────────────────────────────────────
# 7. 반응 지속성 · 데이터 병합 · 함께 고려할 시점 요인 (v3 업데이트 진단용)
# ─────────────────────────────────────────────────────────────
def persistence(ratios, early=(0, 1, 2), late=(3, 4, 5, 6)):
    """D0~D+6 배수에서 초기(D0~D2)와 후기(D3~D6) 평균, 그리고 후기/초기 비율을 계산.
    직전 평균 대비 배수이므로 '1.0 미만'이 곧 업데이트 실패를 뜻하지는 않습니다 (직전 추세가 하락 중일 수 있음)."""
    if not ratios:
        return None
    e = [ratios.get(k, np.nan) for k in early]
    l = [ratios.get(k, np.nan) for k in late]
    if any(pd.isna(x) for x in e + l):
        return None
    e_m, l_m = float(np.mean(e)), float(np.mean(l))
    return {'early': e_m, 'late': l_m, 'retention': (l_m / e_m) if e_m > 0 else None, 'd6': float(ratios[6])}


def merge_frames(base, extra, overwrite=False):
    """기본 데이터(base)에 업로드 데이터(extra)를 합칩니다 — 기간 확장과 국가 보완이 목적.
    · 날짜와 국가는 합집합. 비어 있던 칸만 채우는 것이 기본이며, 겹치는 값이 다르면 기본 데이터를 유지합니다
      (overwrite=True이면 업로드 값을 사용). 보간하거나 새 값을 만들지 않습니다."""
    idx = base.index.union(extra.index)
    cols = list(base.columns) + [c for c in extra.columns if c not in base.columns]
    b = base.reindex(index=idx, columns=cols)
    e = extra.reindex(index=idx, columns=cols)
    both = b.notna() & e.notna()
    diff = both & ((b - e).abs() > 1e-9)
    merged = e.combine_first(b) if overwrite else b.combine_first(e)
    info = {'new_dates': int(len(extra.index.difference(base.index))),
            'new_countries': [c for c in extra.columns if c not in base.columns],
            'overlap_cells': int(both.to_numpy().sum()), 'conflict_cells': int(diff.to_numpy().sum()),
            'max_abs_diff': float((b - e).abs().where(diff).max().max()) if diff.to_numpy().any() else 0.0,
            'overwrite': bool(overwrite), 'start': merged.index.min(), 'end': merged.index.max()}
    merged.index.name = 'date'
    return merged, info


def timing_flags(upd, updates, window, series=None):
    """업데이트 시점 주변의 사실 점검 (날짜·데이터 기반, 원인 판단 없음). [{'kind','text'}]
    series가 있으면 직전 구간의 일별 변화 추세와 D-2·D-1 배수도 사실로 기록합니다."""
    flags = []
    d = pd.Timestamp(upd['date'])
    n = window
    dates = sorted(pd.Timestamp(u['date']) for u in updates)
    prev = [x for x in dates if x < d]
    nxt = [x for x in dates if x > d]
    pre_start, pre_end = d - pd.Timedelta(days=n), d - pd.Timedelta(days=1)
    if prev:
        p = prev[-1]
        k0, k1 = (pre_start - p).days, (pre_end - p).days
        if k0 <= 6:
            flags.append({'kind': '비교 구간 겹침', 'text': f'직전 {n}일 비교 구간({pre_start:%m/%d}~{pre_end:%m/%d})이 이전 업데이트({p:%m/%d})의 영향권(D-2~D+6)과 겹칩니다.'})
        else:
            flags.append({'kind': '직전 구간 위치', 'text': f'직전 {n}일 비교 구간({pre_start:%m/%d}~{pre_end:%m/%d})은 이전 업데이트({p:%m/%d}) 후 D+{k0}~D+{k1}일에 해당합니다. 이전 업데이트 반응이 아직 줄어드는 중일 수 있어 기저가 불안정할 수 있습니다.'})
    else:
        flags.append({'kind': '직전 구간 위치', 'text': f'직전 {n}일 비교 구간({pre_start:%m/%d}~{pre_end:%m/%d})은 등록된 이전 업데이트가 없는 구간입니다 (게임 출시 직후 추세가 섞여 있을 수 있음).'})
    post_end = d + pd.Timedelta(days=n - 1)
    if nxt and nxt[0] <= post_end:
        flags.append({'kind': '비교 구간 겹침', 'text': f'이후 {n}일 구간({d:%m/%d}~{post_end:%m/%d})에 다음 업데이트({nxt[0]:%m/%d})가 포함됩니다.'})
    if series is not None:
        s = series.dropna()
        pre = s[(s.index >= pre_start) & (s.index <= pre_end)]
        if len(pre) == n and (pre > 0).all() and n >= 3:
            slope = np.polyfit(np.arange(n), np.log(pre.values), 1)[0]
            flags.append({'kind': '직전 추세', 'text': f'직전 {n}일 일별 추정 매출은 하루 평균 {(np.exp(slope) - 1) * 100:+.1f}%씩 변하는 추세였습니다 (로그 선형 기울기).'})
        base = prior_mean(series, d, n)
        if base and base > 0:
            r2, r1 = series.get(d - pd.Timedelta(days=2), np.nan), series.get(d - pd.Timedelta(days=1), np.nan)
            if not (pd.isna(r2) or pd.isna(r1)):
                flags.append({'kind': '업데이트 직전', 'text': f'업데이트 직전 D-2는 직전 {n}일 일평균 대비 {(r2 / base - 1) * 100:+.0f}%, D-1은 {(r1 / base - 1) * 100:+.0f}%입니다 (업데이트 전에 이미 움직였는지 확인용).'})
    flags.append({'kind': '요일', 'text': f'업데이트일(D0)은 {"월화수목금토일"[d.dayofweek]}요일입니다. 직전·이후 {n}일에는 각 요일이 한 번씩 들어가지만(n=7일 때) 연휴·프로모션 영향은 별도로 남습니다.'})
    return flags



# ─────────────────────────────────────────────────────────────
# 8. 전주 대비 비교 (업계에서 흔히 쓰는 형태 — v3 진단 화면의 기본 지표)
# ─────────────────────────────────────────────────────────────
def week_compare(s, date, n=7):
    """업데이트 주(업데이트일 포함 n일) vs 직전 n일(n=7이면 전주). 요일 구성이 같고, 값이 하나라도 비면 None.
    합계 비교와 일평균 비교는 같은 변화율입니다."""
    d = pd.Timestamp(date)
    cur = s[(s.index >= d) & (s.index < d + pd.Timedelta(days=n))]
    prev = s[(s.index >= d - pd.Timedelta(days=n)) & (s.index < d)]
    if len(cur) != n or len(prev) != n or cur.isna().any() or prev.isna().any() or prev.sum() == 0:
        return None
    ck, pk = int(np.argmax(cur.values)), int(np.argmax(prev.values))
    return {'cur_sum': float(cur.sum()), 'prev_sum': float(prev.sum()), 'cur_mean': float(cur.mean()), 'prev_mean': float(prev.mean()),
            'pct': (float(cur.sum()) / float(prev.sum()) - 1) * 100,
            'cur_peak': float(cur.max()), 'cur_peak_k': ck, 'prev_peak': float(prev.max()), 'prev_peak_k': pk,
            'peak_pct': (float(cur.max()) / float(prev.max()) - 1) * 100 if prev.max() else None}


def day_vs_prev(s, date, k=0, n=7):
    """D+k일 값과 n일 전(n=7이면 전주 같은 요일) 값. 둘 중 하나라도 없으면 None."""
    d = pd.Timestamp(date)
    x, y = s.get(d + pd.Timedelta(days=k)), s.get(d + pd.Timedelta(days=k - n))
    if x is None or y is None or pd.isna(x) or pd.isna(y):
        return None
    return {'cur': float(x), 'prev': float(y), 'pct': (float(x) / float(y) - 1) * 100 if y else None,
            'cur_date': d + pd.Timedelta(days=k), 'prev_date': d + pd.Timedelta(days=k - n)}
