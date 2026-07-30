---
name: graph-builder
description: 멀티 에이전트 그래프 파이프라인(하네스) 빌더 메타 스킬. 사용자가 에이전트 팀/파이프라인/워크플로우/오케스트레이션을 만들고 싶다고 하거나, 개발 파이프라인(설계→구현→테스트→리뷰)·배치 태스크 체인을 yml 로 구성하고 싶을 때, 기존 하네스 스킬을 그래프로 변환할 때 사용. 산출물은 프로젝트 .claude/skills/ 에 독자 실행 하네스로 생성된다.
---

# graph-builder — 그래프 파이프라인 하네스 빌더

**빌더(이 스킬) → 산출물(프로젝트 하네스)** 구조다. 이 스킬은 파이프라인을
**만들 때만** 쓰이고, 만들어진 하네스는 대상 프로젝트의
`.claude/skills/<파이프라인명>/` 에서 **graph-builder 없이 독자적으로 실행**된다.

사용자는 pipeline.yml + prompts/*.md 만 관리하면 되고, 실행·상태 관리·분기·
병렬·루프는 러너(`scripts/run_graph.py`)의 몫이다 (스펙: `references/yml-spec.md`).

## 절차

### 1. 요구 파악

파이프라인의 성격(개발 협업형 / 배치 절차형)과 역할(노드)·흐름(순서·분기·루프)을
요구사항에서 도출한다. 성격은 템플릿 분기가 아니라 **프롬프트 작성 방식**에만
반영한다 (`references/prompt-guide.md` 의 kind 별 규칙). 애매하면 AskUserQuestion.

### 2. 그래프 설계 (사용자 확인)

흐름은 **중첩 workflow DSL** 로 쓴다 — 위에서 아래로 읽히고 START/END 자동 연결:

```yaml
workflow:
  - analyst
  - parallel: [implement, test]     # Fan-Out → 다음 스텝에서 Fan-In
  - qa:
      if: FAILED                    # 이 노드의 상태 체크. 이미 나온 노드로 goto = 피드백 루프
      goto: implement
      max: 2
      exhausted: [escalate, FAIL]   # 소진 → 보고 후 의도적 실패 종결
  - review:
      if: FAILED
      goto: implement
      max: 2
```

설계 원칙:

- 단순 상태 체크·재작업 루프는 `if/goto` (권장 — 가장 읽기 쉽다),
  값 기반 다중 케이스는 `branch: {on: 키, cases: ...}`,
  루프 범위·소진 경로가 복잡하면 `loop:` 블록
- 조건 분기의 합류점은 `join: any` 를 명시한다 (branch/앞으로 goto 대상은 자동)
- 특수 위상만 저수준 `edges:` 로 보충
- 대화형 확인·커밋 등 사람 게이트는 그래프에 넣지 않는다 (실행 전/후 수동)
- 기존 하네스 스킬 변환은 `references/prompt-guide.md` 매핑과
  `examples/dev-harness-graph/` 를 따른다

`--mermaid` 출력을 코드블록으로 사용자에게 보여주고 구조를 확인받는다.

### 3. 하네스 스캐폴딩 (대상: 프로젝트 `.claude/skills/<파이프라인명>/`)

```
<project>/.claude/skills/<파이프라인명>/
  SKILL.md                    # templates/pipeline-skill.md 기반 — 트리거·실행 절차
  pipeline.yml                # templates/dev-team/pipeline.yml 기반 설계 반영
  prompts/*.md                # templates/dev-team/prompts/ + prompt-guide.md 규칙
  scripts/run_graph.py        # 러너 그대로 복사 (수정 금지 — 독립 실행 보장)
  references/session-mode.md  # 세션 모드 해석 규칙 복사
```

프롬프트 규칙: 상태 보고 문법은 러너가 자동 주입하므로 **판정 기준과
GRAPH_OUTPUT 키 규약**만 쓴다. 실행 저장소에 전용 에이전트 정의(.claude/agents)가
있으면 노드 `agent:` 필드로 재사용하고 프롬프트에는 태스크 입력만 쓴다.

### 4. CLAUDE.md 등록 (필수)

프로젝트 ROOT 의 CLAUDE.md 에 트리거 블록을 추가한다 (없으면 생성).
이미 같은 마커 블록이 있으면 교체한다:

```markdown
<!-- graph-builder:<파이프라인명> start -->
## 그래프 파이프라인: <파이프라인명>
<트리거 조건 — 예: 개발·기능 수정 요구사항> 요청 시
`.claude/skills/<파이프라인명>` 스킬(그래프 파이프라인 하네스)을 사용해 수행하라.
단일 파일 수준의 얇은 변경은 직접 수행한다.
<!-- graph-builder:<파이프라인명> end -->
```

### 5. 검증 (필수 — 건너뛰지 마라)

```bash
python3 .claude/skills/<이름>/scripts/run_graph.py .claude/skills/<이름>/pipeline.yml --validate
python3 .claude/skills/<이름>/scripts/run_graph.py .claude/skills/<이름>/pipeline.yml --dry-run
# 분기·루프 경로 검증 (claude 호출 없음):
python3 ... --mock --mock-status review=FAILED,SUCCEEDED
python3 ... --mock --mock-output 'prepare={"route": "light"}'
```

### 6. 인계 보고

사용자에게 보고한다:

- 생성된 하네스 위치·구조와 CLAUDE.md 등록 내용
- **비용 특성 (필수 고지)**: 노드 1회 실행 = claude 세션 1개. 노드 수 × 루프
  상한 기준 최대 세션 수를 알린다
- **실행 모드 2가지**: 러너 모드(기본 — 결정적·상태저장·resume, 콘솔 로그) /
  세션 모드(트리 UI 관찰 — 하네스의 references/session-mode.md)
- **컨텍스트 격리**: 각 노드는 독립 세션(빈 컨텍스트 시작), 노드 간 전달은
  선행 출력 요약 + 파일 경로뿐 (bounded handoff)
- permission-mode 정책(`settings.claude_args`, 기본 acceptEdits) 확인

## 참조

- `references/yml-spec.md` — pipeline.yml 전체 스키마·DSL·CLI
- `references/prompt-guide.md` — 성격별 프롬프트 작성 규칙, 하네스 변환 매핑
- `references/session-mode.md` — 세션 오케스트레이션(트리 UI) 해석 규칙
- `templates/dev-team/` — 기본 파이프라인 템플릿 (병렬 + if/goto 루프)
- `templates/pipeline-skill.md` — 생성될 파이프라인 스킬(SKILL.md) 템플릿
- `examples/leave-batch/` — 배치 태스크 체인 예제
- `examples/dev-harness-graph/` — 오케스트레이터 하네스 스킬의 그래프 변환 예제
