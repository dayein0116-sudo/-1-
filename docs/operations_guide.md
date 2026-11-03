# GUI 운영 가이드 — 게임 등록 및 데이터 갱신

> 대상: 관리자 (데이터 등록·갱신 담당)  
> 전제: Python 분석 로직은 변경하지 않습니다. 파일 추가·수정만으로 게임을 등록하거나 갱신합니다.

---

## 1. 폴더 구조

```
gui/
  projects/
    cookierun_crumble/      ← 기존 게임 (참고용)
    new_game_id/            ← 신규 게임 (폴더명 = id)
      project.json
      revenue.csv
      dau.csv
      updates.json
  templates/                ← 신규 등록용 템플릿
    project.json
    revenue.csv
    dau.csv
    updates.json
```

앱은 `projects/` 하위의 `project.json` 이 있는 폴더를 모두 자동 탐색합니다.  
폴더 추가 후 앱을 재시작(또는 Streamlit Cloud 재배포)하면 게임 목록에 나타납니다.

---

## 2. 신규 게임 등록 절차

### 단계 1 — 폴더 생성

```
projects/<game_id>/
```

- `game_id`: 영문 소문자, 숫자, 언더바(`_`)만 사용. 이후 변경하지 않습니다.
- **`game_id`는 `project.json`의 `id` 값과 반드시 일치해야 합니다.**

### 단계 2 — `project.json` 작성

`templates/project.json`을 복사해 다음 항목을 채웁니다.

| 필드 | 필수 | 설명 |
|---|---|---|
| `id` | ✅ | 폴더명과 동일하게 입력 |
| `name` | ✅ | 앱에 표시될 게임 이름 |
| `files.revenue` | ✅ | 매출 CSV 파일명 (기본: `revenue.csv`) |
| `files.dau` | ✅ | DAU CSV 파일명 (기본: `dau.csv`) |
| `files.updates` | ✅ | 업데이트 파일명 (기본: `updates.json`) |
| `categories` | ✅ | 8개 카테고리 목록 — 게임마다 커스텀 가능, `updates.json`과 반드시 일치 |
| `game` | — | 게임 공식 명칭 (표시용) |
| `data_source` | — | 데이터 출처 (예: `Sensor Tower 추정치`) |
| `data_note` | — | 데이터 주의사항 |
| `max_countries` | — | 국가 표시 최대 수 (기본: 10) |
| `common_countries` | — | 없으면 매출·DAU 양쪽에 있는 모든 국가가 자동 지정. 특정 국가만 공통 분석에 포함할 때 명시 |

**`categories` 주의:** `updates.json`의 `items` 키와 정확히 일치해야 합니다. 오타가 있으면 경고(데이터 누락) 또는 오류가 발생합니다.

### 단계 3 — `revenue.csv` 작성

```csv
날짜,대한민국 수익 (절대적),미국 수익 (절대적),일본 수익 (절대적),기타 수익 (절대적)
2026-01-01,150000.00,80000.00,60000.00,25000.00
2026-01-02,140000.00,75000.00,58000.00,24000.00
```

| 규칙 | 내용 |
|---|---|
| 첫 번째 열 헤더 | `날짜` 권장 (다른 이름도 허용, 단 첫 열이 날짜로 자동 처리됨) |
| 날짜 형식 | `YYYY-MM-DD` 권장. `YYYY/MM/DD`도 인식하나 일관성을 위해 하이픈 사용 |
| 국가 열 헤더 | `{국가명} 수익 (절대적)` — `수익 (절대적)` 접미사는 로더가 자동 제거, 실제 컬럼명은 `{국가명}` |
| 집계 불가 국가 | `기타 수익 (절대적)` — 파일 전체 합계에 포함되나 공통 분석에서 제외 |
| 날짜 연속성 | 하루도 빠지면 안 됩니다. 누락일이 있으면 그 날짜가 걸린 업데이트는 "자료 부족"으로 처리됩니다 |
| 값 | 소수점 허용. 빈 칸 허용(NaN으로 처리) — 단, 분석 대상 기간에 빈 칸이 많으면 결과 품질 저하 |
| 인코딩 | UTF-8 또는 UTF-8-BOM (`utf-8-sig`) |

### 단계 4 — `dau.csv` 작성

revenue.csv와 동일한 규칙. 국가 열 헤더는 `{국가명} DAU (절대적)`.

```csv
날짜,대한민국 DAU (절대적),미국 DAU (절대적),일본 DAU (절대적),기타 DAU (절대적)
2026-01-01,50000,30000,25000,15000
```

- revenue.csv와 날짜 범위가 다를 수 있으나 **업데이트일 ± 7일** 이상 겹치는 기간이 있어야 분석 가능합니다.
- 국가 구성이 revenue.csv와 달라도 됩니다. 양쪽에 모두 있는 국가가 "공통 국가"가 됩니다.

### 단계 5 — `updates.json` 작성

