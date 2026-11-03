"""Plotly 차트 생성 (Streamlit 의존 없음). 관측값만 그리며 값을 보간하거나 새로 만들지 않습니다."""
import numpy as np
import pandas as pd
import plotly.graph_objects as go

BLUE, GREEN, PURPLE, NAVY, GRAY = '#2f5bea', '#19b37a', '#6b4fd8', '#16254d', '#9aa5c4'
FONT = dict(family="Pretendard, 'Noto Sans KR', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif", color=NAVY, size=13)
OFFSETS = list(range(-2, 7))


def _label(k):
    return 'D0' if k == 0 else f'D{k:+d}'.replace('+', '+')


def _base_layout(fig, height):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8), font=FONT, paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)', hoverlabel=dict(font=FONT))
    return fig


def fig_response(rev_ratios, dau_ratios, rev_alt=None, alt_name='', rev_name='추정 매출 배수', dau_name='DAU 배수'):
    """D-2~D+6 일별 값을 '직전 N일 평균 = 1.0' 배수로 표시. 관측된 날짜의 점만 사용합니다."""
    fig = go.Figure()
    fig.add_vrect(x0=-0.5, x1=2.5, fillcolor=PURPLE, opacity=0.08, line_width=0)
    fig.add_hline(y=1.0, line_dash='dot', line_color=GRAY, line_width=1)
    top = 1.2

    def add(ratios, name, color, label_ks, pos, dash=None, show_text=True):
        nonlocal top
        if not ratios:
            return
        xs = [k for k in OFFSETS if k in ratios and not np.isnan(ratios[k])]
        ys = [ratios[k] for k in xs]
        if ys:
            top = max(top, max(ys))
        text = [f'×{ratios[k]:.2f}' if (show_text and k in label_ks) else '' for k in xs]
        fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode='lines+markers+text', text=text, textposition=pos,
                                 textfont=dict(color=color, size=12), line=dict(color=color, width=2.5, dash=dash),
                                 marker=dict(size=7), connectgaps=False,
                                 hovertemplate='%{customdata}: ×%{y:.2f}<extra>' + name + '</extra>', customdata=[_label(k) for k in xs]))

    add(rev_ratios, rev_name, BLUE, (0, 1, 2, 6), 'top center')
    add(rev_alt, alt_name, '#8aa6f2', (), 'top center', dash='dash', show_text=False) if rev_alt else None
    add(dau_ratios, dau_name, GREEN, (6,), 'bottom center')
    fig.update_xaxes(tickmode='array', tickvals=OFFSETS, ticktext=[_label(k) for k in OFFSETS], showgrid=False, zeroline=False)
    lows = [v for r in (rev_ratios, dau_ratios, rev_alt) if r for k, v in r.items() if k in OFFSETS and not np.isnan(v)]
    # 값의 폭이 좁은 지표(DAU 등)는 축을 0에서 시작하면 변화가 보이지 않으므로 확대합니다 (기준선 ×1.0은 항상 표시).
    lo = 0 if (not lows or top > 2.5 or min(lows) < 0.5) else max(0.0, np.floor((min(lows) - 0.1) * 10) / 10)
    fig.update_yaxes(range=[lo, top * 1.2 if lo == 0 else top + 0.1], gridcolor='#e6eaf4', zeroline=False, tickformat='.1f')
    fig.update_layout(legend=dict(orientation='h', y=1.14, x=0, font=dict(size=12)))
    return _base_layout(fig, 340)


def fig_country_bars(values, color=BLUE, height=None):
    """values: {표시 이름: D0~D2 평균 배수 또는 None}. None은 그리지 않습니다 (분석 불가)."""
    items = sorted(((k, v) for k, v in values.items() if v is not None and not np.isnan(v)), key=lambda x: x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation='h', marker_color=color,
                           text=[f'×{v:.2f}' for _, v in items], textposition='outside', cliponaxis=False,
                           hovertemplate='%{y}: ×%{x:.2f}<extra></extra>'))
    fig.add_vline(x=1.0, line_dash='dot', line_color=GRAY, line_width=1)
    mx = max([v for _, v in items] + [1.0])
    fig.update_xaxes(range=[0, mx * 1.22], showgrid=True, gridcolor='#e6eaf4', zeroline=False, tickformat='.1f')
    fig.update_yaxes(showgrid=False)
    return _base_layout(fig, height or max(240, 34 * len(items) + 40))


