# graph-builder

**개발 오케스트레이션 구성 메타 플러그인** (Claude Code). 도메인 설명 한
문장에서, 프로젝트에서 **독자적으로 동작하는 멀티 에이전트 개발 파이프라인**
— 그래프(루프(하네스)) — 을 구성해 준다. 사용자는 이후 **yml 만으로** 흐름을
추가·변경한다.

```
graph-builder 플러그인
  ├─ graph-builder:build   # 오케스트레이션 구성 (Phase 1~6)
  └─ graph-builder:edit    # 설치된 파이프라인의 yml·에이전트 변경·진단
        │
        ▼  "개발 오케스트레이션 구성해줘"
<project>/
  CLAUDE.md                            # 개발 요청 시 오케스트레이션 사용 명시
  .claude/
    skills/<도메인>-pipeline-dev/      # 메인 오케스트레이션 스킬 (독자 실행)
      SKILL.md · pipeline.yml · prompts/ · scripts/run_graph.py
    agents/<prefix>-analyst.md ···     # 에이전트 구성 (역할·모델·도구)
```

역할 분담: **흐름 = pipeline.yml, 역할 = .claude/agents, 태스크 입력 = prompts,
실행·상태·분기 = run_graph.py** (노드 = `claude -p` 헤드리스 세션).

## 설치

```
/plugin marketplace add <이 저장소 git URL 또는 로컬 경로>
/plugin install graph-builder@graph-builder-marketplace
```

설치 후: "개발 오케스트레이션 구성해줘" → `build` 스킬이 프로젝트 분석 →
팀 설계 확인(mermaid) → 에이전트·파이프라인 스킬 생성 → CLAUDE.md 등록 →
mock 검증 → 인계. 이후 "파이프라인에 보안 검사 추가해줘" → `edit` 스킬.

## 기본 개발 오케스트레이션 (templates/pipeline-dev)

```yaml
workflow:
  - analyst                          # 분석·SDD 스펙 초안(acceptance A1..)·확정 질문 도출
  - spec-gate                        # ⏸ 일시정지 → AskUserQuestion 스펙 확정 → resume
  - parallel: [implement, test]      # 구현 ‖ 테스트 작성 (Fan-Out)
  - qa:                              # Fan-In — 합쳐서 빌드·실행 검증
      if: FAILED                     # acceptance FAIL → 구현 재작업 수렴 루프
      goto: implement
      max: 2
      exhausted: escalate            # 반복 실패 → 보고 노드 실행 후 자동 실패 종결
  - review:                          # 정적 리뷰 (APPROVE → END, 커밋은 사람 게이트)
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate
```

각 노드는 `.claude/agents/<prefix>-*.md` 정의(역할·모델·도구)로 실행된다.
다른 팀 구조는 `references/team-patterns.md` 의 패턴(Pipeline, Fan-Out/In,
Producer-Reviewer, Expert Pool, Gate)에서 출발한다.

## yml 로 표현하는 것

| 기능 | 방법 |
|---|---|
| 순차/병렬 (Fan-Out/In) | `workflow` 나열 / `parallel: [a, b]` 블록 |
| 상태 체크 분기·루프 | 노드에 `{if: FAILED, goto: ...}` 부착 (뒤로 = 루프, 앞으로 = 분기) |
| 다중 케이스 분기 | `branch: {on: 출력키, cases: ...}` |
| 루프 블록 | `loop: {body, redo, max, exhausted}` |
| 사람 확인 게이트 (SDD) | 노드 `gate: true` — 일시정지(exit 3) → 확인 후 `--resume` + `--var` 주입 |
| 저수준 제어 | `edges:` — from/to/when(표현식 `route == heavy`)/loop, `to: FAIL` 종결 |
| 상태 관리·재개 | `.graph-runs/<run-id>/state.json`, `--resume RUN_ID` (성공 노드 캐시 재사용) |
| 모의 실행 | `--mock`, `--mock-status NODE=FAILED,SUCCEEDED`, `--mock-output 'NODE={...}'` |
| 시각화·계획 | `--mermaid`, `--dry-run`, `--validate` |
| 트리 UI 관찰 | 세션 모드 (`references/session-mode.md`) — Claude 가 Agent 툴로 직접 오케스트레이션 |

에이전트는 작업 후 마지막 줄에 `GRAPH_STATUS: SUCCEEDED|FAILED` 를 보고하고
(러너가 프로토콜을 자동 주입), 분기용 값은 `GRAPH_OUTPUT: {"key": "value"}` 로
넘긴다. 러너는 Python 3 표준 라이브러리 단독으로 동작한다 (PyYAML 있으면
사용, 없으면 내장 파서 폴백).

## 실행 모델 — 배포 전 반드시 알아야 할 것

- **비용**: 노드 1회 실행 = claude 헤드리스 세션 1개. 최대 세션 수
  ≈ 노드 수 + (피드백 노드 수 × 루프 max). 얇은 변경은 파이프라인 대신
  직접 수행 — CLAUDE.md 트리거에 단서 조항 기본 포함.
- **컨텍스트 격리**: 각 노드는 빈 컨텍스트에서 시작하는 독립 세션.
  노드 간 전달은 "선행 노드 출력(기본 8,000자 절단) + 전체 출력 파일 경로"뿐
  (bounded handoff). 오케스트레이터는 스크립트라 컨텍스트 오염이 없다.
- **관찰성**: 러너 모드 = 콘솔 로그(▶/✔/↻/●) + `.graph-runs/` 산출물.
  세션 모드 = Claude Code 트리 UI. 러너 모드의 노드 내부 tool-use 는
  실시간으로 보이지 않는다 (출력 전문은 파일 저장).
- **권한**: 노드 세션 permission-mode 는 `settings.claude_args` 로 정한다
  (기본 `acceptEdits`).
- **사람 확인은 게이트로**: headless 노드는 질문할 수 없다 — 사람 확인이
  필요한 지점(스펙 확정 등)에는 `gate: true` 노드를 둔다(일시정지 후
  AskUserQuestion → resume). 커밋·머지는 실행 후에 사람이 한다.

## 플러그인 구조

```
.claude-plugin/
  plugin.json / marketplace.json    # 매니페스트 · 셀프 호스팅 마켓플레이스
skills/
  build/                            # graph-builder:build — 오케스트레이션 구성
    SKILL.md                        # Phase 1~6 구성 절차
    scripts/run_graph.py            # 실행 엔진 (산출물에 복사됨)
    templates/pipeline-dev/         # 산출물 오케스트레이션 스킬 골격 (SKILL.md+yml+prompts)
    templates/agents/               # 에이전트 정의 골격 (analyst/implementer/test/qa/reviewer)
    references/team-patterns.md     # 팀 아키텍처 패턴 ↔ 그래프 DSL
    references/agent-guide.md       # 에이전트 작성·치환 규칙
    references/yml-spec.md          # pipeline.yml 전체 스펙
    references/prompt-guide.md      # 프롬프트 규칙 + 기존 하네스 변환 매핑
    references/session-mode.md      # 트리 UI(세션) 모드 해석 규칙
  edit/                             # graph-builder:edit — 구성 변경·진단
    SKILL.md
```
