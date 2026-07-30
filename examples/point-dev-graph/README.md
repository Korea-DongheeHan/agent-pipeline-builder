# point-dev-graph — point-dev 하네스 스킬의 그래프 변환 예제

`~/projects/point/.claude/skills/point-dev`(오케스트레이터 스킬)의 full-team
경로를 graph-builder 형식(yml + 프롬프트)으로 변환한 예제다.

## 매핑

| point-dev (스킬) | point-dev-graph (그래프) |
|---|---|
| Phase 1-1 분석 (point-analyst 서브 에이전트) | `analyst` 노드 |
| Phase 2 팀 3인 동시 스폰 | `analyst → [implement, test]` Fan-Out |
| Phase 2 최종 통합 QA (T8) | `qa` 노드 (`join: all` Fan-In) |
| Phase 3 리뷰 (point-reviewer) | `review` 노드 |
| 수렴 루프 (FAIL 항목만 재작업) | `qa/review --FAILED--> implement` 피드백 엣지 |
| 2회 연속 FAIL 에스컬레이션 | `loop: {max: 2, on_exhausted: escalate}` |
| acceptance 판정표 (`A1…`) | 스펙·판정 프롬프트 규약 + `GRAPH_OUTPUT.failed_items` |
| 전용 에이전트 정의 (.claude/agents/point-*) | 노드 `agent:` 필드 → `claude --agent` |
| WS 산출물 (`_workspace/<브랜치>/0N_*.md`) | run 디렉토리 (`.graph-runs/<run-id>/outputs/`) |

## 스킬 대비 의도적으로 다른 것 (headless 제약)

- **스펙 게이트(Phase 1-2) 없음** — headless 실행은 사용자에게 질문할 수 없다.
  analyst 가 가정을 문서화하고, 사용자는 실행 후 가정을 검토한다.
  스펙 확정이 중요한 작업이면 그래프 실행 **전에** 대화형으로 스펙을 확정하고
  `--var requirement=` 에 확정 스펙을 넣어라.
- **팀 실시간 통신(SendMessage) 없음** — incremental QA 의 실시간 왕복 대신
  그래프 엣지(FAILED 피드백 루프)로 결함이 순환한다. 왕복 지연이 커지는 대신
  구조가 결정적(deterministic)이고 재현 가능하다.
- **Phase 0(작업공간)·Phase 4(마무리/커밋) 없음** — point-dev 규칙대로 커밋·머지는
  사람 게이트다. 브랜치 준비는 실행 전에, 커밋은 결과 검토 후에 직접 한다.
- **fast-path 없음** — 얇은 변경이면 그래프를 쓰지 말고 point-dev fast-path 를 쓰는
  편이 낫다. 그래프는 full-team 급 작업의 무인 실행에 적합하다.

## 실행

point 저장소 루트에서 실행해야 한다 (`.claude/agents/point-*` 정의와 git diff 기준).

```bash
cd ~/projects/point
python3 ~/graph-builder/scripts/run_graph.py \
  ~/graph-builder/examples/point-dev-graph/pipeline.yml \
  --var requirement="신규 가입자 첫 주문 시 2배 적립 기능 추가"
```

그래프 로직만 확인하려면(claude 호출 없이):

```bash
python3 scripts/run_graph.py examples/point-dev-graph/pipeline.yml \
  --mock --mock-status qa=FAILED,SUCCEEDED
```
