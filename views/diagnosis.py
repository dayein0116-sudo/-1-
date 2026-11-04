"""업데이트 진단 — 메인 화면. 선택한 업데이트 1건의 리포트를 위에서 아래로 보여줍니다."""
from types import SimpleNamespace

import pandas as pd
import streamlit as st

import analysis as an
import charts
import report
import ui
from ui import esc, fmt_range, fp, fx


# ── 상단 요약 + KPI ────────────────────────────────────────
def _hero(env):
    u, rep = env.upd, env.rep
    d = pd.Timestamp(u['date'])
    n_items = sum(len(v) for v in u['items'].values())
    chips = ''.join(f'<span class="chip"><span class="c">{esc(cat)}</span>{esc(" · ".join(txt))}</span>'
                    for cat, txt in env.highlights)
    kinds = [x['kind'] for v in u['items_detail'].values() for x in v if x['kind']]
    kind_html = ''.join(f'<span class="badge kind">{esc(k)}</span>' for k in dict.fromkeys(kinds))
    st.markdown(
        f'<div class="hero">'
        f'<div class="dt">{d:%Y.%m.%d} ({"월화수목금토일"[d.dayofweek]})</div>'
        f'<div class="ti">{esc(u["title"])}</div>'
        f'<div style="margin-top:6px"><span class="badge gray">{esc(rep["scope_label"])}</span>'
        f'<span class="badge gray">전주 대비 업데이트 주 비교</span>'
        f'<span class="badge gray">공지 항목 {n_items}개</span></div>'
        f'</div>',
        unsafe_allow_html=True)
    with st.expander('업데이트 상세 내용 확인', expanded=False):
        st.markdown(
            f'<div class="muted" style="margin-bottom:6px">{esc(env.scope_note)}</div>'
            + (f'<div style="margin-bottom:6px">{chips}</div>' if chips else '')
            + (f'<div style="margin-bottom:6px">{kind_html}</div>' if kind_html else '')
            + f'<div class="muted">출처: {esc(u["source"] or "패치노트 원문 미등록")}</div>',
            unsafe_allow_html=True)


def _num(v):
    return '분석 불가' if v is None else f'{v:,.0f}'


def _labels(n):
    return report.period_labels(n)


def _cal_labels():
    return report.cal_period_labels()


