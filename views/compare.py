"""업데이트 비교 — 등록된 업데이트를 달력 주(월~일) 기준으로 나란히 봅니다."""
import pandas as pd
import streamlit as st

import analysis as an
import charts
import report
import ui
from ui import fmt_range, fp, fx


def render(env):
    ctx, n, ups, d_sel = env.ctx, env.window, env.project.updates, env.upd['date']
    cur_l, prev_l = report.cal_period_labels()
    st.caption(f'비교 기준: {prev_l}(직전 월–일) 대비 {cur_l}(D0 포함 월–일) · 집계 범위: {env.rep["scope_label"]}')
    rs, ds = ctx.series(env.scope)

    # ── 추정 매출 ──
    rows, labs, prevs, curs = [], [], [], []
    for u in ups:
        w = an.week_compare_cal(rs, u['date'])
        lab = u['date'][5:]
        labs.append(lab)
        prevs.append(w['prev_sum'] * ui.KRW_RATE / 1e8 if w else None)
        curs.append(w['cur_sum'] * ui.KRW_RATE / 1e8 if w else None)
        rows.append({'날짜': u['date'], '업데이트': u['title'],
                     f'{prev_l} 추정 매출 합계': ui.fmt_krw(w['prev_sum'] if w else None),
                     f'{cur_l} 추정 매출 합계': ui.fmt_krw(w['cur_sum'] if w else None),
                     '증감액': ui.fmt_krw_delta(w['cur_sum'] - w['prev_sum'] if w else None),
                     '증감률': fp(w['pct']) if w else '분석 불가'})
    no_data = [u['date'][5:] for u in ups if an.week_compare_cal(rs, u['date']) is None]
    with st.container(key='card_cmp_rev'):
        ui.card_title('추정 매출', f'{cur_l} 합계 vs {prev_l} 합계 · 원화 환산 (1 USD = 1,350원) · {env.rep["rev_scope_label"]}')
        ui.table(pd.DataFrame(rows))
        ui.show(charts.fig_group_bars(labs, prevs, curs, prev_l, cur_l, charts.BLUE, unit='억원'))
        if no_data:
            st.caption(f'막대가 없는 업데이트 ({", ".join(no_data)}): 달력 기준 전주(월~일) 7일이 CSV 데이터 범위 밖이라 비교 불가입니다. 해당 날짜의 직전 월~일 데이터를 CSV에 추가하면 계산됩니다.')

    # ── DAU ──
    rows, prevs, curs = [], [], []
    for u in ups:
        w = an.week_compare_cal(ds, u['date'])
        prevs.append(w['prev_mean'] if w else None)
        curs.append(w['cur_mean'] if w else None)
        rows.append({'날짜': u['date'], '업데이트': u['title'],
                     f'{prev_l} 일평균 DAU': f"{w['prev_mean']:,.0f}" if w else '분석 불가',
                     f'{cur_l} 일평균 DAU': f"{w['cur_mean']:,.0f}" if w else '분석 불가',
                     '증감률': fp(w['pct']) if w else '분석 불가'})
    with st.container(key='card_cmp_dau'):
        ui.card_title('DAU', f'{cur_l} 일평균 DAU vs {prev_l} 일평균 DAU · {env.rep["dau_scope_label"]}')
        ui.table(pd.DataFrame(rows))
        ui.show(charts.fig_group_bars(labs, prevs, curs, prev_l, cur_l, charts.GREEN))
        st.caption(report.DAU_NOTE + ' 매출과 결합한 지표(ARPDAU 등)는 계산하지 않습니다.')

    # ── 국가별 매출 비교 (날짜별 금액 / 증감률) ──
    with st.container(key='card_cmp_country'):
        ui.card_title('국가별 추정 매출', f'업데이트 주 금액(원화 환산) 및 증감률 — 증감률만으로 판단하지 말고 규모를 함께 보세요')
        dates = [u['date'][5:] for u in ups]
        mi_cols = pd.MultiIndex.from_tuples(
            [('국가', '')] + [(d, s) for d in dates for s in ['금액', '증감률']]
        )
        # 모든 업데이트 주에 완전한 데이터가 있는 국가만 표시
        complete_countries = [c for c in ctx.rev_countries
                              if all(an.week_compare_cal(ctx.rev[c], u['date']) is not None for u in ups)]
        data = []
        for c in complete_countries:
            row_data = [c + ('' if c in ctx.dau_countries else ' (매출만)')]
            for u in ups:
                w = an.week_compare_cal(ctx.rev[c], u['date'])
                row_data.append(ui.fmt_krw(w['cur_sum']))
                row_data.append(f"{w['pct']:+.1f}%" if w['pct'] is not None else '-')
            data.append(row_data)

        if not data:
            st.info('비교 가능한 국가 데이터 없음')
        else:
            df_c = pd.DataFrame(data, columns=mi_cols)

            def _style_pct(v):
                try:
                    pct = float(str(v).replace('%', '').replace('+', '').strip())
                    return 'color: #c0504d; font-weight: 700' if pct > 0 else ('color: #2f5bea; font-weight: 700' if pct < 0 else '')
                except (ValueError, AttributeError):
                    return ''

            pct_cols = [(d, '증감률') for d in dates]
            st.dataframe(df_c.style.map(_style_pct, subset=pct_cols), use_container_width=True)
        st.caption('소규모 국가는 일 규모가 작아 증감률의 변동이 큽니다.')
