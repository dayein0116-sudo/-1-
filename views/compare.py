"""업데이트 비교 — 등록된 업데이트를 같은 기준(이전 7일 vs 이후 7일)으로 나란히 봅니다."""
import numpy as np
import pandas as pd
import streamlit as st

import analysis as an
import charts
import report
import ui
from ui import fmt_range, fp, fx


def render(env):
    ctx, n, ups, d_sel = env.ctx, env.window, env.project.updates, env.upd['date']
    cur_l, prev_l = report.period_labels(n)
    st.caption(f'모든 업데이트에 같은 방식을 적용했습니다: 이전 {n}일(D-{n}∼D-1) vs 이후 {n}일(D0∼D+{n - 1}, 업데이트 당일 포함, 요일 구성 동일).')
    st.caption(f'집계 범위: {env.rep["scope_label"]} (위에서 변경)')
    rs, ds = ctx.series(env.scope)

    # ── 추정 매출 ──
    rows, labs, prevs, curs = [], [], [], []
    for u in ups:
        w, x = an.week_compare(rs, u['date'], n), an.day_vs_prev(rs, u['date'], 0, n)
        lab = u['date'][5:]
        labs.append(lab)
        prevs.append(w['prev_sum'] * ui.KRW_RATE / 1e8 if w else None)
        curs.append(w['cur_sum'] * ui.KRW_RATE / 1e8 if w else None)
        rows.append({'날짜': u['date'], '업데이트': u['title'],
                     'D0 추정 매출': ui.fmt_krw(x['cur'] if x else None), 'D0 (참고: 7일 전 같은 요일 대비)': fp(x['pct']) if x else '분석 불가',
                     f'{prev_l} 합계': ui.fmt_krw(w['prev_sum'] if w else None), f'{cur_l} 합계': ui.fmt_krw(w['cur_sum'] if w else None),
                     '증감액': ui.fmt_krw_delta(w['cur_sum'] - w['prev_sum'] if w else None), '증감률': fp(w['pct']) if w else '분析 불가',
                     '최고 일 (D0~)': (ui.fmt_krw(w['cur_peak']) + f' ({"D0" if w["cur_peak_k"] == 0 else f"D+{w["cur_peak_k"]}"})') if w else '분析 불가'})
    with st.container(key='card_cmp_rev'):
        ui.card_title('추정 매출', f'{cur_l} 합계 vs {prev_l} 합계 · 원화 환산 (1 USD = 1,350원) · {env.rep["rev_scope_label"]}')
        ui.table(pd.DataFrame(rows))
        ui.show(charts.fig_group_bars(labs, prevs, curs, prev_l, cur_l, charts.BLUE, unit='억원'))

    # ── DAU ──
    rows, prevs, curs = [], [], []
    for u in ups:
        w, x = an.week_compare(ds, u['date'], n), an.day_vs_prev(ds, u['date'], 0, n)
        prevs.append(w['prev_mean'] if w else None)
        curs.append(w['cur_mean'] if w else None)
        rows.append({'날짜': u['date'], '업데이트': u['title'],
                     'D0 DAU': f"{x['cur']:,.0f}" if x else '분석 불가', 'D0 (참고: 7일 전 같은 요일 대비)': fp(x['pct']) if x else '분석 불가',
                     f'{prev_l} 일평균': f"{w['prev_mean']:,.0f}" if w else '분석 불가', f'{cur_l} 일평균': f"{w['cur_mean']:,.0f}" if w else '분석 불가',
                     '증감률': fp(w['pct']) if w else '분석 불가'})
    with st.container(key='card_cmp_dau'):
        ui.card_title('DAU', f'{cur_l} 일평균 vs {prev_l} 일평균 · {env.rep["dau_scope_label"]}')
        ui.table(pd.DataFrame(rows))
        ui.show(charts.fig_group_bars(labs, prevs, curs, prev_l, cur_l, charts.GREEN))
        st.caption(report.DAU_NOTE + ' 매출과 결합한 지표(ARPDAU 등)는 계산하지 않습니다.')

    # ── 국가별 ──
    with st.container(key='card_cmp_country'):
        ui.card_title('국가별 추정 매출 증감률 · 이후 7일 매출', f'각 칸: 증감률 · {cur_l} 합계(원화 환산 (1 USD = 1,350원)) — 증감률만으로 판단하지 말고 규모를 함께 보세요')
        crow = []
        for c in ctx.rev_countries:
            row = {'국가': c + ('' if c in ctx.dau_countries else ' (매출만)')}
            for u in ups:
                w = an.week_compare(ctx.rev[c], u['date'], n)
                row[u['date'][5:]] = (f"{fp(w['pct'], 0)} · " + ui.fmt_krw(w['cur_sum'])) if w else '분析 불가'
            crow.append(row)
        ui.table(pd.DataFrame(crow))
        st.caption('소규모 국가는 일 규모가 작아 증감률의 변동이 큽니다.')

    # ── 기존 MVP 2 비교 화면 (보존) ──
    with st.expander('기존 비교 화면 (MVP 2 방식 · 기저·기존 판정 포함 · 고급, 참고용)'):
        rev_total = ctx.rev.sum(axis=1, min_count=1)
        dau_total = ctx.dau.sum(axis=1, min_count=1)
        common_dau = an.sum_countries(ctx.dau, ctx.common)
        sg_t = an.daily_noise_sigma(rev_total, ctx.upd_dates)
        ordered = sorted(ups, key=lambda u: u['date'])
        st.markdown('**전체 추정 매출 단순 비교 (직전 평균 기저)**')
        rows = []
        for u in ups:
            r = an.delta(pd.DataFrame({'total': rev_total}), 'total', u['date'], n)
            rows.append({'날짜': u['date'], '업데이트': u['title'], '이전 일평균': round(r['before'], 2) if r else None,
                         '이후 일평균': round(r['after'], 2) if r else None, '매출 변화율(%)': round(r['change_pct'], 1) if r else None})
        ui.table(pd.DataFrame(rows))
        st.markdown('**D0 보조 지표와 기존 판정**')
        prof = []
        for u in ordered:
            m = an.series_metrics(rev_total, u, n, sg_t, an.variability_reference(rev_total, ctx.upd_dates, n))
            rr_ = m['ratios'] or {}
            prof.append({'날짜': u['date'], 'D0 배수': fx(rr_.get(0)), 'D0 (7일 전 같은 요일 대비)': fx(m['d0_same_weekday']),
                         'D0 (사전 상승 제외 기저)': fx(m['d0_alt']) if m['d0_alt'] else '-', 'D1 배수': fx(rr_.get(1)), 'D2 배수': fx(rr_.get(2)),
                         'D+6 배수': fx(rr_.get(6)), 'D0 기존 판정': m['d0_judge'], f'{n}일 변화 범위': fmt_range(m['lo'], m['hi']),
                         '기저 진단': m['direction'], '기존 판정(일별 변동 기준)': m['judge']})
        ui.table(pd.DataFrame(prof))
        if sg_t:
            st.caption(f'기존 판정 = 일별 변동 약 {sg_t * 100:.1f}%와 비교한 참고값입니다. 7일 변화율의 판정 기준으로는 부적절할 수 있어 비교용으로만 남겼습니다.')
        st.markdown('**기저 방식별 상세값**')
        det = []
        for u in ordered:
            m = an.series_metrics(rev_total, u, n, sg_t, None)
            for k, v in m['baselines'].items():
                note = '기본 기저' if k == an.BASE_MEAN else ('보조 (불안정 가능)' if k.startswith(an.BASE_TREND) else '대안 기저')
                if k.startswith(an.BASE_TREND) and m['trend_loo']:
                    note += f" · 직전 값 1개씩 빼면 {m['trend_loo'][0]:+.0f}% ~ {m['trend_loo'][1]:+.0f}%"
                det.append({'날짜': u['date'], '기저 방식': k, '변화율(%)': round(v, 1), '비고': note})
        ui.table(pd.DataFrame(det))
        st.markdown('**DAU 합계 (집계 범위 구분)**')
        drows = []
        for scope, ser in (('파일 전체 (개별 국가 + 기타)', dau_total), (f'공통 {len(ctx.common)}개국', common_dau)):
            sgd = an.daily_noise_sigma(ser, ctx.upd_dates)
            for u in ordered:
                m = an.series_metrics(ser, u, n, sgd, None)
                rr_ = m['ratios'] or {}
                drows.append({'집계 범위': scope, '날짜': u['date'], 'D0 배수': fx(rr_.get(0)), 'D+3 배수': fx(rr_.get(3)),
                              'D+6 배수': fx(rr_.get(6)), f'{n}일 변화 범위': fmt_range(m['lo'], m['hi']), '기저 진단': m['direction'],
                              '기존 판정(일별 변동 기준)': m['judge']})
        ui.table(pd.DataFrame(drows))
        st.caption('DAU는 매출과 집계 범위(국가·플랫폼)가 같은지 확인되지 않았습니다. 매출과 결합한 지표(ARPDAU 등)는 계산하지 않습니다.')
        thr = st.slider('동시 상승 판정 배수 (D0 기준)', 1.1, 2.0, 1.3, 0.05, key='cmp_thr')
        brow = []
        for u in ordered:
            valid = [c for c in ctx.rev_countries if an.profile(ctx.rev[c], u['date'], n)[1]]
            up = [c for c in valid if not np.isnan(an.profile(ctx.rev[c], u['date'], n)[1][0]) and an.profile(ctx.rev[c], u['date'], n)[1][0] >= thr]
            brow.append({'날짜': u['date'], f'D0 ≥ ×{thr:.2f}인 국가': f'{len(up)} / {len(valid)}개국', '해당 국가': ', '.join(up) or '-'})
        ui.table(pd.DataFrame(brow))
        st.caption('여러 국가가 동시에 오르면 공통 요인의 단서일 수 있으나 원인을 확정하지 않습니다.')