def _kpis(env):
    rep, n, d = env.rep, env.rep['window'], env.upd['date']
    cur_l, prev_l = _cal_labels()
    rs, ds = rep['rev_series'], rep['dau_series']
    dt = pd.Timestamp(d)
    w_r = an.week_compare_cal(rs, d)
    w_d = an.week_compare_cal(ds, d)

    # 달력 주 날짜 (데이터 여부와 무관하게 계산 가능)
    ws = dt - pd.Timedelta(days=dt.dayofweek)
    we = ws + pd.Timedelta(days=6)
    ps = ws - pd.Timedelta(days=7)
    pe = ws - pd.Timedelta(days=1)
    pre_days = dt.dayofweek

    def _pv(v):
        if v is None: return '분석 불가'
        clr = '#c0504d' if v > 0 else ('#2f5bea' if v < 0 else '')
        txt = f'{v:+.1f}%'
        return f'<span style="color:{clr};font-weight:700">{txt}</span>' if clr else txt

    th = 'padding:8px 12px;border-bottom:2px solid var(--line);color:var(--muted);font-size:12.5px;font-weight:600;text-align:{}'
    td = 'padding:10px 12px;border-bottom:1px solid var(--line);font-size:14px;text-align:{};color:var(--navy)'
    td_b = 'padding:10px 12px;font-size:14px;text-align:{};color:var(--navy);font-weight:700'

    def _row(label, rv, dv, style):
        return (f'<tr><td style="{style.format("left")}">{label}</td>'
                f'<td style="{style.format("right")}">{rv}</td>'
                f'<td style="{style.format("right")}">{dv}</td></tr>')

    table_html = (
        '<table style="width:100%;border-collapse:collapse;margin-top:6px">'
        f'<thead><tr>'
        f'<th style="{th.format("left")}">기간</th>'
        f'<th style="{th.format("right")}">추정 매출 합계</th>'
        f'<th style="{th.format("right")}">일평균 DAU</th>'
        f'</tr></thead><tbody>'
        + _row(f'{prev_l} <span style="font-weight:400;font-size:12px;color:var(--muted)">({ps.strftime("%m/%d")}~{pe.strftime("%m/%d")})</span>',
               ui.fmt_krw(w_r['prev_sum'] if w_r else None), ui.fmt_dau(w_d['prev_mean'] if w_d else None), td)
        + _row(f'{cur_l} <span style="font-weight:400;font-size:12px;color:var(--muted)">({ws.strftime("%m/%d")}~{we.strftime("%m/%d")}, D0={dt.strftime("%m/%d")}{"" if pre_days == 0 else f", 이 중 {pre_days}일은 업데이트 이전"})</span>',
               ui.fmt_krw(w_r['cur_sum'] if w_r else None), ui.fmt_dau(w_d['cur_mean'] if w_d else None), td)
        + _row('주간 변화율',
               _pv(w_r['pct'] if w_r else None), _pv(w_d['pct'] if w_d else None), td_b)
        + '</tbody></table>'
    )

    with st.container(key='card_kpi_tbl'):
        st.markdown(f'<div class="card-sub">{esc(rep["rev_scope_label"])} / {esc(rep["dau_scope_label"])}</div>' + table_html,
                    unsafe_allow_html=True)
    st.write('')

    x = an.day_vs_prev(rs, d, 0, n)
    if x and x['pct'] is not None:
        wd = '월화수목금토일'[x['prev_date'].dayofweek]
        st.caption(f'업데이트 당일(D0) 추정 매출 {ui.fmt_krw(x["cur"])} — {n}일 전 같은 요일({x["prev_date"]:%m/%d} {wd}) {ui.fmt_krw(x["prev"])} 대비 {fp(x["pct"])} (하루 단위 참고값)')
    if w_r and w_r.get('peak_pct') is not None:
        st.caption(f'{cur_l} 최고 일 추정 매출 {ui.fmt_krw(w_r["cur_peak"])} — {prev_l} 최고 일 {ui.fmt_krw(w_r["prev_peak"])} 대비 {fp(w_r["peak_pct"])}')
    st.caption(f'비교 기준: {prev_l}({ps.strftime("%m/%d")}–{pe.strftime("%m/%d")}) 대비 {cur_l}({ws.strftime("%m/%d")}–{we.strftime("%m/%d")}) · 월–일 기준. '
               f'D0 이전 {pre_days}일이 업데이트 주에 포함됩니다. 추정 매출은 Sensor Tower USD → 1,350원 환산. 관찰이지 인과 아님.')


