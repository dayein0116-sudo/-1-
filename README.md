# 게임 퀵리뷰 툴

## Netlify 배포 방법 (5단계)

### 1. 사전 준비
- [GitHub 계정](https://github.com) 필요
- [Netlify 계정](https://netlify.com) 필요 (GitHub으로 가입 가능)
- [Anthropic API 키](https://console.anthropic.com) 필요

### 2. GitHub에 올리기
```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/[내아이디]/game-quickreview.git
git push -u origin main
```

### 3. Netlify에서 배포
1. [netlify.com](https://netlify.com) 접속 → Add new site → Import an existing project
2. GitHub 선택 → 저장소 선택
3. Build settings 확인:
   - Build command: `npm run build`
   - Publish directory: `build`
4. **Site configuration → Environment variables** 에서 아래 추가:
   - Key: `REACT_APP_ANTHROPIC_API_KEY`
   - Value: Anthropic 콘솔에서 발급받은 API 키
5. Deploy site 클릭

### 4. 배포 완료
- `https://[프로젝트명].netlify.app` URL 생성
- 이 URL을 노션 페이지에 `/embed` 명령으로 삽입

### 5. 노션에 삽입하는 법
노션 페이지에서:
1. `/embed` 입력
2. Netlify URL 붙여넣기
3. 완료

---

## 로컬 실행
```bash
cp .env.example .env
# .env 파일에 API 키 입력 후
npm install
npm start
```

---

## 주의사항
API 키가 프론트엔드에 노출되는 구조입니다.
팀 내부 전용으로만 사용하거나, Netlify의 Password Protection 기능으로 접근을 제한하세요.
(Site configuration → Identity or Netlify Password Protection 플러그인)
