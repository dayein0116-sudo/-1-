"""업데이트 구성 — 공지 요약을 범주별로 분류해 보여줍니다."""
import pandas as pd
import streamlit as st

import ui
from ui import esc


def _cell(its):
    if not its:
        return '—'
    return '\n'.join(f'- {x["text"]}' + (f'  `{x["kind"]}`' if x['kind'] else '') for x in its)


def render(env):
    ups, cats = env.project.updates, env.project.categories
    st.subheader('공지 항목 분류')
    st.caption('전달받은 공지 원문을 요약·분류한 것이며 원문 전체가 아닙니다. "신규 BM 가능성"은 공지에 표기된 뽑기·패스·픽업 구조만 적은 것으로 실제 결제 구조나 매출 기여는 확인되지 않았습니다.')
    head = st.columns(len(ups))
    for col, u in zip(head, ups):
        col.markdown(f"**{u['date']}**\n\n{u['title']}")
    for cat in cats:
        st.markdown(f'---\n**{cat}**')
        for col, u in zip(st.columns(len(ups)), ups):
            col.markdown(_cell(u['items_detail'].get(cat, [])))

    st.subheader('범주별 항목 수')
    cnt = pd.DataFrame({u['date'][5:]: [len(u['items'].get(c, [])) for c in cats] for u in ups}, index=cats)
    st.dataframe(cnt)

    st.subheader('함께 투입된 요인 (식별 가능성)')
    st.caption('한 업데이트 안에서 동시에 투입된 요소는 개별 효과를 분리할 수 없습니다. 말할 수 있는 것은 업데이트 단위의 반응까지입니다.')
    for u in ups:
        st.markdown(f"**{u['date']} · {u['title']}**")
        st.markdown('\n'.join(f'- {x}' for x in u['confounds']) or '—')

    st.subheader('사업적 해석 가설')
    st.caption('공지에 명시된 목적이 아니라 공지 구성에서 추론한 가설입니다. 매출 기여를 입증하지 않으며, 근거 항목을 함께 표시합니다.')
    for u in ups:
        st.markdown(f"**{u['date']} · {u['title']}**")
        for h in map(ui.norm_hyp, u['hypotheses']):
            st.markdown(f'- {h["text"]}' + (f'  \n  <span class="muted">근거 항목: {esc(" / ".join(h["basis"]))}</span>' if h['basis'] else ''), unsafe_allow_html=True)

