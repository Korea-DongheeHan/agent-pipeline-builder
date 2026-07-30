# 태스크 입력: 리뷰 (point-dev Phase 3 대응)

역할·프로토콜은 point-reviewer 에이전트 정의를 따른다. 아래는 태스크 입력이다.

## 요구사항
{{vars.requirement}}

## 작업
`git diff develop...HEAD`(또는 이번 변경 범위)를 리뷰하라. 선행 노드
산출물(하단 컨텍스트)로 의도를 파악한다.

QA(qa 노드)가 실행 검증·완결성 페어를 이미 수행했으므로 중복하지 말고
**컨벤션·트랜잭션·품질**에 집중하라. 금액 부호·의존 방향은 항상 확인한다.

## 판정 기준
- **APPROVE** (GRAPH_STATUS: SUCCEEDED): blocker/major 없음 +
  acceptance 전 항목 PASS 확인.
- **REQUEST_CHANGES** (GRAPH_STATUS: FAILED): blocker/major 존재.
  각 지적에 파일:라인, 문제, 요구 수정, 해당 acceptance 항목(`A#`)을
  명시하라. minor 는 기록만 하고 판정에 반영하지 마라.
