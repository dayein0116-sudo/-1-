"""화면 공통 요소: 스타일(CSS), 카드, 표시 형식. 계산은 하지 않습니다 (analysis.py / report.py)."""
import html
import re

import numpy as np
import pandas as pd
import streamlit as st

import analysis as an

NAVY, BLUE, PURPLE = '#16254d', '#2f5bea', '#6b4fd8'

KRW_RATE = 1350  # 1 USD = 1,350 KRW (Sensor Tower 매출 고정 환율, 표시 목적)


def fmt_krw(v):
    """USD → KRW 표시 문자열. 계산은 원본 USD 유지."""
    if v is None:
        return '분析 불가'
    krw = v * KRW_RATE
    if krw >= 1e8:
        return f'약 {krw / 1e8:.1f}억 원'
    if krw >= 1e4:
        return f'약 {int(krw / 1e4):,}만 원'
    return f'{krw:,.0f}원'


def fmt_krw_delta(v):
    """USD 증감액 → KRW 증감 표시 (부호 포함)."""
    if v is None:
        return '분析 불가'
    krw = v * KRW_RATE
    if abs(krw) >= 1e8:
        return f'{krw / 1e8:+.1f}억 원'
    if abs(krw) >= 1e4:
        return f'{krw / 1e4:+,.0f}만 원'
    return f'{krw:+,.0f}원'


def fmt_dau(v):
    return '분析 불가' if v is None else f'{v:,.0f}명'


# 증감률 부호별 색상: 양수=빨간색(증가), 음수=파란색(감소) — 한국 게임 관례
CLR_UP = '#c0504d'
CLR_DN = '#2f5bea'


def fp_colored(v, nd=2):
    """fp()와 같되, 양수는 빨간색·음수는 파란색 HTML <span>으로 감쌉니다."""
    txt = fp(v, nd)
    if v is None or (isinstance(v, float) and np.isnan(v)) or v == 0:
        return txt
    clr = CLR_UP if v > 0 else CLR_DN
    return f'<span style="color:{clr};font-weight:600">{txt}</span>'


def _style_pct_cell(val):
    """Pandas Styler용 — % 로 끝나는 셀에 부호별 색상을 적용합니다."""
    if not isinstance(val, str) or not val.endswith('%'):
        return ''
    try:
        num = float(val.replace(',', '').replace('%', '').replace(' ', ''))
        if num > 0:
            return f'color: {CLR_UP}'
        if num < 0:
            return f'color: {CLR_DN}'
    except ValueError:
        pass
    return ''


