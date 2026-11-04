"""업데이트 1건의 진단 리포트에 필요한 모든 계산 — Streamlit 의존 없음.

화면은 이 모듈이 돌려주는 dict만 그립니다. 모든 수치는 Python이 계산하고,
데이터가 부족한 항목은 값을 만들지 않고 ok=False와 사유를 돌려줍니다 (→ 화면에 '분석 불가').
"""
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

import analysis as an

SCOPE_LABELS = {'common': '공통 {n}개국 합산', 'file': '파일 전체 합계 (개별 국가 + 기타)'}
REV_SCOPE_LABELS = {'common': '공통 {n}개국 매출 합계', 'file': '매출 파일 전체 합계 (개별 국가 + 기타)'}
DAU_SCOPE_LABELS = {'common': '공통 {n}개국 DAU 합계', 'file': 'DAU 파일 전체 합계 (개별 국가 + 기타)'}
DAU_NOTE = ('DAU 합계는 국가별 DAU 추정치를 같은 날짜끼리 더한 값입니다. 여러 국가에서 접속한 이용자가 중복 집계되는지 CSV로는 확인되지 않아 '
            '고유 이용자 수가 아닙니다. 국가별 원본 수치는 변경하지 않았습니다.')


def period_labels(n=7):
    """D0 기반 비교의 두 구간 이름 (이후 N일 vs 이전 N일). 일별 추이 차트·테이블에서 사용."""
    return f'이후 {n}일', f'이전 {n}일'


def cal_period_labels():
    """달력 주(월~일) 기준 비교의 두 구간 이름. KPI·국가 비교·업데이트 비교에서 사용."""
    return '업데이트 주', '전주'


@dataclass
class DataContext:
    """한 프로젝트의 매출·DAU와 파생 정보 (프로젝트별로 하나씩 만듭니다)."""
    rev: pd.DataFrame
    dau: pd.DataFrame
    updates: list
    categories: list
    rev_countries: list
    dau_countries: list
    common: list
    display_countries: list
    truncated: int
    upd_dates: list

    def scope_columns(self, scope):
        """집계에 쓰는 열. common → 매출·DAU 모두 같은 공통 국가 목록, file → 각 파일의 모든 열(기타 포함)."""
        if scope == 'common':
            return list(self.common), list(self.common)
        return list(self.rev.columns), list(self.dau.columns)

    def series(self, scope):
        """scope='common' → 공통 국가 합산, 'file' → 파일 전체 합계(기타 포함). 매출·DAU는 서로 결합하지 않습니다."""
        rc, dc = self.scope_columns(scope)
        return self.rev[rc].sum(axis=1, min_count=1), self.dau[dc].sum(axis=1, min_count=1)


def scope_audit(ctx, scope='common'):
    """매출·DAU 합계가 실제로 같은 국가 집합으로 계산되는지 점검합니다 (series()가 쓰는 열 목록을 그대로 확인)."""
    rc, dc = ctx.scope_columns(scope)
    missing = int(ctx.rev[rc].isna().sum().sum() + ctx.dau[dc].isna().sum().sum())
    same = set(rc) == set(dc)
    return {'scope': scope, 'rev_cols': rc, 'dau_cols': dc, 'same_countries': same, 'missing_cells': missing,
            'ok': (same or scope != 'common') and missing == 0}


def build_context(project, rev, dau):
    rev_c = [c for c in rev if c != '기타']
    dau_c = [c for c in dau if c != '기타']
    actual_common = set(rev_c) & set(dau_c)
    explicit = project.meta.get('common_countries')
    if explicit:
        common = [c for c in explicit if c in actual_common]  # 프로젝트별 공통 국가 지정 (CSV에는 보존)
    else:
        common = sorted(actual_common)
    first = pd.Timestamp(project.updates[0]['date']) if project.updates else rev.index.max()
    pre = rev.loc[rev.index < first]
    size = pre.sum() if len(pre) else rev.sum()
    ranked = sorted(common, key=lambda c: -float(size.get(c, 0) or 0))
    rev_only = sorted([c for c in rev_c if c not in dau_c], key=lambda c: -float(size.get(c, 0) or 0))
    dau_only = sorted([c for c in dau_c if c not in rev_c], key=lambda c: -float(dau[c].sum()))
    allc = ranked + rev_only + dau_only
    limit = int(project.meta.get('max_countries', 10))
    return DataContext(rev=rev, dau=dau, updates=project.updates, categories=project.categories,
                       rev_countries=rev_c, dau_countries=dau_c, common=common, display_countries=allc[:limit],
                       truncated=max(0, len(allc) - limit), upd_dates=[u['date'] for u in project.updates])