ROLE_COLOR = {'기본': '#8fb0f7', '대안': BLUE, '보조 (참고)': '#b9bfe8'}


def fig_baseline(rows, height=300):
    """rows: report의 baseline_rows. 기저 방식별 7일 변화율 비교."""
    names = [f"{r['기저 방식'].replace(' (', '<br>(')}<br><sub>{r['구분']}</sub>" for r in rows]
    vals = [r['변화율(%)'] for r in rows]
    fig = go.Figure(go.Bar(x=names, y=vals, marker_color=[ROLE_COLOR.get(r['구분'], GRAY) for r in rows],
                           text=[f'{v:+.2f}%' for v in vals], textposition='outside', cliponaxis=False,
                           hovertemplate='%{y:+.2f}%<extra></extra>'))
    fig.add_hline(y=0, line_color=GRAY, line_width=1)
    lo, hi = min(vals + [0]), max(vals + [0])
    pad = (hi - lo) * 0.18 or 10
    fig.update_yaxes(range=[lo - (pad if lo < 0 else 0), hi + pad], gridcolor='#e6eaf4', ticksuffix='%', zeroline=False)
    fig.update_xaxes(showgrid=False)
    return _base_layout(fig, height)


def fig_overlay(series, title_y='배수', height=340):
    """series: [(이름, _, {offset: ratio})] — 업데이트별 D-2~D+6 반응을 겹쳐 그림. 관측값만 사용."""
    colors = [BLUE, PURPLE, GREEN, NAVY, GRAY]
    fig = go.Figure()
    fig.add_hline(y=1.0, line_dash='dot', line_color=GRAY, line_width=1)
    top = 1.2
    for i, (name, _, ratios) in enumerate(series):
        if not ratios:
            continue
        xs = [k for k in OFFSETS if k in ratios and not np.isnan(ratios[k])]
        ys = [ratios[k] for k in xs]
        top = max([top] + ys)
        fig.add_trace(go.Scatter(x=xs, y=ys, name=name, mode='lines+markers',
                                 line=dict(color=colors[i % len(colors)], dash='solid', width=2.2),
                                 marker=dict(size=6), customdata=[_label(k) for k in xs],
                                 hovertemplate='%{customdata}: ×%{y:.2f}<extra>' + name + '</extra>'))
    fig.update_xaxes(tickmode='array', tickvals=OFFSETS, ticktext=[_label(k) for k in OFFSETS], showgrid=False, zeroline=False)
    fig.update_yaxes(range=[0, top * 1.15], gridcolor='#e6eaf4', zeroline=False, title=title_y)
    fig.update_layout(legend=dict(orientation='h', y=1.16, x=0))
    return _base_layout(fig, height)


def fig_ranges(rows, height=300):
    """rows: [(라벨, 유형, lo, hi, primary)] — 기저별 변화율 범위(막대)와 기본 기저(마커)."""
    fig = go.Figure()
    for lab, _, lo, hi, prim in rows:
        if lo is None:
            continue
        fig.add_trace(go.Bar(x=[lab], y=[hi - lo], base=[lo], marker_color=BLUE, opacity=0.55, showlegend=False,
                             hovertemplate=f'{lo:+.2f}% ~ {hi:+.2f}%<extra>{lab}</extra>', width=0.45))
        if prim is not None:
            fig.add_trace(go.Scatter(x=[lab], y=[prim], mode='markers', marker=dict(color=NAVY, size=10, symbol='diamond'), showlegend=False,
                                     hovertemplate=f'기본 기저 {prim:+.2f}%<extra>{lab}</extra>'))
    fig.add_hline(y=0, line_color=GRAY, line_width=1)
    fig.update_yaxes(gridcolor='#e6eaf4', ticksuffix='%', zeroline=False)
    fig.update_xaxes(showgrid=False)
    return _base_layout(fig, height)