def _findings(env):
    """주요 발견 — 3단계 문장형 요약: 전체 변화 / 시간 반응 / 국가별."""
    rep, n, d = env.rep, env.rep['window'], env.upd['date']
    rs, ds = rep['rev_series'], rep['dau_series']
    w_r = an.week_compare_cal(rs, d)
    w_d = an.week_compare_cal(ds, d)

    # ① 전체 변화
    def _dir(w):
        return None if (w is None or w['pct'] is None) else (w['pct'] > 0)

    r_up, d_up = _dir(w_r), _dir(w_d)
    if r_up is not None and d_up is not None:
        if r_up and d_up:            headline = '추정 매출과 DAU 모두 증가'
        elif not r_up and not d_up:  headline = '추정 매출과 DAU 모두 감소'
        elif r_up:                   headline = '추정 매출은 증가했지만, DAU는 감소'
        else:                        headline = '추정 매출은 감소했지만, DAU는 증가'
    elif r_up is not None:
        headline = f'추정 매출 {"증가" if r_up else "감소"} / DAU 계산 불가'
    elif d_up is not None:
        headline = f'추정 매출 계산 불가 / DAU {"증가" if d_up else "감소"}'
    else:
        headline = '추정 매출·DAU 계산 불가'

    pct_parts = []
    if w_r and w_r['pct'] is not None:
        pct_parts.append(f'추정 매출 {ui.fp_colored(w_r["pct"])}')
    if w_d and w_d['pct'] is not None:
        pct_parts.append(f'일평균 DAU {ui.fp_colored(w_d["pct"])}')
    pct_note_html = ' · '.join(pct_parts) if pct_parts else '수치 계산 불가'

    # ② 시간에 따른 반응 (D0~D+6 일자별 전주 동일 요일 대비)
    def _trend_desc(ser, label):
        vals = [(k, x['pct']) for k in range(n) for x in [an.day_vs_prev(ser, d, k, n)] if x and x['pct'] is not None]
        if not vals:
            return None, None
        pos = [k for k, v in vals if v > 0]
        neg = [k for k, v in vals if v < 0]
        kmax = vals[-1][0]
        if len(pos) == len(vals):
            pattern = f'D0~D+{kmax} 전주 동일 요일 대비 모두 플러스(+)'
        elif len(neg) == len(vals):
            pattern = f'D0~D+{kmax} 전주 동일 요일 대비 모두 마이너스(-)'
        elif vals[0][1] > 0:
            first_neg = next(k for k, v in vals if v < 0)
            pos_range = 'D0만' if first_neg == 1 else f'D0~D+{first_neg - 1}'
            pattern = f'{pos_range} 전주 동일 요일 대비 플러스(+), D+{first_neg}부터 마이너스(-) 전환'
        elif vals[0][1] < 0:
            first_pos = next(k for k, v in vals if v > 0)
            neg_range = 'D0만' if first_pos == 1 else f'D0~D+{first_pos - 1}'
            pattern = f'{neg_range} 전주 동일 요일 대비 마이너스(-), D+{first_pos}부터 플러스(+) 전환'
        else:
            pattern = f'D0~D+{kmax}: 플러스(+) {len(pos)}일, 마이너스(-) {len(neg)}일 (전주 동일 요일 대비)'
        basis = ' / '.join(f'{"D0" if k == 0 else f"D+{k}"} {ui.fp_colored(v)}' for k, v in vals)
        return f'{label}: {pattern}', basis

    rev_desc, rev_basis = _trend_desc(rs, '매출')
    dau_desc, dau_basis = _trend_desc(ds, 'DAU')

    # ③ 국가별 반응
    pool = [c for c in rep['countries'] if rep['scope'] != 'common' or not c['tag']]

    def _ctry(key_name):
        # 달력 주(월~일) 기준 — 주 KPI와 동일한 계산 방식
        df_col = env.ctx.rev if key_name == 'rev' else env.ctx.dau
        rows = []
        for c in pool:
            if not (c[key_name] and c[key_name]['ok']):
                continue
            if c['name'] in df_col.columns:
                w = an.week_compare_cal(df_col[c['name']], d)
                if w:
                    rows.append((c['name'], w['pct']))
        if not rows:
            return None, None, None, None
        rows.sort(key=lambda x: -x[1])
        up = sum(v > 0 for _, v in rows)
        return up, len(rows), rows[0], rows[-1]

    rev_up, rev_tot, rev_max, rev_min = _ctry('rev')
    dau_up, dau_tot, dau_max, dau_min = _ctry('dau')

    if rev_up is not None and dau_up is not None:
        if rev_up == rev_tot and dau_up == dau_tot:
            ctry_hl = f'분석 대상 {rev_tot}개국 전체에서 매출·DAU 모두 증가 관찰'
        elif rev_up == rev_tot:
            ctry_hl = f'매출 증가가 분석 대상 {rev_tot}개국 모두에서 관찰 · DAU는 {dau_tot}개국 중 {dau_up}개국 증가'
        elif dau_up == dau_tot:
            ctry_hl = f'DAU 증가가 분석 대상 {dau_tot}개국 모두에서 관찰 · 매출은 {rev_tot}개국 중 {rev_up}개국 증가'
        else:
            ctry_hl = f'분석 대상 {rev_tot}개국 중 매출 증가 {rev_up}개국 · DAU 증가 {dau_up}/{dau_tot}개국'
        ctry_basis = f'매출 증가 {rev_up}/{rev_tot}개국 · DAU 증가 {dau_up}/{dau_tot}개국'
    elif rev_up is not None:
        ctry_hl = f'매출: {rev_tot}개국 중 {rev_up}개국 증가 · DAU 국가 데이터 없음'
        ctry_basis = f'매출 증가 {rev_up}/{rev_tot}개국'
    elif dau_up is not None:
        ctry_hl = f'DAU: {dau_tot}개국 중 {dau_up}개국 증가 · 매출 국가 데이터 없음'
        ctry_basis = f'DAU 증가 {dau_up}/{dau_tot}개국'
    else:
        ctry_hl, ctry_basis = None, None

    detail_parts = []
    if rev_tot and rev_tot > 1:
        detail_parts.append(f'매출 최고 {rev_max[0]} {rev_max[1]:+.0f}% · 최저 {rev_min[0]} {rev_min[1]:+.0f}%')
    if dau_tot and dau_tot > 1:
        detail_parts.append(f'DAU 최고 {dau_max[0]} {dau_max[1]:+.0f}% · 최저 {dau_min[0]} {dau_min[1]:+.0f}%')

    sub = f'<span style="font-weight:400">'
    with st.container(key='card_obs'):
        st.markdown('<div class="blk"><h4><span class="tag-obs">[관찰]</span> 주요 발견 — 계산된 수치</h4></div>', unsafe_allow_html=True)

        st.markdown(
            f'<div style="font-size:12px;font-weight:600;color:var(--muted);margin:6px 0 2px 0">① 전체 변화</div>'
            f'<div style="font-size:16px;font-weight:700;color:var(--navy);margin:0 0 2px 0">{esc(headline)}</div>'
            f'<div class="muted" style="margin-bottom:10px">{pct_note_html} — {esc(rep["rev_scope_label"])} / {esc(rep["dau_scope_label"])} · 달력 주(월~일) 기준</div>',
            unsafe_allow_html=True)

        if rev_desc or dau_desc:
            st.markdown(
                f'<div style="font-size:12px;font-weight:600;color:var(--muted);margin:4px 0 4px 0">'
                f'② 시간에 따른 반응 {sub}(전주 동일 요일 대비 일자별 — 업데이트 효과의 지속성을 단정하지 않습니다)</span></div>',
                unsafe_allow_html=True)
            for desc, basis in [(rev_desc, rev_basis), (dau_desc, dau_basis)]:
                if desc:
                    st.markdown(
                        f'<div style="font-size:13.5px;color:var(--navy);margin-bottom:1px">{esc(desc)}</div>'
                        f'<div class="muted" style="margin-bottom:6px">근거: {basis}</div>',
                        unsafe_allow_html=True)

        if ctry_hl:
            st.markdown(
                f'<div style="font-size:12px;font-weight:600;color:var(--muted);margin:4px 0 4px 0">'
                f'③ 국가별 반응 {sub}(달력 주 기준 · 선택된 집계 범위)</span></div>'
                f'<div style="font-size:13.5px;color:var(--navy);margin-bottom:1px">{esc(ctry_hl)}</div>'
                f'<div class="muted" style="margin-bottom:4px">근거: {esc(ctry_basis)}</div>',
                unsafe_allow_html=True)
            if detail_parts:
                st.caption(' | '.join(detail_parts))