# ─────────────────────────────────────────────────────────────
def _metric_block(s, upd, n, upd_dates):
    """시리즈 1개 × 업데이트 1건. 계산 불가면 ok=False와 사유."""
    if s is None or s.dropna().empty:
        return {'ok': False, 'reason': '해당 지표 데이터가 없습니다.'}
    var = an.variability_reference(s, upd_dates, n)
    m = an.series_metrics(s, upd, n, None, var)
    d = an.delta(pd.DataFrame({'x': s}), 'x', upd['date'], n)
    if not m['ratios']:
        rows = an.validate_updates([upd], s.index, n)
        return {'ok': False, 'reason': rows[0]['사유'] if rows[0]['상태'] != '분석 가능' else f'직전 {n}일 구간에 빈 값이 있습니다.'}
    p = an.persistence(m['ratios'])
    ok_after = bool(m['baselines'])
    return {'ok': True, 'm': m, 'delta': d, 'persistence': p, 'variability': var,
            'after_ok': ok_after, 'reason': None if ok_after else f'이후 {n}일 구간이 자료 끝을 넘거나 비어 있습니다.'}


metric_block = _metric_block  # 화면에서 국가 1개씩 계산할 때 사용


def _baseline_rows(blk, label):
    if not blk.get('ok') or not blk['m']['baselines']:
        return []
    m = blk['m']
    rows = []
    for name, pct in m['baselines'].items():
        if name == an.BASE_MEAN:
            role, note = '기본', '직전 평균을 그대로 유지한다고 본 기저'
        elif name.startswith(an.BASE_MEAN):
            role, note = '대안', '사전 상승이 섞인 직전 며칠을 제외한 기저 (인과적으로 올바른 기저라고 확정할 수 없음)'
        else:
            role, note = '보조 (참고)', '직전 추세를 이어간다고 본 기저 — 외삽이라 불안정할 수 있음'
            if m.get('trend_loo'):
                note += f' · 직전 값 1개씩 빼면 {m["trend_loo"][0]:+.0f}% ~ {m["trend_loo"][1]:+.0f}%'
        rows.append({'지표': label, '기저 방식': name, '구분': role, '변화율(%)': pct, '비고': note})
    return rows


def _strip_paren(t):
    return re.sub(r'\s*[\(（].*?[\)）]', '', t).strip()


def highlights(upd, limit=2):
    """업데이트 요약 카드용 주요 콘텐츠: 범주별 앞쪽 항목 (공지 요약 기준)."""
    order = ['신규 캐릭터·수집', '경쟁·엔드 콘텐츠', '신규 BM 가능성(공지 표기 기준)', '성장 시스템', '이벤트']
    out = []
    for cat in order:
        items = upd['items_detail'].get(cat, [])
        if items:
            out.append((cat, [_strip_paren(x['text']) for x in items[:limit]]))
    return out


def _fx(v):
    return '분석 불가' if v is None or (isinstance(v, float) and np.isnan(v)) else f'×{v:.2f}'


def _pct(v):
    return '분석 불가' if v is None else f'{v:+.1f}%'


def notice_facts(upd):
    """[사실] 공지 요약에 등록된 내용 (원문 전체 아님)."""
    det = upd['items_detail']
    facts = [f'등록된 공지 요약 항목: ' + ', '.join(f'{c} {len(v)}건' for c, v in det.items() if v) + '.']
    kinds = {}
    for cat, v in det.items():
        for x in v:
            if x['kind']:
                kinds.setdefault(x['kind'], []).append(_strip_paren(x['text']))
    for k, texts in kinds.items():
        if any(w in k for w in ('신규 전용 뽑기', '신규 패스', 'PvP', 'PvE', '신규 BM 아님')):
            facts.append(f'{k}: ' + ', '.join(texts) + '.')
    if not det.get('신규 BM 가능성(공지 표기 기준)'):
        facts.append('공지 요약에 신규 BM(신규 전용 뽑기 재화·패스 등)으로 표기된 항목이 없습니다.')
    return facts


def _pc(v):
    return '분석 불가' if v is None else f'{v:+.1f}%'


