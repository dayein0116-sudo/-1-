"""국가별 — 국가 1개를 골라 업데이트별 (전주 vs 업데이트 주)을 봅니다."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import charts
import report
import ui
from ui import fp


def _tag(ctx, c):
    if c in ctx.rev and c not in ctx.dau:
        return f'{c} (매출만)'
    if c in ctx.dau and c not in ctx.rev:
        return f'{c} (DAU만)'
    return c


def render(env):
    ctx, n, ups = env.ctx, env.window, env.project.updates
    cur_l, prev_l = report.cal_period_labels()
    d_upd = env.upd['date']

    def _available(c):
        if c in ctx.common:
            return True
        if c in ctx.dau.columns and c not in ctx.rev.columns:
            return an.week_compare_cal(ctx.dau[c], d_upd) is not None
        if c in ctx.rev.columns and c not in ctx.dau.columns:
            return an.week_compare_cal(ctx.rev[c], d_upd) is not None
        return True

    avail_countries = [c for c in ctx.display_countries if _available(c)]
    country = st.selectbox('국가', avail_countries, format_func=lambda c: _tag(ctx, c), key='country_sel')
    st.caption('매출만 있거나 DAU만 있는 국가는 있는 지표만 표시합니다. "기타"는 개별 국가가 아니라 제외합니다. 소규모 국가는 변동이 커서 증감률만으로 비교하지 않습니다. 국가별 DAU는 원본 수치 그대로이며, 합산하지 않은 국가 단독 값입니다.')
    for key, df, lab, unit in (('rev', ctx.rev, '매출', '합계'), ('dau', ctx.dau, 'DAU', '일평균')):
        if country not in df:
            st.warning(f'{country}은(는) {"매출" if key == "rev" else "DAU"} 파일에 없어 해당 지표는 분석 불가입니다.')
            continue
        ser = df[country]
        rows, labs, prevs, curs = [], [], [], []
        for u in ups:
            w = an.week_compare_cal(ser, u['date'])
            mult = (ui.KRW_RATE / 1e8) if key == 'rev' else (1 / 7)
            labs.append(u['date'][5:])
            prevs.append(w['prev_sum'] * mult if w else None)
            curs.append(w['cur_sum'] * mult if w else None)
            rows.append({'업데이트': u['date'],
                         f'{prev_l} {unit}': (ui.fmt_krw(w['prev_sum']) if key == 'rev' else f"{w['prev_sum'] * mult:,.0f}명") if w else '분석 불가',
                         f'{cur_l} {unit}': (ui.fmt_krw(w['cur_sum']) if key == 'rev' else f"{w['cur_sum'] * mult:,.0f}명") if w else '분석 불가',
                         '증감액': (ui.fmt_krw_delta(w['cur_sum'] - w['prev_sum']) if key == 'rev' else f"{(w['cur_sum'] - w['prev_sum']) * mult:+,.0f}명") if w else '분석 불가',
                         '증감률': fp(w['pct']) if w else '분석 불가'})
        with st.container(key=f'card_ctry_{key}'):
            ui.card_title(f'{country} · {lab}', f'{cur_l} {unit} vs {prev_l} {unit} · {"원화 환산 (1 USD = 1,350원)" if key == "rev" else "원본 단위"}')
            c1, c2 = st.columns([1.2, 1])
            with c1:
                ui.show(charts.fig_group_bars(labs, prevs, curs, prev_l, cur_l, charts.BLUE if key == 'rev' else charts.GREEN, unit='억원' if key == 'rev' else '명'))
            with c2:
                ui.table(pd.DataFrame(rows))

    with st.expander('일별 추이 (전체 기간)'):
        t1, t2 = st.columns(2)
        for col, df, lab in ((t1, ctx.rev, '매출'), (t2, ctx.dau, 'DAU')):
            if country in df:
                line_color = charts.BLUE if lab == '매출' else charts.GREEN
                fig = go.Figure(go.Scatter(x=df.index, y=df[country], mode='lines', line=dict(color=line_color)))
                fig.update_layout(title=f'{country} 일별 {lab}', height=300, margin=dict(l=8, r=8, t=40, b=8))
                fig.update_xaxes(type='date', tickformat='%Y/%m')
                col.plotly_chart(ui.mark_updates(fig, ups), width='stretch', config={'displayModeBar': False})
        st.caption('점선: 업데이트 날짜 표시. 매출과 DAU는 단위·범위가 달라 결합하지 않습니다.')
