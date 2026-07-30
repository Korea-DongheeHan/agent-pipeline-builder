# 세션 오케스트레이션 모드 — 트리 UI 관찰용 실행 규칙

러너(run_graph.py) 대신 **Claude(메인 세션)가 pipeline.yml 을 해석해 Agent 툴로
노드를 실행**하는 모드다. 각 노드가 Claude Code 트리 UI 에 서브에이전트로
표시되어 진행을 실시간 관찰할 수 있다. pipeline.yml 이 SSOT 인 것은 동일하다.

## 모드 선택 기준

| | 러너 모드 | 세션 모드 |
|---|---|---|
| 실행 보장 | 스크립트가 결정적으로 보장 | 모델의 규칙 준수에 의존 |
| 관찰성 | 콘솔 로그 + state.json | **트리 UI 실시간** |
| resume | 성공 노드 캐시 재사용 | 없음 |
| 컨텍스트 | 노드 완전 격리, 메인 세션 무관 | 메인 세션에 노드 요약 누적 |
| 용도 | 무인·배치·대규모 | 대화형·관찰 필요 시 |

## 해석 규칙 (Claude 가 반드시 준수)

1. **시작 전 구조 파악** — `--validate` 로 검증하고 `--dry-run` 으로 wave
   순서·분기·루프를 확인한다. 그래프를 임의로 재해석하지 않는다.
2. **노드 실행 = Agent 툴 1회.** prompt 구성:
   - 프롬프트 파일 내용 (`{{vars.*}}` 를 실제 값으로 치환)
   - 선행 노드 결과: 요약 + 출력 파일 경로 (전문 인라인 금지 — bounded handoff)
   - 상태 보고 지시: "작업 완료 후 응답 마지막 줄에 `GRAPH_STATUS: SUCCEEDED`
     또는 `FAILED`, 분기 판정 값이 있으면 직전 줄에 `GRAPH_OUTPUT: {json}`"
   - 노드에 `agent:` 가 있으면 해당 이름을 `subagent_type` 으로 지정한다
3. **병렬(parallel/같은 wave)** — 한 응답에서 Agent 를 동시 호출한다
   (트리 UI 에 병렬로 표시된다).
4. **Fan-In** — `join: all`(기본) 노드는 모든 비-루프 선행이 끝나야 실행,
   `join: any` 는 첫 도착 시 실행한다.
5. **조건 판정** — 서브에이전트가 보고한 GRAPH_STATUS / GRAPH_OUTPUT 으로
   엣지 조건(when / if / branch cases)을 판정한다. 마커가 없으면 SUCCEEDED
   로 간주하되 보고에 명시한다.
6. **루프 상한 엄수** — 피드백 루프(loop / 뒤로 goto)는 `max` 를 초과할 수
   없다. 초과 시 exhausted 경로를 따른다 (FAIL = 중단하고 사용자 보고,
   노드 = 그 노드로 위임).
7. **산출물 보존** — 노드별 결과 전문은
   `.graph-runs/session-<YYYYMMDD-HHMMSS>/outputs/<node>.iterN.md` 로 저장하고
   세션 컨텍스트에는 요약만 유지한다.
8. **종료** — END 도달 = 노드별 판정표와 함께 성공 보고.
   FAIL 종단·데드락·루프 소진 = 원인·근거와 함께 실패 보고.
   실행하지 않은 노드를 실행한 것으로 보고하지 않는다.