def data_facts(rep):
    """[관찰] 계산된 수치를 문장으로 옮긴 것 — 해석이나 원인 판단을 넣지 않습니다."""
    n, d, f = rep['window'], rep['update']['date'], []
    cur, prev = cal_period_labels()
    for key, label in (('rev', '추정 매출'), ('dau', 'DAU')):
        ser = rep[f'{key}_series']
        d0, wk = an.day_vs_prev(ser, d, 0, n), an.week_compare_cal(ser, d)
        if d0 is None and wk is None:
            f.append(f'{label}: 분석 불가 — {rep[key].get("reason") or "비교 구간 자료 부족"}')
            continue
        if wk:
            if key == 'rev':
                f.append(f'{label}({rep[key + "_scope_label"]}): {cur} 합계는 {prev} 합계 대비 {_pc(wk["pct"])} ({wk["prev_sum"]:,.0f} → {wk["cur_sum"]:,.0f}, 증감액 {wk["cur_sum"] - wk["prev_sum"]:+,.0f}).')
            else:
                f.append(f'{label}({rep[key + "_scope_label"]}): {cur} 일평균은 {prev} 일평균 대비 {_pc(wk["pct"])} ({wk["prev_mean"]:,.0f} → {wk["cur_mean"]:,.0f}).')
        else:
            f.append(f'{label}: {cur} 비교는 분석 불가 — 자료 끝({ser.dropna().index.max():%m/%d})을 넘거나 비어 있습니다.')
        if d0:
            f.append(f'{label}: 업데이트 당일(D0)은 {n}일 전 같은 요일 대비 {_pc(d0["pct"])} ({d0["prev"]:,.0f} → {d0["cur"]:,.0f}) — 하루 단위 참고값입니다.')
    for key, label in (('rev', '추정 매출'), ('dau', 'DAU')):
        pool = [c for c in rep['countries'] if rep['scope'] != 'common' or not c['tag']]
        rows = [(c['name'], c[key]['delta']['change_pct']) for c in pool if c[key] and c[key]['ok'] and c[key].get('delta')]
        if rows:
            rows.sort(key=lambda x: -x[1])
            up = sum(v > 0 for _, v in rows)
            f.append(f'국가별 {label}: {cur}이 {prev}보다 늘어난 국가 {up}/{len(rows)}개국 '
                     f'(가장 큰 {rows[0][0]} {rows[0][1]:+.0f}%, 가장 작은 {rows[-1][0]} {rows[-1][1]:+.0f}%).')
    return f


def limits_for(rep, upd, ctx):
    """[한계] 이 업데이트·이 데이터에서 해석이 제한되는 이유."""
    n = rep['window']
    out = ['Sensor Tower 추정치이며 업데이트가 매출·DAU 변화의 원인이라는 증거가 아닙니다 (관찰된 변화만 제시).',
           '공지 요약 항목별 매출 기여도는 계산하지 않습니다 (상품별 매출·PU 데이터 없음).']
    if upd['confounds']:
        out.append('같은 업데이트 안에서 동시에 투입된 요소는 개별 효과를 분리할 수 없습니다.')
    out.append('업데이트는 공지 기준 13:00 전후 반영되며 Sensor Tower 일 경계(시간대)가 확정되지 않아 D0 해석에 주의가 필요합니다.')
    out.append(DAU_NOTE)
    out.append('매출과 DAU의 플랫폼·집계 범위가 같은지 확인되지 않아 두 지표를 결합한 지표(ARPDAU 등)는 계산하지 않습니다. 매출 CSV 통화는 USD(Sensor Tower), 표시는 1 USD = 1,350원 환산. 플랫폼 범위는 확인되지 않았습니다.')
    out.append('결제자 수·ARPPU·신규/복귀 이용자 수는 데이터에 없어 판단하지 않습니다. 운영 이슈가 있었더라도 매출·DAU 증감과 연결하지 않습니다.')
    if rep['scope'] == 'common':
        out.append('"공통 국가 합산"은 매출·DAU 파일 모두에 있는 국가만 합친 값이라 파일 전체 합계(기타·홍콩·호주 등 포함)와 다릅니다.')
    else:
        out.append('파일 전체 합계의 DAU에는 매출 파일에 없는 국가와 기타가 섞여 있어, 특정 국가의 지속적인 증감이 합계 방향을 좌우할 수 있습니다.')
    if any(c['rev'] and c['rev']['ok'] for c in rep['countries']):
        out.append('소규모 국가는 일 매출 규모가 작아 변동이 크므로 국가 간 배수를 단순 비교하지 않습니다.')
    out += [f'미반영: {x}' for x in upd['pending_review']]
    return out


