"""Game Update Intelligence — 진입 파일.
프로젝트·업데이트를 고르면 해당 업데이트의 진단 리포트를 보여줍니다. 계산은 analysis.py / report.py, 화면은 views/ 에 있습니다.
실행: python -m streamlit run app.py
"""
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import analysis as an
import registry
import report
import ui
from views import compare, country, diagnosis, overview, structure

st.set_page_config(page_title='Game Update Intelligence', page_icon='🎮', layout='wide')
ui.inject_css()
BASE = Path(__file__).parent

PAGES = ['업데이트 진단', '업데이트 비교', '국가별 반응', '업데이트 구성', '전체 개요']
SCOPE_OPTIONS = ['common', 'file']
WINDOW = 7  # 비교 기간: KPI/국가는 달력 주(월~일) 기준, 일별 차트는 D0 기준 이전/이후 7일

# ── 등록된 프로젝트 불러오기 ────────────────────────────────
projects, failed = registry.discover_projects(BASE / 'projects')
if not projects:
    st.error('등록된 프로젝트가 없습니다. projects/<프로젝트 이름>/ 폴더에 project.json, revenue.csv, dau.csv, updates.json을 두세요.')
    for name, why in failed:
        st.warning(f'{name}: {why}')
    st.stop()

# ── 사이드바 ───────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="gui-logo"><div class="mark">GUI</div><div><div class="t1">Game Update<br>Intelligence</div>'
                '<div class="t2">업데이트 반응 진단</div></div></div>', unsafe_allow_html=True)
    st.session_state.setdefault('page', PAGES[0])
    page = st.radio('메뉴', PAGES, key='page', label_visibility='collapsed')
    st.divider()
    window = WINDOW
    st.markdown(f'<div class="side-note"><b>비교 기준</b><br>핵심 KPI·주요 발견·국가별 비교: 달력 주(월~일) 기준 — 업데이트 주 vs 전주. 일별 추이 차트: 전주(월~일) vs 업데이트 주(월~일), 업데이트일 D0 표시.</div>', unsafe_allow_html=True)
    st.markdown('<div class="side-note">Sensor Tower 추정치 기반입니다. 관찰된 변화이며 업데이트의 인과적 효과나 콘텐츠별 매출 기여율이 아닙니다.</div>', unsafe_allow_html=True)
    if failed:
        with st.expander(f'읽지 못한 프로젝트 {len(failed)}개'):
            for name, why in failed:
                st.caption(f'{name}: {why}')

# ── 상단: 프로젝트 선택 ────────────────────────────────────
top1, top2, top3 = st.columns([1.2, 2.2, 1.3])
with top1:
    pid = st.selectbox('분석 게임', [p.id for p in projects], format_func=lambda i: next(p.name for p in projects if p.id == i), key='project_sel')
project = next(p for p in projects if p.id == pid)

# ── 데이터 로딩 ──────────────────────────────────────────────
try:
    data = registry.load_project_data(project)
except Exception as e:
    st.error(f'등록된 데이터를 읽지 못했습니다: {e}')
    st.stop()
ctx = report.build_context(project, data.rev, data.dau)

# ── 상단: 업데이트·집계 범위 선택 ────────────────────────────
dates = [u['date'] for u in project.updates]
st.session_state.setdefault('sel_upd', dates[-1])
if st.session_state['sel_upd'] not in dates:
    st.session_state['sel_upd'] = dates[-1]
st.session_state.setdefault('sel_scope', 'file')
if st.session_state['sel_scope'] not in SCOPE_OPTIONS:
    st.session_state['sel_scope'] = 'file'
by_date = {u['date']: u for u in project.updates}
with top2:
    st.selectbox('업데이트 선택', dates, index=dates.index(st.session_state['sel_upd']), key='upd_w',
                 format_func=lambda d: ui.upd_label(by_date[d]), on_change=lambda: st.session_state.update(sel_upd=st.session_state['upd_w']))
