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
    for cat in cats:
        its = u_sel['items_detail'].get(cat, [])
        if its:
            st.markdown(f'**{cat}**')
            st.markdown(_cell(its), unsafe_allow_html=True)

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

