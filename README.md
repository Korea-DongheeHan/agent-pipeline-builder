# graph-builder

**yml + 프롬프트 파일**로 멀티 에이전트 그래프 파이프라인 — 그래프(루프(하네스)) —
을 정의하고 실행하는 **Claude Code 플러그인**.

```
graph-builder 플러그인 (빌더)
    │  "에이전트 팀 파이프라인 만들어줘"  →  graph-builder:build 스킬
    ▼
<project>/.claude/skills/<파이프라인명>/   ← 독자 실행 산출물 (플러그인 불필요)
    SKILL.md · pipeline.yml · prompts/ · scripts/run_graph.py
<project>/CLAUDE.md                        ← 트리거 규칙 자동 등록
```

- 사용자: `pipeline.yml` + `prompts/*.md` 만 관리 (빌더가 스캐폴딩)
- 러너(`run_graph.py`): 실행, 상태 관리, 조건 분기, 병렬, 피드백 루프
- 노드 = `claude -p` 헤드리스 서브 에이전트, 엣지 = 트리거(조건·루프)

## 설치

```
/plugin marketplace add <이 저장소 git URL 또는 로컬 경로>
/plugin install graph-builder@graph-builder-marketplace
```

설치 후 아무 프로젝트에서 "에이전트 팀 파이프라인 만들어줘"라고 하면
`graph-builder:build` 스킬이 설계 확인(mermaid) → `.claude/skills/` 하네스 생성 →
CLAUDE.md 등록 → mock 검증 → 인계 보고 순으로 진행한다.

## 빠른 시작 (예제 직접 실행)

```bash
cd skills/build
# 검증 → 시각화 → 모의 실행 → 실제 실행
python3 scripts/run_graph.py examples/leave-batch/pipeline.yml --validate
python3 scripts/run_graph.py examples/leave-batch/pipeline.yml --mermaid
python3 scripts/run_graph.py examples/leave-batch/pipeline.yml --mock
python3 scripts/run_graph.py examples/leave-batch/pipeline.yml
```

의존성 없음 — Python 3 표준 라이브러리 + claude CLI 만 있으면 된다.
(PyYAML 이 있으면 사용하고, 없으면 내장 미니 YAML 파서로 폴백)

## 워크플로우 정의 — 중첩 블록 DSL

워크플로우는 위에서 아래로 읽히는 중첩 구조로 쓴다 (START/END 자동 연결):

```yaml
workflow:
  - analyst
  - parallel: [implement, test]    # Fan-Out → 다음 스텝에서 Fan-In
  - qa:
      if: FAILED                   # 이 노드의 상태 체크 — 뒤로 goto = 피드백 루프
      goto: implement
      max: 2
      exhausted: [escalate, FAIL]  # 소진 → 에스컬레이션 보고 후 실패 종결
  - review
  - branch:                        # GRAPH_OUTPUT 값 기반 다중 케이스 분기
      on: route
      cases:
        heavy: process-heavy
        light: process-light
  - finalize                       # 합류점 — 자동 join: any
```

## 기능

| 기능 | 방법 |
|---|---|
| 순차/병렬 (Fan-Out/In) | `workflow` 나열 / `parallel: [a, b]` 블록 |
| 상태 체크 분기·루프 | 노드에 `{if: FAILED, goto: ...}` 부착 (뒤로 = 루프, 앞으로 = 분기) |
| 다중 케이스 분기 | `branch: {on: 출력키, cases: ...}` |
| 루프 블록 | `loop: {body, redo, max, exhausted}` |
| 저수준 제어 | `edges:` — from/to/when(표현식 `route == heavy`)/loop, `to: FAIL` 종결 |
| 상태 관리·재개 | `.graph-runs/<run-id>/state.json`, `--resume RUN_ID` (성공 노드 캐시 재사용) |
| 모의 실행 | `--mock`, `--mock-status NODE=FAILED,SUCCEEDED`, `--mock-output 'NODE={...}'` |
| 시각화·계획 | `--mermaid`, `--dry-run`, `--validate` |
| 전용 에이전트 재사용 | 노드 `agent: my-analyst` → `claude --agent` |
| 트리 UI 관찰 | 세션 모드 (`references/session-mode.md`) — Claude 가 Agent 툴로 직접 오케스트레이션 |

에이전트는 작업 후 마지막 줄에 `GRAPH_STATUS: SUCCEEDED|FAILED` 를 보고하고
(러너가 프로토콜을 프롬프트에 자동 주입), 분기용 값은
`GRAPH_OUTPUT: {"key": "value"}` 로 넘긴다.

## 실행 모델 — 배포 전 반드시 알아야 할 것

- **비용**: 노드 1회 실행 = claude 헤드리스 세션 1개. 최대 세션 수
  ≈ 노드 수 + (피드백 노드 수 × 루프 max). 얇은 변경은 파이프라인 대신
  직접 수행이 낫다 — CLAUDE.md 트리거에 단서 조항을 두라.
- **컨텍스트 격리**: 각 노드는 빈 컨텍스트에서 시작하는 독립 세션이다.
  노드 간 전달은 러너가 주입하는 "선행 노드 출력(기본 8,000자 절단) + 전체
  출력 파일 경로"뿐 (bounded handoff). 오케스트레이터는 스크립트라
  컨텍스트 오염이 없다.
- **관찰성**: 러너 모드는 콘솔 로그(▶/✔/↻/●) + `.graph-runs/` 산출물로,
  세션 모드는 Claude Code 트리 UI 로 관찰한다. 러너 모드의 노드 내부
  tool-use 는 실시간으로 보이지 않는다 (출력 전문은 파일로 저장).
- **권한**: 노드 세션의 permission-mode 는 `settings.claude_args` 로 정한다
  (템플릿 기본 `acceptEdits`). 코드가 아닌 읽기 전용 파이프라인이면 낮춰라.
- **사람 게이트 없음**: headless 노드는 질문할 수 없다. 스펙 확정은 실행
  전에, 커밋·머지는 실행 후에 사람이 한다.

## 구조

```
.claude-plugin/
  plugin.json               # 플러그인 매니페스트
  marketplace.json          # 셀프 호스팅 마켓플레이스 정의
skills/build/               # graph-builder:build — 빌더 메타 스킬
  SKILL.md                  # 하네스 스캐폴딩 절차
  scripts/run_graph.py      # 오케스트레이션 러너 (단일 파일, 산출물에 복사됨)
  references/yml-spec.md    # pipeline.yml 전체 스펙 (DSL + 저수준 edges)
  references/prompt-guide.md    # 프롬프트 작성 규칙 + 하네스 스킬 변환 매핑
  references/session-mode.md    # 세션 오케스트레이션(트리 UI) 해석 규칙
  templates/dev-team/       # 기본 파이프라인 템플릿 (병렬 + if/goto 루프)
  templates/pipeline-skill.md   # 생성될 파이프라인 스킬(SKILL.md) 템플릿
  examples/leave-batch/     # 배치 태스크 체인 예제
  examples/dev-harness-graph/   # 오케스트레이터 하네스 스킬의 그래프 변환 예제
```