# ── 1. 달력 주(월~일) 기준 일별 추이 ────────────────────────────────────────────
def _response(env):
    rep = env.rep
    d = pd.Timestamp(env.upd['date'])
    ws = d - pd.Timedelta(days=d.dayofweek)
    ps = ws - pd.Timedelta(days=7)
    ui.section(1, '업데이트 전후 일별 반응',
               f'전주(월~일) {ps:%m/%d}–{ps + pd.Timedelta(days=6):%m/%d} 대비 업데이트 주(월~일) '
               f'{ws:%m/%d}–{ws + pd.Timedelta(days=6):%m/%d} · 업데이트가 발생한 요일에 D0 표시')
    c1, c2 = st.columns(2)
    for col, key, label, color in ((c1, 'rev', '추정 매출', charts.BLUE), (c2, 'dau', 'DAU', charts.GREEN)):
        with col.container(key=f'card_resp_{key}'):
            ui.card_title(f'일별 {label}', f'전주 대비 업데이트 주 일별 추이 · {rep[f"{key}_scope_label"]}')
            ser = rep[f'{key}_series']
            disp_ser = ser * ui.KRW_RATE / 1e8 if key == 'rev' else ser
            fig = charts.fig_cal_week_overlay(disp_ser, env.upd['date'], color, name=label,
                                              zero=(key == 'rev'), unit='억원' if key == 'rev' else '명')
            if fig is None:
                st.info('분석 불가 — 전주(월~일) 7일 데이터가 없습니다.')
            else:
                ui.show(fig)
    st.caption('DAU 차트는 변화가 보이도록 세로축이 0에서 시작하지 않습니다 (폭이 작으면 과장돼 보일 수 있어 숫자를 함께 확인하세요).')
    for f in rep['flags']:
        if f['kind'] == '업데이트 직전':
            st.caption('참고: ' + f['text'])