with top3:
    st.selectbox('집계 범위', SCOPE_OPTIONS, index=SCOPE_OPTIONS.index(st.session_state['sel_scope']), key='scope_w',
                 format_func=lambda s: report.SCOPE_LABELS[s].format(n=len(ctx.common)).split(' (')[0],
                 on_change=lambda: st.session_state.update(sel_scope=st.session_state['scope_w']))
upd, scope = by_date[st.session_state['sel_upd']], st.session_state['sel_scope']

st.markdown(f'<div class="muted" style="margin:-4px 0 10px 2px">분석 데이터: {data.rev.index.min():%Y.%m.%d} ~ {data.rev.index.max():%Y.%m.%d} ({len(data.rev)}일) · '
            f'출처: {ui.esc(project.meta.get("data_source", "-"))} · 매출 USD → 1,350원 환산 표시 · 플랫폼·집계 범위 미확인</div>', unsafe_allow_html=True)

rep = report.build_update_report(ctx, upd, window, scope)
ranked_common = ctx.display_countries[:len(ctx.common)]
if scope == 'common':
    scope_note = (f'집계 범위 — 공통 {len(ctx.common)}개국: {", ".join(ranked_common)} '
                  '(매출 파일과 DAU 파일 양쪽에 모두 있는 개별 국가를 매출·DAU 모두 같은 목록으로 합산)')
else:
    scope_note = (f'집계 범위 — 전체 국가: 매출 파일 {", ".join(ctx.rev_countries)} + 기타 / '
                  f'DAU 파일 {", ".join(ctx.dau_countries)} + 기타 (두 파일의 국가 구성이 다름)')

# ── 업데이트 비교·구성 화면이 공유하는 주기 집계 ──────────────────────────────
# scope·project·data가 확정된 뒤 한 번만 계산하고 env에 넣는다.
_rs, _ds = ctx.series(scope)
rev_cycles = an.cycle_compare(_rs, project.updates, cutoff_date=data.data_cutoff,
                               next_update_date=data.next_update_date)
pre_period = None
if rev_cycles:
    _pre_len = rev_cycles[0]['days']
    _pre_end = pd.Timestamp(rev_cycles[0]['date']) - pd.Timedelta(days=1)
    _pre_start = _pre_end - pd.Timedelta(days=_pre_len - 1)
    _rs_valid = _rs.dropna()
    _data_start = _rs_valid.index.min() if len(_rs_valid) > 0 else None
    if _data_start is not None and _pre_start >= _data_start:
        _pre_data = _rs[(_rs.index >= _pre_start) & (_rs.index <= _pre_end)].dropna()
        if len(_pre_data) > 0:
            _pre_total = float(_pre_data.sum())
            pre_period = {
                'd_start': str(_pre_start.date()),
                'd_end': str(_pre_end.date()),
                'days': len(_pre_data),
                'total': _pre_total,
                'daily_avg': _pre_total / len(_pre_data),
            }
dau_cycles = an.cycle_compare(_ds, project.updates, cutoff_date=data.data_cutoff,
                               next_update_date=data.next_update_date)
pre_dau_period = None
if pre_period:
    _ps = pd.Timestamp(pre_period['d_start'])
    _pe = pd.Timestamp(pre_period['d_end'])
    _pre_dau = _ds[(_ds.index >= _ps) & (_ds.index <= _pe)].dropna()
    if len(_pre_dau) > 0:
        pre_dau_period = {'daily_avg': float(_pre_dau.mean()), 'days': len(_pre_dau)}

env = SimpleNamespace(project=project, data=data, ctx=ctx, upd=upd, window=window, scope=scope, rep=rep,
                      highlights=report.highlights(upd), scope_note=scope_note,
                      rev_cycles=rev_cycles, dau_cycles=dau_cycles,
                      pre_period=pre_period, pre_dau_period=pre_dau_period)

if page == '업데이트 진단':
    diagnosis.render(env)
elif page == '업데이트 비교':
    compare.render(env)
elif page == '국가별 반응':
    country.render(env)
elif page == '업데이트 구성':
    structure.render(env)
else:
    overview.render(env)
