"""국가별 — 국가 1개를 골라 업데이트 주기별 성과를 봅니다."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis as an
import charts
import ui
from ui import fp


def _tag(ctx, c):
    if c in ctx.rev and c not in ctx.dau:
        return f'{c} (매출만)'
    if c in ctx.dau and c not in ctx.rev:
        return f'{c} (DAU만)'
    return c


def render(env):
    ctx, ups = env.ctx, env.project.updates
    rev_cycles = env.rev_cycles
    dau_cycles = env.dau_cycles
    pre_range = env.pre_period  # {'d_start','d_end',...} or None — 날짜 범위를 국가별 계산에 재사용

    avail_countries = ctx.display_countries
    country = st.selectbox('국가', avail_countries, format_func=lambda c: _tag(ctx, c), key='country_sel')
    st.caption('매출만 있거나 DAU만 있는 국가는 있는 지표만 표시합니다. "기타"는 개별 국가가 아니라 제외합니다. 소규모 국가는 변동이 커서 증감률만으로 비교하지 않습니다. 국가별 DAU는 원본 수치 그대로이며, 합산하지 않은 국가 단독 값입니다.')
    st.caption('비교 기준: 업데이트 주기(D0~다음D0-1) 기준 · 직전 주기 대비 · 변화율은 일평균 매출 기준')

    # ── 매출 ──
    if country not in ctx.rev:
        st.warning(f'{country}은(는) 매출 파일에 없어 매출 분석 불가입니다.')
    else:
        ccs = an.cycle_compare_country(ctx.rev[country], rev_cycles, pre_range)
        rows, labs, prevs, curs = [], [], [], []
        for cc in ccs:
            star = '*' if not cc['complete'] else ''
            labs.append(cc['date'][5:] + star)
            curs.append(cc['daily_avg'] * ui.KRW_RATE / 1e8 if cc['daily_avg'] is not None else None)
            prevs.append(cc['prev_daily_avg'] * ui.KRW_RATE / 1e8 if cc['prev_daily_avg'] is not None else None)
            if cc['can_compare']:
                change_str = f"{cc['change_pct']:+.1f}%"
                delta_str = ui.fmt_krw_delta(cc['daily_avg'] - cc['prev_daily_avg'])
            elif not cc['complete']:
                change_str = '비교 불가 — 주기 미완료'
                delta_str = '-'
            else:
                change_str = '비교 기준 없음'
                delta_str = '-'
            rows.append({
                '날짜': cc['date'],
                '기간': f"{cc['d_start'][5:]}~{cc['d_end'][5:]}",
                '일수': f"{cc['valid_days']}/{cc['days']}일",
                '직전주기 합계': ui.fmt_krw(cc['prev_total']),
                '직전주기 일평균': ui.fmt_krw(cc['prev_daily_avg']),
                '이번주기 합계': ui.fmt_krw(cc['total']),
                '이번주기 일평균': ui.fmt_krw(cc['daily_avg']),
                '일평균 증감액': delta_str,
                '일평균 증감률': change_str,
            })
        with st.container(key='card_ctry_rev'):
            ui.card_title(f'{country} · 매출',
                          '업데이트 주기별 · 직전 주기 대비 일평균 증감률 · 원화 환산 (1 USD = 1,350원)')
            c1, c2 = st.columns([1.2, 1])
            with c1:
                ui.show(charts.fig_group_bars(labs, prevs, curs,
                                              '직전 주기 일평균', '이번 주기 일평균', charts.BLUE, unit='억원'))
            with c2:
                ui.table(pd.DataFrame(rows))

    # ── DAU ──
    if country not in ctx.dau:
        st.warning(f'{country}은(는) DAU 파일에 없어 DAU 분석 불가입니다.')
    else:
        ccs_d = an.cycle_compare_country(ctx.dau[country], dau_cycles, pre_range)
        rows_d, labs_d, prevs_d, curs_d = [], [], [], []
        for cc in ccs_d:
            star = '*' if not cc['complete'] else ''
            labs_d.append(cc['date'][5:] + star)
            curs_d.append(cc['daily_avg'])
            prevs_d.append(cc['prev_daily_avg'])
            if cc['can_compare']:
                change_str = f"{cc['change_pct']:+.1f}%"
                delta = cc['daily_avg'] - cc['prev_daily_avg']
                delta_str = f"{delta:+,.0f}명"
            elif not cc['complete']:
                change_str = '비교 불가 — 주기 미완료'
                delta_str = '-'
            else:
                change_str = '비교 기준 없음'
                delta_str = '-'
            rows_d.append({
                '날짜': cc['date'],
                '기간': f"{cc['d_start'][5:]}~{cc['d_end'][5:]}",
                '일수': f"{cc['valid_days']}/{cc['days']}일",
                '직전주기 일평균 DAU': ui.fmt_dau(cc['prev_daily_avg']),
                '이번주기 일평균 DAU': ui.fmt_dau(cc['daily_avg']),
                '증감 인원': delta_str,
                '증감률': change_str,
            })
        with st.container(key='card_ctry_dau'):
            ui.card_title(f'{country} · DAU', '업데이트 주기별 일평균 DAU · 직전 주기 대비')
            c1, c2 = st.columns([1.2, 1])
            with c1:
                ui.show(charts.fig_group_bars(labs_d, prevs_d, curs_d,
                                              '직전 주기 일평균', '이번 주기 일평균', charts.GREEN))
            with c2:
                ui.table(pd.DataFrame(rows_d))

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