# ── 2. 국가별 ──────────────────────────────────────────────
def _comparison(env):
    rep, n = env.rep, env.rep['window']
    cur_l, prev_l = _cal_labels()
    ui.section(2, '국가별 비교', f'국가별 {cur_l} vs {prev_l} — 증감률만으로 판단하지 말고 실제 규모(값·증감액)와 함께 보세요')
    metric = st.radio('표시 지표', ['추정 매출', 'DAU'], horizontal=True, key='cmp_metric')
    key = 'rev' if metric == '추정 매출' else 'dau'
    unit = '합계' if key == 'rev' else '일평균'
    tbl = report.country_week_table(env.ctx, rep, key)
    total, body = tbl[0], tbl[1:]
    ok = [r for r in body if r['pct'] is not None]
    skipped = [r['name'] for r in body if r['pct'] is None and r['group'] == '포함']

    def line(r, label=None):
        fv = ui.fmt_krw if key == 'rev' else ui.fmt_dau
        fd = ui.fmt_krw_delta if key == 'rev' else (lambda v: '분석 불가' if v is None else f'{v:+,.0f}명')
        return {'국가': label or r['name'] + ('' if r['group'] != '미포함' else ' *'),
                f'{prev_l} {unit}': fv(r['prev']), f'{cur_l} {unit}': fv(r['cur']),
                '증감액': fd(r['diff']), '증감률': fp(r['pct']) if r['pct'] is not None else '분석 불가'}

    rows = [line(total, '합계 (공통 {}개국)'.format(len(env.ctx.common)) if rep['scope'] == 'common' else '합계 (파일 전체)')] + [line(r) for r in body]
    c1, c2 = st.columns([0.8, 1.55])
    with c1.container(key='card_country'):
        basis = st.radio('막대 기준', ['증감액 (실제 규모)', '증감률'], horizontal=True, key='cmp_basis')
        inc = [r for r in ok if r['group'] == '포함']
        ui.card_title(f'국가별 {metric} {"증감액" if basis.startswith("증감액") else "증감률"}',
                      f'{cur_l} {unit} − {prev_l} {unit}' + (' (원화 환산, 억원)' if basis.startswith('증감액') and key == 'rev' else '') if basis.startswith('증감액') else f'{cur_l} {unit} ÷ {prev_l} {unit} − 1')
        if inc:
            if basis.startswith('증감액') and key == 'rev':
                ui.show(charts.fig_diff_bars({r['name']: r['diff'] * ui.KRW_RATE / 1e8 if r['diff'] is not None else None for r in inc}, unit='억원'))
            elif basis.startswith('증감액'):
                ui.show(charts.fig_diff_bars({r['name']: r['diff'] for r in inc}))
            else:
                ui.show(charts.fig_change_bars({r['name']: r['pct'] for r in inc}))
        else:
            st.info('분석 불가')
        if skipped:
            st.caption('분석 불가: ' + ', '.join(skipped))
        st.caption('소규모 국가는 일 규모가 작아 증감률이 크게 나올 수 있습니다. 여러 국가가 함께 움직여도 업데이트의 인과적 효과가 입증되는 것은 아닙니다.')
    with c2.container(key='card_country_tbl'):
        ui.card_title(f'국가별 {metric} 실제 값 ({"원화 환산" if key == "rev" else "원본 단위"}, 규모순)', rep[f'{key}_scope_label'] + ' 기준 · 전주 7일 데이터가 없는 국가는 분석 불가')
        ui.table(pd.DataFrame(rows))
        if any(r['group'] == '미포함' for r in body):
            st.caption('* 합계에 포함되지 않은 국가 — ' + ('매출 파일에만 있는 국가' if key == 'rev' else 'DAU 파일에만 있는 국가') +
                       '입니다 (공통 국가 합산은 매출·DAU 파일 모두에 있는 국가만 더합니다).')