def country_week_table(ctx, rep, key):
    """국가별 달력 주(월~일) 기준 업데이트 주 / 전주 값, 증감액, 증감률 (+합계 행).
    key='rev'면 주간 합계, 'dau'면 주간 일평균.
    반환: [{'name','group','prev','cur','diff','pct','d0','d0_pct'}] — group: '합계' / '포함' / '미포함'. 계산 불가 칸은 None."""
    n, d = rep['window'], rep['update']['date']
    df = ctx.rev if key == 'rev' else ctx.dau
    inc_cols = ctx.scope_columns(rep['scope'])[0 if key == 'rev' else 1]
    mult = 1.0 if key == 'rev' else 1.0 / 7  # DAU: 주간 일평균

    def row(name, ser, group):
        w, x = an.week_compare_cal(ser, d), an.day_vs_prev(ser, d, 0, n)
        if not w:
            return {'name': name, 'group': group, 'prev': None, 'cur': None, 'diff': None, 'pct': None,
                    'd0': x['cur'] if x else None, 'd0_pct': x['pct'] if x else None}
        prev, cur = w['prev_sum'] * mult, w['cur_sum'] * mult
        return {'name': name, 'group': group, 'prev': prev, 'cur': cur, 'diff': cur - prev, 'pct': w['pct'],
                'd0': x['cur'] if x else None, 'd0_pct': x['pct'] if x else None}

    cols = [c for c in df.columns if c in inc_cols or c != '기타']   # 기타는 파일 전체 범위에서만 포함
    out = [row(c, df[c], '포함' if c in inc_cols else '미포함') for c in cols]
    out.sort(key=lambda r: (r['group'] != '포함', -(r['cur'] if r['cur'] is not None else -1)))
    total = row(rep[f'{key}_scope_label'], rep[f'{key}_series'], '합계')
    return [total] + out


def build_update_report(ctx, upd, window, scope='common'):
    """업데이트 1건 × (선택한 집계 범위) 진단에 필요한 모든 값을 계산합니다."""
    n = window
    rev_s, dau_s = ctx.series(scope)
    rep = {'update': upd, 'window': n, 'scope': scope,
           'scope_label': SCOPE_LABELS[scope].format(n=len(ctx.common)),
           'rev_scope_label': REV_SCOPE_LABELS[scope].format(n=len(ctx.common)),
           'dau_scope_label': DAU_SCOPE_LABELS[scope].format(n=len(ctx.common)),
           'rev': _metric_block(rev_s, upd, n, ctx.upd_dates), 'dau': _metric_block(dau_s, upd, n, ctx.upd_dates)}
    g = upd.get('base_gap') or 0
    for key, s in (('rev', rev_s), ('dau', dau_s)):
        rep[key]['alt_ratios'] = None
        if g and rep[key]['ok']:
            _, alt = an.profile(s, upd['date'], n, gap=g)
            rep[key]['alt_ratios'] = alt
    rep['rev_series'], rep['dau_series'] = rev_s, dau_s
    # 국가별
    countries = []
    for c in ctx.display_countries:
        row = {'name': c, 'tag': '', 'rev': None, 'dau': None}
        if c in ctx.rev:
            row['rev'] = _metric_block(ctx.rev[c], upd, n, ctx.upd_dates)
        if c in ctx.dau:
            row['dau'] = _metric_block(ctx.dau[c], upd, n, ctx.upd_dates)
        if row['rev'] is None:
            row['tag'] = 'DAU만'
        elif row['dau'] is None:
            row['tag'] = '매출만'
        base_n = an.prior_mean(ctx.rev[c], upd['date'], n) if c in ctx.rev else None
        row['rev_prior_mean'] = base_n
        countries.append(row)
    rep['countries'] = countries
    rep['baseline_rows'] = {'rev': _baseline_rows(rep['rev'], '추정 매출'), 'dau': _baseline_rows(rep['dau'], 'DAU')}
    rep['flags'] = an.timing_flags(upd, ctx.updates, n, rev_s)
    rep['notice_facts'] = notice_facts(upd)
    rep['data_facts'] = data_facts(rep)
    rep['limits'] = limits_for(rep, upd, ctx)
    rep['availability'] = {'rev': an.validate_updates([upd], ctx.rev.index, n)[0], 'dau': an.validate_updates([upd], ctx.dau.index, n)[0]}
    return rep
