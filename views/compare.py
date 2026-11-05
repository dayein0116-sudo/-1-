"""업데이트 비교 — 등록된 업데이트 주기(D0~다음D0-1) 기준 매출 성과를 나란히 봅니다.
데이터 품질 cutoff는 registry.load_project_data()에서 전역 적용되므로 여기서는 슬라이싱하지 않습니다.
"""
import pandas as pd
import streamlit as st

import analysis as an
import charts
import report
import ui
from ui import fmt_range, fp, fx


def _asterisk_note(cy, cutoff_reason):
    """미완료 주기의 별표 주석 한 줄 생성. 완료 주기는 None."""
    if cy['complete']:
        return None
    mon = cy['date'][5:]  # MM-DD
    v, d = cy['valid_days'], cy['days']
    if cy['truncated']:
        # 완성된 주기보다 먼저 cutoff 발생 (쿠키런 10/22)
        why = cutoff_reason or '데이터 정확성 미확인'
        return (f"* {mon} 업데이트는 전체 {d}일 주기 중 {cy['d_end']}까지의 {v}일만 집계. "
                f"{why}으로 이후 데이터 제외.")
    if not cy.get('open_ended') and v < d:
        # 다음 업데이트 날짜 확정, 데이터가 주기 끝에 미치지 못함 (메이플 10/15)
        return (f"* {mon} 업데이트는 전체 {d}일 주기 중 {cy['d_end']}까지의 {v}일만 집계.")
    # 완전히 열린 주기 (open_ended)
    return (f"* {mon} 업데이트: 다음 업데이트 일정이 미확정이어서 "
            f"현재까지 {v}일만 집계했습니다. "
            "주기 미완료이므로 완료된 주기와 직접 비교하지 않습니다.")