# ── 3. 일자별 값 (7일 전 같은 요일 비교 · 참고) ──────────────────────────────────────────────────────
def _daily_table(env):
    rep, n, d = env.rep, env.rep['window'], env.upd['date']
    ui.section(3, f'일자별 값 — {n}일 전 같은 요일과 비교 (참고)', '날짜별 실제 값과 증감 — 하루 단위 참고 지표이며 업데이트 효과를 직접 측정하는 값이 아닙니다')
    c1, c2 = st.columns(2)
    for col, key, label in ((c1, 'rev', '추정 매출'), (c2, 'dau', 'DAU')):
        with col.container(key=f'card_daily_{key}'):
            ui.card_title(label, rep[f'{key}_scope_label'])
            rows = []
            fv = ui.fmt_krw if key == 'rev' else ui.fmt_dau
            for k in range(n):
                x = an.day_vs_prev(rep[f'{key}_series'], d, k, n)
                day = pd.Timestamp(d) + pd.Timedelta(days=k)
                rows.append({'날짜': f'{day:%m/%d} ({"월화수목금토일"[day.dayofweek]}) {"D0" if k == 0 else f"D+{k}"}',
                             f'{n}일 전 같은 요일': fv(x['prev'] if x else None), '업데이트 후': fv(x['cur'] if x else None),
                             '증감': fp(x['pct']) if x and x['pct'] is not None else '분석 불가'})
            ui.table(pd.DataFrame(rows))
    st.caption('대표 성과는 위의 달력 주(전주 대비 업데이트 주) 비교입니다. 이 표는 같은 요일끼리 하루씩 맞춘 참고값이라, 연휴·후속 이벤트가 겹치면 증감의 원인을 구분할 수 없습니다.')


# ── 4. 공지·관찰·가설·요인·한계 ──────────────────────────────
def _items_html(upd):
    items_detail = upd.get('items_detail') or {}
    items = upd.get('items') or {}
    # Fallback: synthesize items_detail from items when items_detail is empty
    if not items_detail and items:
        items_detail = {cat: [{'text': t, 'kind': ''} for t in its] for cat, its in items.items() if its}
    out = []
    for cat, its in items_detail.items():
        if not its:
            continue
        lis = ''.join(f'<li>{esc(x["text"])}' + (f' <span class="badge kind">{esc(x["kind"])}</span>' if x.get('kind') else '') + '</li>' for x in its)
        out.append(f'<div class="meta" style="margin-top:6px"><b>{esc(cat)}</b></div><ul>{lis}</ul>')
    return ''.join(out)


