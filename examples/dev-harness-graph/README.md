# dev-harness-graph — 오케스트레이터 하네스 스킬의 그래프 변환 예제

대화형 오케스트레이터 하네스 스킬(분석 → 팀 구현 → 리뷰 → acceptance 기반
수렴 루프 형태)을 graph-builder 형식(yml + 프롬프트)으로 변환한 예제다.
같은 형태의 하네스 스킬을 그래프로 옮길 때 이 매핑을 따른다.

## 매핑

| 하네스 스킬 (오케스트레이터) | dev-harness-graph (그래프) |
|---|---|
| 분석 Phase (서브 에이전트) | `analyst` 노드 |
| 구현 팀 동시 스폰 (implementer/test/qa) | `analyst → [implement, test]` Fan-Out |
| 최종 통합 QA | `qa` 노드 (`join: all` Fan-In) |
| 리뷰 Phase (독립 서브 에이전트) | `review` 노드 |
| 수렴 루프 (FAIL 항목만 재작업) | `qa/review --FAILED--> implement` 피드백 엣지 |
| N회 연속 FAIL 에스컬레이션 | `loop: {max: N, on_exhausted: escalate}` |
| acceptance 판정표 (`A1…`) | 스펙·판정 프롬프트 규약 + `GRAPH_OUTPUT.failed_items` |
| 전용 에이전트 정의 (.claude/agents/*) | 노드 `agent:` 필드 → `claude --agent` (주석 참조) |
| 워크스페이스 산출물 (`WS/0N_*.md`) | run 디렉토리 (`.graph-runs/<run-id>/outputs/`) |

## 스킬 대비 의도적으로 다른 것 (headless 제약)

- **대화형 스펙 게이트(AskUserQuestion) 없음** — headless 실행은 사용자에게
  질문할 수 없다. analyst 가 가정을 문서화하고, 사용자는 실행 후 가정을 검토한다.
  스펙 확정이 중요한 작업이면 그래프 실행 **전에** 대화형으로 스펙을 확정하고
  `--var requirement=` 에 확정 스펙을 넣어라.
- **팀 실시간 통신(SendMessage) 없음** — incremental QA 의 실시간 왕복 대신
  그래프 엣지(FAILED 피드백 루프)로 결함이 순환한다. 왕복 지연이 커지는 대신
  구조가 결정적(deterministic)이고 재현 가능하다.
- **작업공간 준비·마무리(커밋) Phase 없음** — 커밋·머지는 사람 게이트다.
  브랜치 준비는 실행 전에, 커밋은 결과 검토 후에 직접 한다.
- **경량(fast-path) 분기 없음** — 얇은 변경이면 그래프 대신 대화형 스킬을 쓰는
  편이 낫다. 그래프는 팀 규모 작업의 무인 실행에 적합하다.

## 실행

변경 대상 저장소 루트에서 실행한다. 저장소에 전용 에이전트 정의가 있으면
pipeline.yml 의 `agent:` 주석을 해제해 역할 정의를 재사용한다.

```bash
cd <대상 저장소>
python3 <graph-builder>/scripts/run_graph.py \
  <graph-builder>/examples/dev-harness-graph/pipeline.yml \
  --var requirement="구현할 요구사항"
```

그래프 로직만 확인하려면(claude 호출 없이):

```bash
python3 scripts/run_graph.py examples/dev-harness-graph/pipeline.yml \
  --mock --mock-status qa=FAILED,SUCCEEDED
```