def render(env):
    ctx, n, ups, d_sel = env.ctx, env.window, env.project.updates, env.upd['date']
    rs, ds = ctx.series(env.scope)

    # cutoff 정보는 registry가 ProjectData에 저장 — 슬라이싱은 이미 완료
    cutoff_str = env.data.data_cutoff
    cutoff_reason = env.data.data_cutoff_reason
    if cutoff_str:
        st.caption(
            f'데이터 품질 제한: {cutoff_str} 이후 데이터 제외 (원본 CSV 미변경) '
            f'· {cutoff_reason} · 집계 범위: {env.rep["scope_label"]}'
        )

    # ── 업데이트 주기별 추정 매출 ──
    # cutoff_date와 next_update_date 모두 명시적으로 전달:
    # - cutoff_date: mid-cycle truncation 감지 (마지막 업데이트와 구분)
    # - next_update_date: 마지막 주기의 전체 예정 일수 확정 (days vs valid_days 분리)
    cycles = an.cycle_compare(rs, ups, cutoff_date=cutoff_str,
                              next_update_date=env.data.next_update_date)

    rows, curs, prevs, labels = [], [], [], []
    asterisk_notes = []
    for cy in cycles:
        needs_asterisk = not cy['complete']
        star = '*' if needs_asterisk else ''
        v, d = cy['valid_days'], cy['days']

        if cy['complete']:
            status = f'완료 ({d}일)'
        elif v < d:
            status = f'부분 집계 ({v}/{d}일)'
        else:
            status = f'진행 중 ({v}일)'

        if cy['can_compare'] and cy['change_pct'] is not None:
            basis = '합계' if cy['change_type'] == 'sum' else '일평균'
            change_str = f"{cy['change_pct']:+.1f}%  ({basis} 기준)"
        else:
            change_str = '비교 불가 — 주기 미완료'

        rows.append({
            '날짜': cy['date'],
            '업데이트': cy['title'] + star,
            '기간': f"{cy['d_start'][5:]}~{cy['d_end'][5:]}",
            '일수': f"{cy['valid_days']}/{cy['days']}일",
            '주기 합계': ui.fmt_krw(cy['total']),
            '일평균': ui.fmt_krw(cy['daily_avg']),
            '직전 주기 대비': change_str,
            '상태': status,
        })
        # 차트 라벨에도 별표 적용
        labels.append(cy['date'][5:] + star)
        curs.append(cy['daily_avg'] * ui.KRW_RATE / 1e8 if cy['daily_avg'] else None)
        prevs.append(cy['prev_daily_avg'] * ui.KRW_RATE / 1e8 if cy.get('prev_daily_avg') else None)

        note = _asterisk_note(cy, cutoff_reason)
        if note:
            asterisk_notes.append(note)

    with st.container(key='card_cmp_rev'):
        ui.card_title(
            '추정 매출 — 업데이트 주기별',
            f'D0~다음D0-1 성과 · 일수 = 유효/전체 · 원화 환산 (1 USD = 1,350원) · {env.rep["rev_scope_label"]}'
        )
        ui.table(pd.DataFrame(rows))
        ui.show(charts.fig_group_bars(labels, prevs, curs, '직전 주기 일평균', '이번 주기 일평균', charts.BLUE, unit='억원'))
        # 별표 각주
        if asterisk_notes:
            for note in asterisk_notes:
                st.caption(note)
        if any(cy['truncated'] for cy in cycles) or any(not cy['complete'] for cy in cycles):
            st.caption('* 표시 업데이트는 주기가 완료되지 않아 직전 완료 주기와 성과를 직접 비교하지 않습니다.')

    # ── DAU (달력 주 기준 — 기존 유지) ──
    cur_l, prev_l = report.cal_period_labels()
    rows_dau, prevs_dau, curs_dau = [], [], []
    for u in ups:
        w = an.week_compare_cal(ds, u['date'])
        prevs_dau.append(w['prev_mean'] if w else None)
        curs_dau.append(w['cur_mean'] if w else None)
        rows_dau.append({
            '날짜': u['date'], '업데이트': u['title'],
            f'{prev_l} 일평균 DAU': f"{w['prev_mean']:,.0f}" if w else '분석 불가',
            f'{cur_l} 일평균 DAU': f"{w['cur_mean']:,.0f}" if w else '분석 불가',
            '증감률': fp(w['pct']) if w else '분석 불가',
        })
    dau_labels = [u['date'][5:] for u in ups]
    with st.container(key='card_cmp_dau'):
        ui.card_title('DAU', f'{cur_l} 일평균 DAU vs {prev_l} 일평균 DAU · {env.rep["dau_scope_label"]}')
        ui.table(pd.DataFrame(rows_dau))
        ui.show(charts.fig_group_bars(dau_labels, prevs_dau, curs_dau, prev_l, cur_l, charts.GREEN))
        st.caption(report.DAU_NOTE + ' 매출과 결합한 지표(ARPDAU 등)는 계산하지 않습니다.')

    # ── 국가별 추정 매출 (달력 주 기준 — 기존 유지) ──
    with st.container(key='card_cmp_country'):
        ui.card_title(
            '국가별 추정 매출',
            '업데이트 주 금액(원화 환산) 및 증감률 · 달력 주(월~일) 기준 — 증감률만으로 판단하지 말고 규모를 함께 보세요'
        )
        dates = [u['date'][5:] for u in ups]
        mi_cols = pd.MultiIndex.from_tuples(
            [('국가', '')] + [(d, s) for d in dates for s in ['금액', '증감률']]
        )
        # ctx.rev는 이미 cutoff 적용 — 별도 필터링 불필요
        complete_countries = [
            c for c in ctx.rev_countries
            if all(an.week_compare_cal(ctx.rev[c], u['date']) is not None for u in ups)
        ]
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
                    return 'color: #c0504d; font-weight: 700' if pct > 0 else (
                        'color: #2f5bea; font-weight: 700' if pct < 0 else ''
                    )
                except (ValueError, AttributeError):
                    return ''

            pct_cols = [(d, '증감률') for d in dates]
            st.dataframe(df_c.style.map(_style_pct, subset=pct_cols), use_container_width=True)
        st.caption('소규모 국가는 일 규모가 작아 증감률의 변동이 큽니다.')

    # ── 달력 주(월~일) 기준 비교 — 보조 참고용 ──
    with st.expander('달력 주(월~일) 기준 비교 — 보조 참고용', expanded=False):
        st.caption(
            f'비교 기준: {prev_l}(직전 월–일) 대비 {cur_l}(D0 포함 월–일) · '
            f'집계 범위: {env.rep["scope_label"]} · '
            '달력 주는 D0 요일에 따라 D0 이전 날이 업데이트 주에 포함될 수 있어 주기별 비교와 수치가 다릅니다.'
        )
        rows_cal, labs_cal, prevs_cal, curs_cal = [], [], [], []
        for u in ups:
            w = an.week_compare_cal(rs, u['date'])
            lab = u['date'][5:]
            labs_cal.append(lab)
            prevs_cal.append(w['prev_sum'] * ui.KRW_RATE / 1e8 if w else None)
            curs_cal.append(w['cur_sum'] * ui.KRW_RATE / 1e8 if w else None)
            rows_cal.append({
                '날짜': u['date'], '업데이트': u['title'],
                f'{prev_l} 추정 매출 합계': ui.fmt_krw(w['prev_sum'] if w else None),
                f'{cur_l} 추정 매출 합계': ui.fmt_krw(w['cur_sum'] if w else None),
                '증감액': ui.fmt_krw_delta(w['cur_sum'] - w['prev_sum'] if w else None),
                '증감률': fp(w['pct']) if w else '분석 불가',
            })
        no_data = [u['date'][5:] for u in ups if an.week_compare_cal(rs, u['date']) is None]
        ui.table(pd.DataFrame(rows_cal))
        ui.show(charts.fig_group_bars(labs_cal, prevs_cal, curs_cal, prev_l, cur_l, charts.BLUE, unit='억원'))
        if no_data:
            st.caption(
                f'막대가 없는 업데이트 ({", ".join(no_data)}): 달력 기준 전주(월~일) 7일이 '
                f'CSV 데이터 범위 밖이라 비교 불가입니다.'
            )
