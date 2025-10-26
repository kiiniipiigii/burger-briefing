# Burger Industry Daily Briefing (Slack)
버거 업계 신제품/콜라보 관련 소식을 매일 08:30 KST에 Slack으로 전송합니다. GitHub Actions로 서버 없이 구동됩니다.

## 빠른 시작
1) 이 저장소를 본인 계정으로 Import 또는 Fork
2) GitHub → Settings → Secrets and variables → Actions 에서 `SLACK_WEBHOOK` 추가
3) Actions 탭에서 워크플로우 실행(수동 실행 가능), 이후 매일 자동 실행

## 커스터마이즈
- `main.py`에서 RSS 소스(`RSS_FEEDS`), 키워드(`KEYWORDS`), 브랜드 힌트(`BRAND_HINTS`) 수정
- 요약 품질을 높이고 싶으면 LLM 요약 부분 주석 해제(모델/키 필요)