def fig_strip(data, height=300):
    """data: [(라벨, 유형, {국가: 배수})] — 국가별 D0~D2 평균 분포."""
    fig = go.Figure()
    for lab, _, vals in data:
        items = [(k, v) for k, v in vals.items() if v is not None and not np.isnan(v)]
        if not items:
            continue
        fig.add_trace(go.Scatter(x=[lab] * len(items), y=[v for _, v in items], mode='markers', text=[k for k, _ in items],
                                 marker=dict(color=BLUE, size=9, opacity=0.8), showlegend=False,
                                 hovertemplate='%{text}: ×%{y:.2f}<extra>' + lab + '</extra>'))
    fig.add_hline(y=1.0, line_dash='dot', line_color=GRAY, line_width=1)
    fig.update_yaxes(gridcolor='#e6eaf4', zeroline=False, title='D0~D2 평균 배수', rangemode='tozero')
    fig.update_xaxes(showgrid=False)
    return _base_layout(fig, height)


NEG = '#c0504d'


def fig_actual(series, date, n, color=BLUE, post=6, name='값', zero=True):
    """업데이트 전 n일 ~ D+post의 일별 실제 값. 점선 = 직전 n일 일평균. 관측된 날짜의 값만 그리며 보간하지 않습니다."""
    d = pd.Timestamp(date)
    s = series.dropna()
    w = s[(s.index >= d - pd.Timedelta(days=n)) & (s.index <= d + pd.Timedelta(days=post))]
    base = s[(s.index >= d - pd.Timedelta(days=n)) & (s.index < d)]
    fig = go.Figure()
    labels = []
    for x in w.index:
        k = (x - d).days
        labels.append('D0' if k == 0 else f'D{k:+d}')
    fig.add_trace(go.Scatter(x=w.index, y=w.values, mode='lines+markers', name=name, line=dict(color=color, width=2.5), marker=dict(size=6),
                             customdata=labels, hovertemplate='%{x|%m/%d} (%{customdata}): %{y:,.0f}<extra></extra>', showlegend=False))
    if len(base) == n:
        m = float(base.mean())
        fig.add_hline(y=m, line_dash='dash', line_color=GRAY, line_width=1.5,
                      annotation_text=f'직전 {n}일 일평균 {m:,.0f}', annotation_position='top left', annotation_font=dict(size=11, color='#66729a'))
    fig.add_vline(x=d.timestamp() * 1000, line_color=PURPLE, line_width=1.5, line_dash='dot')
    fig.add_annotation(x=d, y=1.0, yref='paper', yanchor='bottom', showarrow=False, text='업데이트', font=dict(size=11, color=PURPLE))
    if d in w.index:
        fig.add_annotation(x=d, y=float(w[d]), text=f'D0 {float(w[d]):,.0f}', showarrow=False, xshift=44, yshift=4, font=dict(size=12, color=color))
    fig.update_xaxes(showgrid=False, tickformat='%m/%d', zeroline=False)
    fig.update_yaxes(gridcolor='#e6eaf4', zeroline=False, tickformat=',.0f', rangemode='tozero' if zero else 'normal')
    fig = _base_layout(fig, 320)
    fig.update_layout(margin=dict(l=8, r=8, t=26, b=8))
    return fig


def fig_change_bars(values, height=None):
    """values: {국가: 변화율(%)} — 직전 대비 이후 일평균 변화율. None은 그리지 않음."""
    items = sorted(((k, v) for k, v in values.items() if v is not None and not np.isnan(v)), key=lambda x: x[1])
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation='h',
                           marker_color=[NEG if v >= 0 else BLUE for _, v in items],
                           text=[f'{v:+.2f}%' for _, v in items], textposition='outside', cliponaxis=False,
                           hovertemplate='%{y}: %{x:+.2f}%<extra></extra>'))
    fig.add_vline(x=0, line_color=GRAY, line_width=1)
    lo, hi = min([v for _, v in items] + [0]), max([v for _, v in items] + [0])
    pad = (hi - lo) * 0.18 or 10
    fig.update_xaxes(range=[lo - pad if lo < 0 else 0, hi + pad], gridcolor='#e6eaf4', ticksuffix='%', zeroline=False)
    fig.update_yaxes(showgrid=False)
    return _base_layout(fig, height or max(240, 34 * len(items) + 40))