CSS = """
<style>
:root { --navy:#16254d; --blue:#2f5bea; --purple:#6b4fd8; --line:#e3e8f4; --muted:#66729a; }
html, body, [data-testid="stAppViewContainer"], .stApp { background:#f3f5fb; }
[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:1.4rem; padding-bottom:3rem; max-width:1280px; }
h1,h2,h3,h4 { color:var(--navy); letter-spacing:-0.01em; }

/* 사이드바 */
[data-testid="stSidebar"] { background:#0f1b45; }
[data-testid="stSidebar"] * { color:#dbe3ff; }
[data-testid="stSidebar"] hr { border-color:#27366f; }
[data-testid="stSidebar"] [role="radiogroup"] { gap:2px; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding:9px 12px; border-radius:10px; width:100%; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background:#1b2b63; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background:#2f5bea; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) * { color:#fff; font-weight:600; }
[data-testid="stSidebar"] [data-testid="stRadioOption"] > div > div:first-child { display:none; }
.gui-logo { display:flex; align-items:center; gap:10px; padding:4px 2px 14px 2px; }
.gui-logo .mark { width:38px; height:38px; border-radius:10px; background:linear-gradient(135deg,#2f5bea,#6b4fd8);
  color:#fff !important; font-weight:800; display:flex; align-items:center; justify-content:center; font-size:15px; }
.gui-logo .t1 { color:#fff !important; font-weight:700; font-size:15px; line-height:1.15; }
.gui-logo .t2 { color:#8fa0d6 !important; font-size:11px; }
.side-note { font-size:11.5px; color:#9db0ea !important; line-height:1.5; }

/* 카드 */
[class*="st-key-card"] { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 18px 10px 18px;
  box-shadow:0 1px 2px rgba(22,37,77,.04); overflow:visible; padding-bottom:18px; }
.card-title { font-weight:700; color:var(--navy); font-size:15px; margin-bottom:2px; }
.card-sub { color:var(--muted); font-size:12.5px; margin-bottom:6px; line-height:1.5; }
.sec-head { display:flex; align-items:center; gap:10px; margin:26px 0 10px 0; }
.sec-head .num { width:26px; height:26px; border-radius:50%; background:var(--navy); color:#fff; font-size:13px; font-weight:700;
  display:flex; align-items:center; justify-content:center; }
.sec-head .tt { font-size:18px; font-weight:700; color:var(--navy); }
.sec-head .ss { color:var(--muted); font-size:12.5px; }

/* KPI */
.kpi { background:#fff; border:1px solid var(--line); border-radius:14px; padding:14px 16px; height:100%; min-height:136px;
  box-shadow:0 1px 2px rgba(22,37,77,.04); }
.kpi .lb { color:var(--muted); font-size:12.5px; font-weight:600; }
.kpi .vl { color:var(--navy); font-size:30px; font-weight:800; margin:4px 0 2px 0; line-height:1.15; letter-spacing:-0.02em; }
.kpi .vl.sm { font-size:19px; line-height:1.3; }
.kpi .vl.na { color:#8a93b2; font-size:20px; }
.kpi .sb { color:var(--muted); font-size:12px; line-height:1.5; }
.kpi.blue { border-top:3px solid var(--blue); } .kpi.green { border-top:3px solid #19b37a; }
.kpi.purple { border-top:3px solid var(--purple); } .kpi.navy { border-top:3px solid var(--navy); }

/* 요약 카드 */
.hero { background:#fff; border:1px solid var(--line); border-radius:14px; padding:18px 20px; }
.hero .dt { color:var(--muted); font-size:13px; font-weight:600; }
.hero .ti { color:var(--navy); font-size:22px; font-weight:800; margin:2px 0 8px 0; letter-spacing:-0.02em; }
.badge { display:inline-block; border-radius:999px; padding:2px 10px; font-size:12px; font-weight:700; margin-right:6px; }
.badge.gray { background:#eceff8; color:#4a5686; } .badge.kind { background:#e6eefe; color:#2447b8; font-weight:600; }
.chip { display:inline-block; background:#f1f4fc; border:1px solid var(--line); color:var(--navy); border-radius:8px;
  padding:3px 9px; font-size:12.5px; margin:2px 4px 2px 0; }
.chip .c { color:var(--muted); font-size:11px; margin-right:5px; }
.tag-fact { color:#2447b8; font-weight:700; } .tag-obs { color:#0f8a5f; font-weight:700; }
.tag-hyp { color:#6b4fd8; font-weight:700; } .tag-lim { color:#b4561b; font-weight:700; }
.blk { padding-bottom:12px; }
.blk h4 { margin:0 0 6px 0; font-size:14.5px; }
.blk ul { padding-left:18px; margin:0; } .blk li { font-size:13.5px; line-height:1.55; margin-bottom:5px; color:#23305c; }
.blk .meta { color:var(--muted); font-size:12px; }
.muted { color:var(--muted); font-size:12.5px; }
.retention { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.retention .it { flex:1 1 140px; background:#f6f8fd; border:1px solid var(--line); border-radius:10px; padding:10px 12px; }
.retention .it .a { color:var(--muted); font-size:12px; } .retention .it .b { color:var(--navy); font-weight:800; font-size:20px; }
@media (max-width: 760px) {
  .block-container { padding-left:0.8rem; padding-right:0.8rem; }
  .kpi .vl { font-size:24px; } .hero .ti { font-size:18px; }
}

/* 해석 카드 2행 — 같은 행 두 카드 높이 통일 */
.stHorizontalBlock:has([class*="st-key-card_notice"]),
.stHorizontalBlock:has([class*="st-key-card_conf"]) { align-items:stretch; }
.stColumn:has([class*="st-key-card_notice"]),
.stColumn:has([class*="st-key-card_hyp"]),
.stColumn:has([class*="st-key-card_conf"]),
.stColumn:has([class*="st-key-card_limits"]) { display:flex; flex-direction:column; }
.stColumn:has([class*="st-key-card_notice"]) > *,
.stColumn:has([class*="st-key-card_hyp"]) > *,
.stColumn:has([class*="st-key-card_conf"]) > *,
.stColumn:has([class*="st-key-card_limits"]) > * { flex:1; display:flex; flex-direction:column; }
[class*="st-key-card_notice"],
[class*="st-key-card_hyp"],
[class*="st-key-card_conf"],
[class*="st-key-card_limits"] { flex:1; box-sizing:border-box; }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


def esc(t):
    return html.escape(str(t))


def show(fig):
    try:
        st.plotly_chart(fig, width='stretch', config={'displayModeBar': False})
    except Exception:
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


def table(df, color_pct=True, **kw):
    hide = kw.get('hide_index', True)
    if color_pct and not df.empty:
        try:
            styled = df.style.map(_style_pct_cell)
        except AttributeError:
            styled = df.style.applymap(_style_pct_cell)
        try:
            st.dataframe(styled, width='stretch', hide_index=hide)
        except Exception:
            st.dataframe(styled, use_container_width=True, hide_index=hide)
    else:
        try:
            st.dataframe(df, width='stretch', hide_index=hide)
        except Exception:
            st.dataframe(df, use_container_width=True, hide_index=hide)


def fx(v):
    return '분석 불가' if v is None or (isinstance(v, float) and np.isnan(v)) else f'×{v:.2f}'


def fp(v, nd=2):
    return '분석 불가' if v is None or (isinstance(v, float) and np.isnan(v)) else f'{v:+.{nd}f}%'


def fmt_range(lo, hi):
    if lo is None or (isinstance(lo, float) and np.isnan(lo)):
        return '분석 불가'
    if abs(hi - lo) < 0.005:
        return f'{lo:+.2f}%'
    return f'{lo:+.2f}% ~ {hi:+.2f}%'


def num(v, nd=2):
    if v is None:
        return None
    try:
        if np.isnan(v):
            return None
    except TypeError:
        return None
    return round(float(v), nd)


def section(n, title, sub=''):
    st.markdown(f'<div class="sec-head"><div class="num">{n}</div><div><div class="tt">{esc(title)}</div>'
                + (f'<div class="ss">{esc(sub)}</div>' if sub else '') + '</div></div>', unsafe_allow_html=True)


def card_title(title, sub=''):
    st.markdown(f'<div class="card-title">{esc(title)}</div>' + (f'<div class="card-sub">{esc(sub)}</div>' if sub else ''), unsafe_allow_html=True)


def kpi(label, value, sub='', tone='blue', small=False, na=False):
    cls = 'vl' + (' sm' if small else '') + (' na' if na else '')
    return (f'<div class="kpi {tone}"><div class="lb">{esc(label)}</div><div class="{cls}">{esc(value)}</div>'
            f'<div class="sb">{sub}</div></div>')


def mark_updates(fig, updates):
    """업데이트 날짜 표시"""
    for u in updates:
        x = pd.Timestamp(u['date'])
        fig.add_vline(x=x.timestamp() * 1000, line_dash='dash', line_color=PURPLE)
        fig.add_annotation(x=x, y=1.0, yref='paper', yanchor='bottom', showarrow=False,
                           text=u['date'][5:], font=dict(size=11, color=PURPLE))
    return fig


def upd_label(u):
    return f"{u['date'][5:].replace('-', '/')} · {u['title']}"


def data_checks(project, data, ctx, window):
    """데이터 점검 표 행: 등록 자료·CSV·업로드·매출 DAU 비교·업데이트별 비교 구간."""
    rows = [{'대상': '프로젝트 등록 자료', '수준': lv, '내용': msg} for lv, msg in project.issues]
    rows += [{'대상': src, '수준': lv, '내용': msg} for src, lv, msg in data.issues]
    rows += [{'대상': '매출·DAU 비교', '수준': lv, '내용': msg} for lv, msg in an.validate_pair(ctx.rev, ctx.dau)]
    import report  # 지연 import (report는 화면 의존이 없음)
    au = report.scope_audit(ctx, 'common')
    names = ', '.join(au['rev_cols'])
    if au['ok']:
        rows.append({'대상': '집계 범위 점검', '수준': '안내', '내용': f'공통 {len(au["rev_cols"])}개국({names})의 매출·DAU 합계는 같은 국가 열로 계산되며 결측 칸이 없습니다.'})
    else:
        rows.append({'대상': '집계 범위 점검', '수준': '경고', '내용': f'매출·DAU 합계에 쓰는 국가가 다르거나 결측 칸 {au["missing_cells"]}개가 있습니다. 결측이 있는 날은 일부 국가만 합산됩니다.'})
    for name, idx in (('매출', ctx.rev.index), ('DAU', ctx.dau.index)):
        for r in an.validate_updates(ctx.updates, idx, window):
            if r['상태'] != '분석 가능':
                rows.append({'대상': f'{name} · {r["업데이트"]}', '수준': '경고', '내용': f'비교 기간 {window}일: {r["상태"]} — {r["사유"]}'})
    return rows


def goto(page):
    """사이드바 메뉴를 이동 (버튼의 on_click 콜백에서 사용)"""
    st.session_state['page'] = page


def _strip_strike(t):
    t = re.sub(r'~~(.+?)~~', r'\1', t)
    t = re.sub(r'</?(?:del|s|strike)[^>]*>', '', t)
    return t

def norm_hyp(h):
    """가설 항목은 문자열 또는 {text, basis}"""
    if isinstance(h, str):
        return {'text': _strip_strike(h), 'basis': []}
    return {'text': _strip_strike(h.get('text', '')), 'basis': list(h.get('basis', []))}
