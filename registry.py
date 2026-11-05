"""프로젝트(게임) 등록·불러오기 — Streamlit 의존 없음.

프로젝트 1개 = projects/<id>/ 폴더 1개
    project.json   이름, 데이터 출처·주의, 범주 목록, 파일 이름
    revenue.csv    국가별 추정 매출 (CSV)
    dau.csv        국가별 DAU (CSV)
    updates.json   업데이트 공지 요약·분류 (등록된 업데이트만 분석 대상)

새 게임은 같은 형식의 폴더를 projects/ 아래에 추가하면 앱의 프로젝트 목록에 나타납니다.
등록되지 않은 프로젝트·업데이트·데이터는 만들지 않습니다.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from analysis import merge_frames, read_csv_checked

# ── 프로젝트별 데이터 유효 기간 제한 ─────────────────────────────────
# 원본 CSV는 변경하지 않으며, 로딩 시 슬라이싱으로만 적용합니다.
# 이 날짜(포함)까지만 유효 데이터로 사용합니다.
_PROJECT_CUTOFFS = {
    'cookierun_crumble': '2026-10-27',
    'maple_idle': '2026-10-27',
}
_PROJECT_CUTOFF_REASONS = {
    'cookierun_crumble': '2026-10-28 이후 데이터의 정확성이 확인되지 않음',
    'maple_idle': '2026-10-28 이후 데이터의 정확성이 확인되지 않음',
}
_PROJECT_NEXT_UPDATES = {
    # 마지막 업데이트의 다음 D0 — 집계된 적 없는 주기의 종료일을 확정하는 데만 사용
    'cookierun_crumble': '2026-11-05',
    'maple_idle': '2026-11-05',
}

@dataclass
class Project:
    id: str
    name: str
    root: Path
    meta: dict
    updates: list = field(default_factory=list)
    issues: list = field(default_factory=list)  # [(수준, 메시지)] 등록 자료 점검 결과

    @property
    def categories(self):
        return self.meta['categories']

    def path(self, key):
        return self.root / self.meta['files'][key]


def _norm_items(items, categories, date):
    """items: {범주: [문자열 | {"text","kind"}]} → (범주: [{'text','kind'}], 이슈)"""
    out, issues = {}, []
    for cat in categories:
        out[cat] = []
        for x in items.get(cat, []):
            if isinstance(x, str):
                out[cat].append({'text': x, 'kind': ''})
            elif isinstance(x, dict) and x.get('text'):
                out[cat].append({'text': str(x['text']), 'kind': str(x.get('kind', ''))})
            else:
                raise ValueError(f'{date}: "{cat}" 항목 형식이 올바르지 않습니다 (문자열 또는 text 키가 있는 객체).')
    for cat in items:
        if cat not in categories:
            issues.append(('경고', f'{date}: 등록되지 않은 범주 "{cat}"는 무시되었습니다.'))
    return out, issues


def normalize_updates(raw_list, categories):
    """updates.json 내용을 검사·정규화. 치명적 오류는 ValueError.
    반환: (업데이트 목록(날짜순), 이슈). 각 업데이트의 items는 {범주: [문자열]} 형태이고
    items_detail은 {범주: [{'text','kind'}]} 형태입니다."""
    if not isinstance(raw_list, list) or not raw_list:
        raise ValueError('updates.json에 등록된 업데이트가 없습니다.')
    seen, ups, issues = set(), [], []
    for r in raw_list:
        for key in ('date', 'title', 'items'):
            if key not in r:
                raise ValueError(f'업데이트 항목에 "{key}"가 없습니다: {str(r)[:60]}')
        try:
            d = pd.Timestamp(r['date'])
        except Exception:
            raise ValueError(f'날짜 형식이 올바르지 않습니다: {r["date"]} (예: 2026-09-23)')
        date = d.strftime('%Y-%m-%d')
        if date in seen:
            raise ValueError(f'같은 날짜의 업데이트가 중복 등록되었습니다: {date}')
        seen.add(date)
        detail, iss = _norm_items(r['items'], categories, date)
        issues += iss
        ups.append({
            'date': date, 'type': r.get('type', ''), 'title': r['title'], 'base_gap': int(r.get('base_gap', 0) or 0),
            'source': r.get('source', '사용자 전달 공지 요약 (원문 전체 아님)'),
            'items_detail': detail, 'items': {c: [x['text'] for x in v] for c, v in detail.items()},
            'confounds': list(r.get('confounds', [])), 'hypotheses': list(r.get('hypotheses', [])),
            'pending_review': list(r.get('pending_review', [])),
        })
    return sorted(ups, key=lambda u: u['date']), issues


def load_project(root):
    root = Path(root)
    meta = json.loads((root / 'project.json').read_text(encoding='utf-8'))
    for key in ('id', 'name', 'files', 'categories'):
        if key not in meta:
            raise ValueError(f'{root.name}/project.json에 "{key}"가 없습니다.')
    p = Project(id=meta['id'], name=meta['name'], root=root, meta=meta)
    raw = json.loads((root / meta['files']['updates']).read_text(encoding='utf-8'))
    p.updates, p.issues = normalize_updates(raw, meta['categories'])
    for key in ('revenue', 'dau'):
        if not p.path(key).exists():
            p.issues.append(('오류', f'{meta["files"][key]} 파일이 없습니다.'))
    return p


def discover_projects(projects_dir):
    """projects_dir 아래 project.json이 있는 폴더를 모두 불러옵니다. 읽기에 실패한 폴더는 (폴더, 사유)로 따로 돌려줍니다."""
    found, failed = [], []
    for d in sorted(Path(projects_dir).glob('*/project.json')):
        try:
            found.append(load_project(d.parent))
        except Exception as e:  # 한 프로젝트의 오류가 다른 프로젝트를 막지 않도록
            failed.append((d.parent.name, str(e)))
    return found, failed


@dataclass
class ProjectData:
    rev: pd.DataFrame
    dau: pd.DataFrame
    issues: list
    merge_info: dict       # {'rev': info|None, 'dau': info|None}
    data_cutoff: str = None        # 적용된 cutoff 날짜 (없으면 None)
    data_cutoff_reason: str = None # cutoff 사유
    next_update_date: str = None   # 마지막 업데이트의 다음 D0 (알려진 경우)


def load_project_data(project, extra_rev=None, extra_dau=None, overwrite=False):
    """등록된 CSV를 읽고, 업로드 파일이 있으면 기간 확장·국가 보완 목적으로 병합합니다.
    겹치는 값은 기본적으로 등록 데이터를 유지하고 충돌 건수를 알려줍니다.
    프로젝트별 data_cutoff가 있으면 해당 날짜(포함)까지만 사용합니다 (CSV 미변경)."""
    rev, ri = read_csv_checked(project.path('revenue'))
    dau, di = read_csv_checked(project.path('dau'))
    issues = [('매출 CSV', *i) for i in ri] + [('DAU CSV', *i) for i in di]
    info = {'rev': None, 'dau': None}
    for key, extra, base in (('rev', extra_rev, rev), ('dau', extra_dau, dau)):
        if extra is None:
            continue
        label = '매출' if key == 'rev' else 'DAU'
        add, add_issues = read_csv_checked(extra)
        issues += [(f'업로드 {label} CSV', *i) for i in add_issues]
        merged, minfo = merge_frames(base, add, overwrite=overwrite)
        info[key] = minfo
        if key == 'rev':
            rev = merged
        else:
            dau = merged
    # 데이터 유효 기간 cutoff 적용 (원본 CSV 미변경, 슬라이싱만)
    cutoff_str = _PROJECT_CUTOFFS.get(project.id)
    cutoff_reason = _PROJECT_CUTOFF_REASONS.get(project.id)
    if cutoff_str:
        cutoff_ts = pd.Timestamp(cutoff_str)
        rev = rev[rev.index <= cutoff_ts]
        dau = dau[dau.index <= cutoff_ts]
    next_upd_str = _PROJECT_NEXT_UPDATES.get(project.id)
    return ProjectData(rev=rev, dau=dau, issues=issues, merge_info=info,
                       data_cutoff=cutoff_str, data_cutoff_reason=cutoff_reason,
                       next_update_date=next_upd_str)
