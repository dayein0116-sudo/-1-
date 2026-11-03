"""전체 개요 — 프로젝트·데이터 소개, 국가별 데이터 보유 현황, 지표 정의, 분석의 한계.
누적 매출·전체 일별 그래프는 참고용으로만 두고 메인 화면에서는 뺐습니다."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import charts
import ui


def render(env):
    p, ctx, data = env.project, env.ctx, env.data
    st.subheader(f'{p.name} — 분석 데이터 개요')
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(ui.kpi('분석 기간 (매출)', f'{ctx.rev.index.min():%m/%d} ~ {ctx.rev.index.max():%m/%d}', f'{len(ctx.rev)}일', 'blue', small=True), unsafe_allow_html=True)
    c2.markdown(ui.kpi('등록된 업데이트', f'{len(p.updates)}건', ', '.join(u['date'][5:] for u in p.updates), 'purple'), unsafe_allow_html=True)
    c3.markdown(ui.kpi('공통 개별 국가', f'{len(ctx.common)}개', '매출·DAU 파일 모두에 있는 국가', 'green'), unsafe_allow_html=True)
    c4.markdown(ui.kpi('데이터 출처', p.meta.get('data_source', '-'), '추정치이며 실측이 아닙니다', 'navy', small=True), unsafe_allow_html=True)

    _known = set(ctx.rev_countries) | set(ctx.dau_countries)
    _csv_srcs = {'매출 CSV', 'DAU CSV', '업로드 매출 CSV', '업로드 DAU CSV'}

    def _critical(r):
        if r['대상'] in _csv_srcs:
            col = r['내용'].split(':')[0].strip()
            if col in _known and col not in ctx.common:
                return False
        return True

    warns = [r for r in ui.data_checks(p, data, ctx, env.window)
             if r['수준'] == '경고' and _critical(r)]
    if warns:
        st.warning('**데이터 경고** — 분석 신뢰성에 영향이 있을 수 있습니다.\n\n' +
                   '\n'.join(f'- **{r["대상"]}**: {r["내용"]}' for r in warns))

    st.markdown('#### 국가별 데이터 보유 현황')
    names = sorted(set(ctx.rev.columns) | set(ctx.dau.columns), key=lambda c: (c == '기타', c))
    rows = []
    for c in names:
        row = {'국가': c}
        for df, lab in ((ctx.rev, '매출'), (ctx.dau, 'DAU')):
            if c in df:
                s = df[c].dropna()
                row[lab] = f'{s.index.min():%m/%d}~{s.index.max():%m/%d} ({len(s)}일)' if len(s) else '값 없음'
            else:
                row[lab] = '없음'
        row['분석 취급'] = '개별 국가 (공통)' if c in ctx.common else ('기타 — 개별 국가 아님' if c == '기타' else '매출만' if c in ctx.rev_countries else 'DAU만')
        rows.append(row)
    ui.table(pd.DataFrame(rows))
    st.caption(f'매출 파일: 개별 국가 {len(ctx.rev_countries)}개 + 기타 · DAU 파일: 개별 국가 {len(ctx.dau_countries)}개 + 기타. 기타는 개별 국가로 취급하지 않습니다.')

    st.markdown('#### 지표 정의와 한계')
    st.markdown(
        '- **추정 매출**: Sensor Tower 추정치. 원본 CSV 통화는 USD이며, 표시는 1 USD = 1,350원 환산(고정 환율). 플랫폼·집계 범위는 확인되지 않았습니다.\n'
        '- **증감**: 증감액 = 이후 7일 − 이전 7일, 증감률 = 이후 7일 ÷ 이전 7일 − 1. D0를 7일 전 같은 요일과 비교하는 값은 하루 단위 참고값입니다. 요일 구성이 같아도 추세·연휴·프로모션 영향은 남아 있습니다.\n'
        '- **DAU**: 국가별 DAU 추정치를 같은 날짜끼리 더한 값이며 중복 이용자 제거 여부는 확인되지 않아 고유 이용자 수가 아닙니다. 기간 합계는 의미가 없어 일평균으로 비교합니다.\n'
        '- **집계 범위**: "공통 N개국 합산"은 매출·DAU 파일 모두에 있는 국가만, "파일 전체 합계"는 기타 등을 포함합니다. 두 지표를 결합한 값(ARPDAU 등)은 계산하지 않습니다.\n'
        f'- {p.meta.get("data_note", "")}')

    with st.expander('전체 기간 일별 추정 매출·DAU (참고용)'):
        rev_total, dau_total = ctx.rev.sum(axis=1, min_count=1), ctx.dau.sum(axis=1, min_count=1)
        rev_krw = rev_total * ui.KRW_RATE / 1e8
        for s, title, suffix in (
                (rev_krw, '일별 추정 매출 (원화 환산 억 원, 파일 전체 합계)', '억원'),
                (dau_total, '일별 DAU (파일 전체 합계 — 매출 국가 범위와 다를 수 있음)', '명')):
            fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode='lines', line=dict(color=charts.BLUE)))
            fig.update_layout(title=title, height=300, margin=dict(l=8, r=8, t=40, b=8),
                              yaxis=dict(ticksuffix=suffix))
            st.plotly_chart(ui.mark_updates(fig, p.updates), width='stretch', config={'displayModeBar': False})