```json
[
  {
    "date": "2026-02-05",
    "title": "업데이트 공지 기준 제목",
    "confounds": [],
    "base_gap": 0,
    "items": {
      "신규 캐릭터·수집": ["캐릭터명"],
      "성장 시스템": [],
      ...
    },
    "hypotheses": [],
    "pending_review": []
  }
]
```

| 필드 | 필수 | 규칙 |
|---|---|---|
| `date` | ✅ | `YYYY-MM-DD`. 중복 불가 |
| `title` | ✅ | 공지 기준 제목 (임의 요약 금지) |
| `items` | ✅ | `project.json`의 `categories`와 동일한 키 목록. 없는 카테고리는 빈 배열 `[]` |
| `confounds` | — | 동시 투입 요소 목록. 개별 효과를 분리할 수 없는 항목 명시 |
| `base_gap` | — | 기본값 `0`. 모든 업데이트에 `0` 유지 (정책) |
| `hypotheses` | — | 해석 가설 목록 |
| `pending_review` | — | 원문 불명확·검토 보류 항목 |

---

## 3. 기존 게임 데이터 기간 연장 절차

### 매월 데이터 갱신 (예: 10월 → 11월)

1. `revenue.csv` 파일 끝에 새 날짜 행 추가 (기존 행 수정 금지)
2. `dau.csv` 파일 끝에 새 날짜 행 추가 (기존 행 수정 금지)
3. 해당 기간에 업데이트가 있었으면 `updates.json`에 항목 추가
4. 앱 재시작 또는 Streamlit Cloud 재배포

**절대 하지 말아야 할 것:**
- 기존 날짜의 값 수정 (분석 재현성 파괴)
- 날짜 순서 변경 (로더가 자동 정렬하지만 혼란 방지)
- 날짜 범위 중간에 빈 날짜 삽입 없이 건너뜀

### 신규 국가 열 추가

1. revenue.csv 또는 dau.csv에 새 국가 열 추가
2. 기존 날짜 행에 대한 해당 국가 값이 없으면 빈 칸으로 둠 (NaN)
3. `project.json`의 `common_countries`가 없으면 자동으로 새 국가가 공통 국가에 포함됨
4. 특정 국가만 공통 분석에 포함하려면 `common_countries` 명시

---

## 4. 등록 전 검증 체크리스트

```
[ ] project.json의 id가 폴더명과 일치하는가
[ ] project.json의 categories 목록과 updates.json의 items 키가 완전히 일치하는가
[ ] revenue.csv와 dau.csv의 날짜 범위에 빠진 날이 없는가
[ ] 첫 번째 업데이트일 기준으로 이전 7일 데이터가 있는가 (이전 7일 없으면 첫 업데이트 분석 불가)
[ ] 각 업데이트일 이후 7일 데이터가 있는가 (없으면 해당 업데이트 "자료 부족" 처리)
[ ] updates.json의 날짜가 중복되지 않는가
[ ] CSV 열 헤더 인코딩이 UTF-8-BOM인가 (Excel 저장 시 기본값)
[ ] common_countries에 있는 국가명이 revenue.csv와 dau.csv 양쪽에 존재하는가
[ ] 새 게임 등록 후 앱에서 "읽지 못한 프로젝트" 목록에 나타나지 않는가
```

---

## 5. 사람이 직접 판단해야 하는 항목

자동 검증이 불가능하며 관리자가 직접 판단해야 합니다.

| 항목 | 이유 |
|---|---|
| `confounds` 목록 작성 | 동시 투입 요소 중 어떤 것이 효과 분리를 어렵게 하는지 판단 |
| `common_countries` 선정 | 국가 기여율, 데이터 연속성, 분석 일관성을 고려해 결정. 이후 변경 시 과거 결과와 비교 불가 |
| `pending_review` 작성 | 원문 부재 또는 검증 불가 항목은 임의 생성하지 않고 보류 표시 |
| 데이터 이상값 판단 | 검증 도구가 경고를 표시하지만 실제 운영 이슈인지 Sensor Tower 오류인지는 사람이 판단 |
| 기간 연장 시 국가 열 추가 여부 | Sensor Tower가 신규 국가를 추가한 경우, 기존 기간에 대한 소급 데이터가 없으면 NaN으로 처리됨을 확인 후 추가 |

---

## 6. 검증 방법

등록 후 터미널에서 확인합니다.

```bash
cd gui
python -c "
import registry
from pathlib import Path
p = registry.load_project(Path('projects/<game_id>'))
print('name:', p.name)
print('updates:', [u['date'] for u in p.updates])
print('issues:', p.issues)
d = registry.load_project_data(p)
print('rev shape:', d.rev.shape, '  dau shape:', d.dau.shape)
print('data issues:', d.issues)
"
```

```bash
python -m pytest tests/ -q
```

`49 passed` 가 나오면 기존 게임의 분석 결과에 영향이 없음을 의미합니다.

---

## 7. 배포

Streamlit Cloud 기준:

1. 변경 파일을 Git commit & push
2. Streamlit Cloud가 자동으로 재배포
3. 재배포 후 앱에서 새 게임이 게임 선택 목록에 나타나는지 확인

로컬 실행:
```bash
python -m streamlit run app.py
```
