"""업데이트 구성 — 공지 요약을 범주별로 분류해 보여줍니다."""
import pandas as pd
import streamlit as st

import ui
from ui import esc


def _cell(its):
    """항목 목록을 HTML로 반환 — col.markdown(unsafe_allow_html=True)으로 렌더링.
    markdown() 대신 HTML을 써서 ~~취소선~~ 등 마크다운 서식이 적용되지 않도록 한다."""
    if not its:
        return '<span style="color:#9aa5c4">—</span>'
    rows = []
    for x in its:
        text = esc(x['text'])
        kind = f' <code style="font-size:10px;padding:1px 4px">{esc(x["kind"])}</code>' if x.get('kind') else ''
        rows.append(f'<li>{text}{kind}</li>')
    return f'<ul style="margin:0;padding-left:1.2em">{"".join(rows)}</ul>'


def render(env):
    ups, cats = env.project.updates, env.project.categories
    st.subheader('공지 항목 분류')
    st.caption('전달받은 공지 원문을 요약·분류한 것이며 원문 전체가 아닙니다. "신규 BM 가능성"은 공지에 표기된 뽑기·패스·픽업 구조만 적은 것으로 실제 결제 구조나 매출 기여는 확인되지 않았습니다.')

    # 단독 뷰: 선택한 업데이트 하나
    idx = st.selectbox('업데이트 선택', range(len(ups)),
                       format_func=lambda i: f"{ups[i]['date']} · {ups[i]['title']}", key='struct_upd_sel')
    u_sel = ups[idx]

    # ── 업데이트 주기 매출 (업데이트 비교 화면과 동일한 집계 기준) ──
    cy_sel = next((c for c in env.rev_cycles if c['date'] == u_sel['date']), None)
    if cy_sel:
        is_first = (u_sel['date'] == env.rev_cycles[0]['date'])
        if is_first and env.pre_period and cy_sel['daily_avg']:
            pct = (cy_sel['daily_avg'] / env.pre_period['daily_avg'] - 1) * 100
            chg = f"{pct:+.1f}% (초기 운영 기간 대비)"
            prev_avg = env.pre_period['daily_avg']
        elif cy_sel['can_compare'] and cy_sel['change_pct'] is not None:
            chg = f"{cy_sel['change_pct']:+.1f}%"
            prev_avg = cy_sel.get('prev_daily_avg')
        elif not cy_sel['complete']:
            chg = '비교 불가 — 주기 미완료'
            prev_avg = cy_sel.get('prev_daily_avg')
        else:
            chg = '비교 기준 없음 (첫 주기)'
            prev_avg = None
        scope_txt = (f'공통 {len(env.ctx.common)}개국' if env.scope == 'common'
                     else '전체 국가 매출(기타 포함)')
        with st.container(key='card_struct_rev'):
            ui.card_title('업데이트 주기 매출', '업데이트 비교 화면과 동일한 집계 기준')
            st.caption(f'집계 범위: {scope_txt}  ·  원화 환산: 1달러 = 1,350원')
            ui.table(pd.DataFrame([{
                '기간': f"{cy_sel['d_start'][5:]}~{cy_sel['d_end'][5:]}",
                '일수': f"{cy_sel['valid_days']}/{cy_sel['days']}일",
                '주기 합계': ui.fmt_krw(cy_sel['total']),
                '일평균': ui.fmt_krw(cy_sel['daily_avg']),
                '직전 주기 일평균': ui.fmt_krw(prev_avg),
                '직전 주기 대비': chg,
            }]))
            if is_first and env.pre_period:
                st.caption(
                    f"초기 운영 기간 ({env.pre_period['d_start'][5:]}~{env.pre_period['d_end'][5:]}, "
                    f"{env.pre_period['days']}일) 일평균: {ui.fmt_krw(env.pre_period['daily_avg'])}"
                )

    for cat in cats:
        its = u_sel['items_detail'].get(cat, [])
        if its:
            # 제목+목록을 하나의 블록으로 — Streamlit 단락 간격 없이 카테고리 간 여백만 확보
            st.markdown(
                f'<div style="margin-top:1rem"><strong>{esc(cat)}</strong>'
                + _cell(its) + '</div>',
                unsafe_allow_html=True,
            )

    # 전체 비교표 (접기)
    with st.expander('전체 업데이트 비교표 펼쳐 보기'):
        head = st.columns(len(ups))
        for col, u in zip(head, ups):
            col.markdown(f"**{u['date']}**\n\n{u['title']}")
        for cat in cats:
            st.markdown(f'---\n**{cat}**')
            for col, u in zip(st.columns(len(ups)), ups):
                col.markdown(_cell(u['items_detail'].get(cat, [])), unsafe_allow_html=True)

    st.subheader('범주별 항목 수')
    cnt = pd.DataFrame({u['date'][5:]: [len(u['items'].get(c, [])) for c in cats] for u in ups}, index=cats)
    st.dataframe(cnt)

    st.subheader('함께 투입된 요인 (식별 가능성)')
    st.caption('한 업데이트 안에서 동시에 투입된 요소는 개별 효과를 분리할 수 없습니다. 말할 수 있는 것은 업데이트 단위의 반응까지입니다.')
    for u in ups:
        st.markdown(f"**{u['date']} · {u['title']}**")
        if u['confounds']:
            st.markdown('<ul>' + ''.join(f'<li>{esc(x)}</li>' for x in u['confounds']) + '</ul>',
                        unsafe_allow_html=True)
        else:
            st.markdown('—')

    st.subheader('사업적 해석 가설')
    st.caption('공지에 명시된 목적이 아니라 공지 구성에서 추론한 가설입니다. 매출 기여를 입증하지 않으며, 근거 항목을 함께 표시합니다.')
    for u in ups:
        st.markdown(f"**{u['date']} · {u['title']}**")
        items_html = ''.join(
            f'<li>{esc(h["text"])}'
            + (f'<div class="muted" style="font-size:12px">근거 항목: {esc(" / ".join(h["basis"]))}</div>' if h['basis'] else '')
            + '</li>'
            for h in map(ui.norm_hyp, u['hypotheses'])
        )
        if items_html:
            st.markdown(f'<ul>{items_html}</ul>', unsafe_allow_html=True)