def env_cats(upd):
    return list(upd['items_detail'].keys()) if upd.get('items_detail') else list(upd.get('items', {}).keys())


def _hypothesis(env):
    """사업 해석 제안 [가설] — 주요 발견 이전에 표시."""
    u = env.upd
    with st.container(key='card_hyp'):
        hyp = [ui.norm_hyp(h) for h in u['hypotheses']]
        def _hyp_li(h):
            return (f'<li>{esc(h["text"])}' +
                    (f'<div class="meta">근거 항목: {esc(" / ".join(h["basis"]))}</div>' if h['basis'] else '') +
                    '</li>')
        visible_hyp, extra_hyp = hyp[:2], hyp[2:]
        body = ''.join(_hyp_li(h) for h in visible_hyp)
        st.markdown('<div class="blk"><h4><span class="tag-hyp">[가설]</span> 사업 해석 제안(AI)</h4>'
                    + (f'<ul>{body}</ul>' if body else '<div class="muted">등록된 가설이 없습니다.</div>')
                    + '<div class="meta" style="margin-top:6px">공지 구성에서 추론한 가설이며 공지에 명시된 목적이 아닙니다. 확인 가능한 사실은 아래 [참고]와 위 [관찰]이고, 가설의 한계는 아래 [한계]를 따릅니다.</div></div>',
                    unsafe_allow_html=True)
        if extra_hyp:
            with st.expander(f'나머지 가설 {len(extra_hyp)}개 펼쳐 보기'):
                st.markdown('<ul>' + ''.join(_hyp_li(h) for h in extra_hyp) + '</ul>', unsafe_allow_html=True)


