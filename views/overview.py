"""전체 개요 — 프로젝트·데이터 소개, 국가별 데이터 보유 현황, 지표 정의, 분석의 한계.
누적 매출·전체 일별 그래프는 참고용으로만 두고 메인 화면에서는 뺐습니다."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analysis
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
        with st.expander('데이터 품질 상세', expanded=False):
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

    with st.expander('전체 기간 일별 매출·DAU (참고용)'):
        rev_total, dau_total = ctx.rev.sum(axis=1, min_count=1), ctx.dau.sum(axis=1, min_count=1)
        rev_krw = rev_total * ui.KRW_RATE / 1e8
        for s, title, suffix in (
                (rev_krw, '일별 매출 (원화 환산 억 원, 파일 전체 합계)', '억원'),
                (dau_total, '일별 DAU (파일 전체 합계 — 매출 국가 범위와 다를 수 있음)', '명')):
            fig = go.Figure(go.Scatter(x=s.index, y=s.values, mode='lines', line=dict(color=charts.BLUE)))
            fig.update_layout(title=title, height=300, margin=dict(l=8, r=8, t=40, b=8),
                              yaxis=dict(ticksuffix=suffix))
            st.plotly_chart(ui.mark_updates(fig, p.updates), width='stretch', config={'displayModeBar': False})

    # ── 매출 추세 진단 ─────────────────────────────────────────
    st.markdown('---')
    st.markdown('#### 매출 추세 진단')
    st.caption('관측 기간 내 전체 매출 흐름 — 개별 업데이트 반응이 아닌 중기 추세를 확인합니다.')

    _upd_dates = [u['date'] for u in p.updates]
    _rev = ctx.rev.sum(axis=1, min_count=1)
    _dau = ctx.dau.sum(axis=1, min_count=1)
    _ts = analysis.revenue_trend_stats(_rev, _upd_dates)
    _bs = analysis.baseline_level(_rev, _upd_dates)
    _pers = analysis.rebound_persistence_all(_rev, _upd_dates)
    _cc = analysis.country_half_compare(ctx.rev, ctx.common)
    _ds = analysis.revenue_trend_stats(_dau, _upd_dates)
    _h = _ts.get('half_days', 21)

    # A-1: 추세 차트 + 7일 이동평균
    _ma7 = _rev.rolling(7, center=True, min_periods=4).mean()
    _rev_krw = _rev * ui.KRW_RATE / 1e8
    _ma_krw = _ma7 * ui.KRW_RATE / 1e8
    _fig = go.Figure()
    _fig.add_trace(go.Scatter(x=_rev_krw.index, y=_rev_krw.values, mode='lines',
                               name='일별 매출', line=dict(color='rgba(99,110,250,0.35)', width=1)))
    _fig.add_trace(go.Scatter(x=_ma_krw.index, y=_ma_krw.values, mode='lines',
                               name='7일 이동평균 (추세 참고)', line=dict(color=charts.BLUE, width=2.5)))
    _fig.update_layout(height=300, margin=dict(l=8, r=8, t=40, b=60),
                        title='일별 매출 · 7일 이동평균 (파일 전체 합계, 억 원)',
                        yaxis=dict(ticksuffix='억원'),
                        legend=dict(orientation='h', yanchor='top', y=-0.25, x=0.5, xanchor='center'))
    st.plotly_chart(ui.mark_updates(_fig, p.updates), width='stretch', config={'displayModeBar': False})
    if _ts['can_compare']:
        st.markdown(
            f'초반 **{_h}일** ({_ts["first_start"]:%m/%d}–{_ts["first_end"]:%m/%d}) 일평균 **\\${_ts["first_mean"]:,.0f}** · '
            f'후반 **{_h}일** ({_ts["last_start"]:%m/%d}–{_ts["last_end"]:%m/%d}) 일평균 **\\${_ts["last_mean"]:,.0f}** '
            f'({_ts["change_pct"]:+.1f}%)'
        )
    st.caption(f'※ 7일 이동평균은 추세 시각화용이며 단독으로 원인을 판정하지 않습니다. 초반·후반은 각 {_h}일({_h // 7}주)로 요일 구성이 같습니다.')

    # A-2: 업데이트 기간을 제외한 평소 매출 수준
    st.markdown('**업데이트 기간을 제외한 평소 매출 수준**')
    if _bs['can_compute']:
        st.markdown(
            f'각 업데이트 D-2–D+6 제외 후 비연속적으로 남은 **{_bs["day_count"]}일** · '
            f'일평균 **\\${_bs["mean"]:,.0f}** '
            f'({_bs["date_min"]:%m/%d}–{_bs["date_max"]:%m/%d} 범위에 분포)'
        )
    else:
        st.warning(_bs['reason'])

    # A-3: 반응 지속성 (D0–D2 vs D3–D6, 평균 대 평균)
    st.markdown('**업데이트 이후 매출 반응 변화** (D0–D2 초기 vs D3–D6 후기 — 직전 7일 대비 배수, 평균)')
    _prows = []
    for _r in _pers:
        _pd = _r['persistence']
        if _pd:
            _prows.append({'업데이트': _r['date'],
                            'D0–D2 (초기 3일)': f"{_pd['early']:.2f}배",
                            'D3–D6 (이후 4일)': f"{_pd['late']:.2f}배",
                            '후기/초기 (배수)': f"{_pd['retention']:.2f}배" if _pd['retention'] is not None else '-'})
        else:
            _prows.append({'업데이트': _r['date'], 'D0–D2 (초기 3일)': '자료 부족', 'D3–D6 (이후 4일)': '-', '후기/초기 (배수)': '-'})
    ui.table(pd.DataFrame(_prows))
    st.caption('1.0 미만이 반드시 반응 실패를 뜻하지 않습니다 — 직전 추세가 하락 중이면 1.0 이상 반응도 추세 연장일 수 있습니다.')

    # A-4: 매출 vs DAU 추세
    st.markdown('**매출 vs DAU 추세 비교**')
    if _ts['can_compare'] and _ds['can_compare']:
        _rev_dir = '감소' if _ts['change_pct'] < -5 else ('증가' if _ts['change_pct'] > 5 else '보합')
        _dau_dir = '감소' if _ds['change_pct'] < -5 else ('증가' if _ds['change_pct'] > 5 else '보합')
        st.markdown(
            f'초반→후반 {_h}일: 매출 {_ts["change_pct"]:+.1f}% (**{_rev_dir}**) · DAU {_ds["change_pct"]:+.1f}% (**{_dau_dir}**)'
        )
        if _rev_dir == _dau_dir:
            st.caption('매출과 DAU가 같은 방향으로 변화했습니다. 이용자 수 변화가 매출 변화와 연동되어 있을 가능성이 있으나, 1인당 매출 기여는 별도 확인이 필요합니다.')
        else:
            st.caption('매출과 DAU의 방향이 다릅니다. 이용자 수와 무관한 구매 행동 변화 가능성이 있습니다.')
    else:
        st.caption('데이터 기간이 짧아 비교 불가')

    # A-5: 공통 국가별 매출 변화
    st.markdown(f'**공통 국가별 매출 변화** ({len(ctx.common)}개국 · 초반 vs 후반 각 {_h}일 평균)')
    if _cc:
        _crows = []
        for _c, _cr in _cc.items():
            if _cr['can_compare']:
                _crows.append({'국가': _c, '초반 일평균 (USD)': f'${_cr["first_mean"]:,.0f}',
                                '후반 일평균 (USD)': f'${_cr["last_mean"]:,.0f}',
                                '변화율': f'{_cr["change_pct"]:+.1f}%'})
            else:
                _crows.append({'국가': _c, '초반 일평균 (USD)': '-', '후반 일평균 (USD)': '-',
                                '변화율': _cr.get('reason', '비교 불가')})
        ui.table(pd.DataFrame(_crows))

    # Feature B: 사업적 시사점 (Python 계산 기반)
    with st.expander('매출 추세 사업적 시사점 (Python 계산 기반)', expanded=False):
        st.markdown('**핵심 진단**')
        if _ts['can_compare']:
            _chg = _ts['change_pct']
            _fm, _lm = f'${_ts["first_mean"]:,.0f}', f'${_ts["last_mean"]:,.0f}'
            if _chg < -15:
                st.markdown(f'초반 {_h}일({_ts["first_start"]:%m/%d}~{_ts["first_end"]:%m/%d}) 일평균 {_fm} 대비 후반 {_h}일({_ts["last_start"]:%m/%d}~{_ts["last_end"]:%m/%d}) 일평균 {_lm}로 **{_chg:+.1f}%** 차이가 관측됩니다.')
            elif _chg > 15:
                st.markdown(f'초반 {_h}일 일평균 {_fm} 대비 후반 {_h}일 일평균 {_lm}로 **{_chg:+.1f}%** 차이가 관측됩니다.')
            else:
                st.markdown(f'초반·후반 {_h}일 간 뚜렷한 방향성이 확인되지 않습니다 ({_chg:+.1f}%).')
        else:
            st.markdown(_ts['reason'])

        st.markdown('**확인된 현상**')
        _obs = []
        if _ts['can_compare']:
            _obs.append(f'매출 초반→후반 {_ts["change_pct"]:+.1f}% (각 {_h}일 평균 · 요일 구성 균등)')
        if _bs['can_compute']:
            _obs.append(f'업데이트 기간 제외 평소 매출 수준: \\${_bs["mean"]:,.0f}/일 ({_bs["day_count"]}일 샘플)')
        if _ds['can_compare']:
            _obs.append(f'DAU 초반→후반 {_ds["change_pct"]:+.1f}%')
        _n_p = sum(1 for _r in _pers if _r['has_data'])
        _obs.append(f'반응 지속성 계산 가능 업데이트: {_n_p}/{len(_pers)}건')
        for _item in _obs:
            st.markdown(f'- {_item}')

        st.markdown('**가능한 사업적 해석**')
        _interps = ['아래 해석은 관측된 수치에서 도출한 가능성이며 인과 관계가 아닙니다.']
        if _ts['can_compare'] and _ts['change_pct'] < -15 and _ds['can_compare'] and _ds['change_pct'] < -15:
            _interps.append('매출·DAU가 모두 감소 방향이므로, 이용자 수 감소가 매출 감소의 주요 경로 중 하나일 가능성이 있습니다.')
            _interps.append('신규 게임 출시 직후 자연 하락인지 구조적 감소인지는 더 긴 비교 기간과 외부 비교군 없이는 판별하기 어렵습니다.')
        elif _ts['can_compare'] and _ts['change_pct'] < -15:
            _interps.append('DAU 대비 매출 하락폭이 크다면 이용자 1인당 구매 감소 가능성이 있으나 별도 확인이 필요합니다.')
        for _item in _interps:
            st.markdown(f'- {_item}')

        st.markdown('**추가 확인 필요 사항**')
        for _item in [
            '비교 기간 외 장기 추세 — 현재 관측 기간만으로 구조적 감소/증가를 단정할 수 없습니다.',
            '동일 장르 타 게임과의 비교 — 시장 전체 추세와 개별 게임 추세를 구분해야 합니다.',
            '이용자 1인당 매출 변화 — 이용자 수 감소와 구매율 감소를 분리하려면 별도 집계가 필요합니다.',
            '코호트별 잔존율·복귀율 — 신규·복귀·기존 이용자 비중 변화가 매출 구조에 영향을 미칩니다.',
        ]:
            st.markdown(f'- {_item}')
        st.caption('※ Python으로 계산한 수치를 기반으로 자동 생성됩니다. AI 연동 없음.')
