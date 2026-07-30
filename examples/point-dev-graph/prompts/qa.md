# 태스크 입력: 통합 QA (point-dev Phase 2 qa 대응)

역할·프로토콜은 point-qa 에이전트 정의를 따른다. 아래는 태스크 입력이다.

## 요구사항
{{vars.requirement}}

## 작업
선행 노드 `implement`(구현)와 `test`(테스트)의 산출물(하단 컨텍스트)을 합쳐
검증하라. **컴파일 게이트 → 단위 → 통합** 순으로 단계 실행하고, 영향
모듈만 검증한다.

1. `analyst` 스펙의 acceptance 항목(`A1, A2, ...`)별 판정표를 작성하라:
   `A1: PASS/FAIL/N-A — 근거 1줄`.
2. FAIL 항목에는 에러 원문 일부와 원인 위치(파일:라인)를 명시하라 —
   implement 노드가 이 보고만 보고 수정한다.
3. 빌드 실패 시 원인을 격리(`--info`)하되 직접 수정하지 마라.

## 규칙
- 실행하지 않은 검증을 통과로 보고하지 마라.
- 테스트 환경 불가(Docker 등) 시 정적 검증만 수행하고
  "동적 검증 미수행"을 명시하라.

## 판정
acceptance 전 항목 PASS 시 SUCCEEDED, 하나라도 FAIL 이면 FAILED.
GRAPH_OUTPUT 에 실패 항목을 담아라. 예: GRAPH_OUTPUT: {"failed_items": "A3"}
