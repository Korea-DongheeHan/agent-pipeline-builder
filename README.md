# graph-builder

**yml + 프롬프트 파일**로 멀티 에이전트 그래프 파이프라인 — 그래프(루프(하네스)) —
을 정의하고 실행하는 Claude Code 메타 스킬 + 러너.

- 사용자: `pipeline.yml` + `prompts/*.md` 작성 (스킬이 스캐폴딩)
- 러너(`scripts/run_graph.py`): 실행, 상태 관리, 조건 분기, 병렬, 피드백 루프
- 노드 = `claude -p` 헤드리스 서브 에이전트, 엣지 = 트리거(조건·루프)

## 빠른 시작

```bash
# 검증 → 시각화 → 모의 실행 → 실제 실행
python3 scripts/run_graph.py examples/point-leave/pipeline.yml --validate
python3 scripts/run_graph.py examples/point-leave/pipeline.yml --mermaid
python3 scripts/run_graph.py examples/point-leave/pipeline.yml --mock
python3 scripts/run_graph.py examples/point-leave/pipeline.yml
```

의존성 없음 — Python 3 표준 라이브러리 + claude CLI 만 있으면 된다.
(PyYAML 이 있으면 사용하고, 없으면 내장 미니 YAML 파서로 폴백)

## 기능

| 기능 | 방법 |
|---|---|
| Fan-Out (병렬) | `to: [impl-a, impl-b]` |
| Fan-In (동기화) | 노드 `join: all` (기본) / `join: any` |
| 조건 분기 | `when: [{type: STATUS, status: FAILED}]`, `{type: OUTPUT, key: route, equals: heavy}` |
| 피드백 루프 | 엣지에 `loop: {max: 3, on_exhausted: FAIL | <노드id>}` |
| 의도적 실패 종결 | `to: FAIL` |
| 상태 관리·재개 | `.graph-runs/<run-id>/state.json`, `--resume RUN_ID` (성공 노드 캐시 재사용) |
| 모의 실행 | `--mock`, `--mock-status NODE=FAILED,SUCCEEDED`, `--mock-output 'NODE={...}'` |
| 시각화·계획 | `--mermaid`, `--dry-run`, `--validate` |
| 전용 에이전트 재사용 | 노드 `agent: point-analyst` → `claude --agent` |

에이전트는 작업 후 마지막 줄에 `GRAPH_STATUS: SUCCEEDED|FAILED` 를 보고하고
(러너가 프로토콜을 프롬프트에 자동 주입), 분기용 값은
`GRAPH_OUTPUT: {"key": "value"}` 로 넘긴다.

## 구조

```
SKILL.md                    # 메타 스킬 — 팀 성격(development/workflow)별 스캐폴딩 절차
scripts/run_graph.py        # 오케스트레이션 러너 (단일 파일)
references/yml-spec.md      # pipeline.yml 전체 스펙
references/prompt-guide.md  # 프롬프트 작성 규칙 + 하네스 스킬 변환 매핑
templates/dev-team/         # development 템플릿: 설계→병렬 구현→테스트→리뷰+피드백 루프
templates/workflow/         # workflow 템플릿: 태스크 체인 + OUTPUT 조건 분기
examples/point-leave/       # 배치 태스크 체인 예제
examples/point-dev-graph/   # point-dev 하네스 스킬의 그래프 변환 예제
```

## 스킬 설치

```bash
ln -s "$(pwd)" ~/.claude/skills/graph-builder   # 개인 스킬로
# 또는 프로젝트 스킬: <프로젝트>/.claude/skills/graph-builder 에 복사
```