def fig_diff_bars(values, height=None, unit=''):
    """values: {국가: 증감액} — 이후 N일 − 이전 N일. unit='억원' 이면 소수점 1자리 표시."""
    items = sorted(((k, v) for k, v in values.items() if v is not None and not np.isnan(v)), key=lambda x: x[1])
    fmt = '+.2f' if unit == '억원' else '+,.0f'
    tick_fmt = '.2f' if unit == '억원' else ','
    fig = go.Figure(go.Bar(x=[v for _, v in items], y=[k for k, _ in items], orientation='h',
                           marker_color=[NEG if v >= 0 else BLUE for _, v in items],
                           text=[f'{v:{fmt}}{unit}' for _, v in items], textposition='outside', cliponaxis=False,
                           hovertemplate=f'%{{y}}: %{{x:{fmt}}}{unit}<extra></extra>'))
    fig.add_vline(x=0, line_color=GRAY, line_width=1)
    lo, hi = min([v for _, v in items] + [0]), max([v for _, v in items] + [0])
    pad = (hi - lo) * 0.22 or 10
    fig.update_xaxes(range=[lo - pad if lo < 0 else 0, hi + pad], gridcolor='#e6eaf4', zeroline=False, tickformat=tick_fmt, ticksuffix=unit)
    fig.update_yaxes(showgrid=False)
    return _base_layout(fig, height or max(240, 34 * len(items) + 40))


WD = '월화수목금토일'


def fig_week_overlay(series, date, n, color=BLUE, name='값', zero=True, unit=''):
    """이후 n일(D0~D+n-1)과 이전 n일(D-n~D-1)을 같은 순서로 겹쳐 그림. 관측된 값만 사용, 보간 없음."""
    d = pd.Timestamp(date)
    xs, cur, prev, hov = [], [], [], []
    for k in range(n):
        x, y = series.get(d + pd.Timedelta(days=k)), series.get(d + pd.Timedelta(days=k - n))
        xs.append(f'D{k} ({WD[(d + pd.Timedelta(days=k)).dayofweek]})' if k else f'D0 ({WD[d.dayofweek]})')
        cur.append(None if x is None or pd.isna(x) else float(x))
        prev.append(None if y is None or pd.isna(y) else float(y))
        hov.append(f'{(d + pd.Timedelta(days=k)):%m/%d} vs {(d + pd.Timedelta(days=k - n)):%m/%d}')
    hover_fmt = ':.2f' if unit == '억원' else ':,.0f'
    tick_fmt = '.1f' if unit == '억원' else ',.0f'
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=prev, name=f'이전 {n}일', mode='lines+markers', line=dict(color=GRAY, width=2, dash='dash'),
                             marker=dict(size=6), customdata=hov, connectgaps=False, hovertemplate=f'%{{customdata}}<br>업데이트 이전 7일: %{{y{hover_fmt}}}{unit}<extra></extra>'))
    fig.add_trace(go.Scatter(x=xs, y=cur, name=f'이후 {n}일', mode='lines+markers', line=dict(color=color, width=2.8),
                             marker=dict(size=7), customdata=hov, connectgaps=False, hovertemplate=f'%{{customdata}}<br>업데이트 이후 7일: %{{y{hover_fmt}}}{unit}<extra></extra>'))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor='#e6eaf4', zeroline=False, tickformat=tick_fmt, ticksuffix=unit, rangemode='tozero' if zero else 'normal')
    fig.update_layout(legend=dict(orientation='h', y=1.12, x=0))
    fig = _base_layout(fig, 330)
    fig.update_layout(margin=dict(l=8, r=8, t=30, b=8))
    return fig


def fig_group_bars(labels, prev, cur, prev_name, cur_name, color=BLUE, height=300, unit=''):
    """업데이트별 (직전 vs 이후) 값을 나란히 막대로 표시."""
    fmt = '.1f' if unit == '억원' else ',.0f'
    tick_fmt = '.1f' if unit == '억원' else ',.0f'
    fig = go.Figure()
    fig.add_trace(go.Bar(x=labels, y=prev, name=prev_name, marker_color='#c5ccdf',
                         text=[f'{v:{fmt}}{unit}' if v is not None else '' for v in prev], textposition='outside'))
    fig.add_trace(go.Bar(x=labels, y=cur, name=cur_name, marker_color=color,
                         text=[f'{v:{fmt}}{unit}' if v is not None else '' for v in cur], textposition='outside'))
    fig.update_layout(barmode='group', legend=dict(orientation='h', y=1.14, x=0))
    fig.update_yaxes(gridcolor='#e6eaf4', zeroline=False, tickformat=tick_fmt, ticksuffix=unit)
    fig.update_xaxes(showgrid=False)
    return _base_layout(fig, height)