def _narrative(env):
    rep, u = env.rep, env.upd
    ui.section(4, '공지와 관찰된 반응의 해석', '공지에서 확인된 사실 · 함께 고려할 요인 · 한계를 구분합니다 (가설은 위, 관찰된 수치는 "주요 발견"에 있습니다)')

    # [참고] 공지 기반 업데이트 구성 전체 너비
    with st.container(key='card_notice'):
        n_items = sum(len(v) for v in u['items_detail'].values()) if u.get('items_detail') else sum(len(v) for v in u.get('items', {}).values())
        st.markdown('<div class="blk"><h4><span class="tag-fact">[참고]</span> 공지 기반 업데이트 구성</h4>'
                    f'<div class="meta">출처: {esc(u["source"] or "패치노트 원문 미등록")}</div></div>', unsafe_allow_html=True)
        with st.expander(f'공지 항목 {n_items}개 펼쳐 보기', expanded=False):
            st.markdown(_items_html(u), unsafe_allow_html=True)
        for f in rep['notice_facts'][1:]:
            if f.startswith('공지 요약에 신규 BM'):
                st.caption(f)

    # 2열 — [참고] 함께 고려할 요인 / [한계]
    d_col, e_col = st.columns(2)
    with d_col.container(key='card_conf'):
        flags = ''.join(f'<li><b>{esc(f["kind"])}</b> — {esc(f["text"])}</li>' for f in rep['flags'])
        conf = ''.join(f'<li>{esc(x)}</li>' for x in u['confounds'])
        st.markdown('<div class="blk"><h4><span class="tag-fact">[참고]</span> 함께 고려할 요인 <span class="meta">(외부 요인 · 동시 투입 요소)</span></h4>'
                    + (f'<div class="meta">공지·등록 자료</div><ul>{conf}</ul>' if conf else '')
                    + f'<div class="meta" style="margin-top:8px">시점·데이터 점검</div><ul>{flags}</ul></div>', unsafe_allow_html=True)
    with e_col.container(key='card_limits'):
        limits = rep['limits']
        visible_lim, extra_lim = limits[:3], limits[3:]
        st.markdown('<div class="blk"><h4><span class="tag-lim">[한계]</span> 해석의 한계</h4><ul>'
                    + ''.join(f'<li>{esc(x)}</li>' for x in visible_lim) + '</ul></div>', unsafe_allow_html=True)
        if extra_lim:
            with st.expander(f'추가 한계 {len(extra_lim)}개 펼쳐 보기'):
                st.markdown('<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in extra_lim) + '</ul>', unsafe_allow_html=True)


# ── 5. 추가 분석·데이터 점검 ──────────────────────────────────
def _more(env):
    ui.section(5, '추가 분석 및 데이터 점검', '다른 관점의 분석과 데이터 현황을 확인합니다')
    with st.container(key='card_more'):
        t1, t2 = st.tabs(['추가 분석', '데이터 점검'])
        with t1:
            st.caption('이 업데이트와 같은 기준으로 다른 관점에서 볼 수 있습니다.')
            cols = st.columns(3)
            for col, (pg, desc) in zip(cols, (('업데이트 비교', '4건을 같은 기준으로 비교'), ('국가별 반응', '국가 하나를 골라 업데이트별 반응'),
                                              ('업데이트 구성', '공지 항목 분류 전체'))):
                col.button(pg, key=f'go_{pg}', on_click=ui.goto, args=(pg,), width='stretch')
                col.caption(desc)
        with t2:
            rows = ui.data_checks(env.project, env.data, env.ctx, env.rep['window'])
            if rows:
                ui.table(pd.DataFrame(rows))
            else:
                st.write('점검에서 발견된 문제가 없습니다.')
            ctx = env.ctx
            st.caption(f'자료 기간 {ctx.rev.index.min():%Y-%m-%d} ~ {ctx.rev.index.max():%Y-%m-%d} (매출) / {ctx.dau.index.min():%Y-%m-%d} ~ {ctx.dau.index.max():%Y-%m-%d} (DAU).')


def _glossary(env):
    n = env.rep['window']
    with st.expander('지표 정의 (이 화면의 용어와 계산 기준)'):
        st.markdown(
            f'- **D0**: 업데이트 당일입니다. **이전 {n}일**은 D-{n}~D-1, **이후 {n}일**은 D0~D+{n - 1}(당일 포함)이며 달력 주가 아닙니다. 아래 일별 추이 차트에서 사용합니다.\n'
            f'- **달력 주(월~일) 기준**: 핵심 KPI·주요 발견·국가별 비교의 "주간 변화율"은 D0이 포함된 월~일(업데이트 주) vs 그 직전 월~일(전주)을 비교합니다. 업데이트 주에 D0 이전 날이 포함될 수 있습니다.\n'
            f'- **추정 매출 주간 합계**: 달력 주 7일 합계입니다. **일평균 DAU**: 달력 주 7일 평균입니다. 7일 데이터가 없으면 "계산 불가"로 표시합니다.\n'
            f'- **{n}일 전 같은 요일 비교**: 하루 단위 참고값입니다. 업데이트 효과를 직접 측정하는 지표가 아닙니다.\n'
            f'- **DAU**: {report.DAU_NOTE}\n'
            '- **추정 매출**: Sensor Tower 추정치이며 원본 CSV의 단위 그대로입니다 (통화·집계 범위 미확인).\n'
            '- **집계 범위**: "공통 N개국"은 매출·DAU 파일 모두에 있는 개별 국가를 같은 목록으로 합산합니다. "파일 전체 합계"는 각 파일의 기타 등을 포함하며 두 파일의 국가 구성이 다릅니다.')


def render(env):
    _hero(env)
    st.write('')
    _kpis(env)
    _findings(env)
    _hypothesis(env)
    _glossary(env)
    _response(env)
    _comparison(env)
    _daily_table(env)
    _narrative(env)
    _more(env)
