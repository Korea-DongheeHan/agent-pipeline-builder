---
name: graph-builder
description: 멀티 에이전트 그래프 파이프라인(팀) 구성 메타 스킬. 사용자가 에이전트 팀/파이프라인/워크플로우/오케스트레이션을 만들고 싶다고 하거나, 개발 파이프라인(설계→구현→테스트→리뷰)·배치 태스크 체인을 yml 로 구성·실행하고 싶을 때, 기존 하네스 스킬을 그래프로 변환할 때 사용. Fan-Out/In·조건 분기·피드백 루프를 yml + 프롬프트 파일로 정의하고 run_graph.py 가 실행한다.
---

# graph-builder — 그래프 파이프라인 구성 메타 스킬

사용자가 **pipeline.yml + prompts/*.md 만 작성하면** 멀티 에이전트 파이프라인이
돌아가게 스캐폴딩한다. 실행·상태 관리·분기·병렬·루프는 전부
`scripts/run_graph.py` 의 몫이다 (스펙: `references/yml-spec.md`).

역할 분담: **사용자 = yml + 프롬프트, 러너 = 실행/상태/분기, 이 스킬 = 스캐폴딩.**

## 절차

### 1. 팀 성격 판별 (kind)

생성할 프롬프트의 성격이 갈린다. 요청에서 판별하고, 애매하면 AskUserQuestion 으로 확정한다:

| kind | 신호 | 기본 그래프 형태 |
|---|---|---|
| `development` | 기능 개발·구현·리뷰·테스트 등 **역할 협업** | 설계 → Fan-Out 구현 → Fan-In 검증 → 리뷰 + FAILED 피드백 루프 |
| `workflow` | 배치·태스크 체인·순차 잡 등 **절차 실행** | 태스크 체인 + STATUS/OUTPUT 조건 분기 |

### 2. 그래프 설계

요구사항에서 노드(역할/태스크)와 흐름(순서·분기·루프)을 도출해 사용자에게
표로 확인받는다. 흐름은 **중첩 workflow DSL** 로 쓴다 (위에서 아래로 읽히고
START/END 자동 연결 — 스펙: `references/yml-spec.md`):

```yaml
workflow:
  - analyst
  - loop:                              # 피드백 루프: 판정 실패 → 재작업
      max: 2
      exhausted: [escalate, FAIL]
      redo: implement
      body:
        - parallel: [implement, test]  # Fan-Out → 다음 스텝에서 Fan-In
        - qa
        - review
```

설계 원칙:

- 병렬 가능한 작업은 `parallel` 블록으로, 판정 노드(테스트·QA·리뷰)의 재작업은
  `loop` 블록으로 표현한다 — `max` 로 무한 루프를 막고 `exhausted` 로 소진 시
  경로(에스컬레이션 보고 등)를 정한다
- 값 기반 분기는 GRAPH_OUTPUT 키를 정하고 `branch: {on: 키, cases: ...}` 로
  라우팅한다 (케이스 전수 정의 — 미매칭은 데드락 실패)
- 특수 위상만 저수준 `edges:` 로 보충한다
- 대화형 확인·커밋 등 사람 게이트는 그래프에 넣지 않는다 (실행 전/후 수동)
- 기존 하네스 스킬을 변환할 때는 `references/prompt-guide.md` 의 변환 매핑과
  `examples/dev-harness-graph/` 를 따른다

### 3. 스캐폴딩

대상 디렉토리에 생성한다:

1. `scripts/run_graph.py` — 이 스킬의 것을 그대로 복사 (수정 금지)
2. `pipeline.yml` — `templates/<kind>/pipeline.yml` 을 기반으로 설계에 맞게 수정
3. `prompts/*.md` — `templates/<kind>/prompts/` 를 기반으로 노드별 생성.
   작성 규칙은 `references/prompt-guide.md` 를 따른다. 핵심:
   - 상태 보고 문법은 러너가 자동 주입 — 프롬프트에는 **판정 기준**과
     **GRAPH_OUTPUT 키 규약**만 쓴다
   - 프롬프트 경로는 스크립트 실행 위치(cwd) 기준 상대경로
   - 실행 저장소에 전용 에이전트 정의(.claude/agents)가 있으면 노드 `agent:`
     필드로 재사용하고 프롬프트에는 태스크 입력만 쓴다

### 4. 검증 (필수 — 건너뛰지 마라)

```bash
python3 scripts/run_graph.py pipeline.yml --validate   # 스키마·도달성·사이클
python3 scripts/run_graph.py pipeline.yml --mermaid    # 그래프를 사용자에게 시각화로 제시
python3 scripts/run_graph.py pipeline.yml --dry-run    # 병렬 wave 실행 계획
```

mermaid 출력을 코드블록으로 사용자에게 보여주고 그래프 구조를 확인받는다.

### 5. 모의 실행 (claude 호출 없이 그래프 로직 검증)

```bash
python3 scripts/run_graph.py pipeline.yml --mock
# 분기·루프가 있으면 해당 경로도 검증:
python3 scripts/run_graph.py pipeline.yml --mock --mock-status review=FAILED,SUCCEEDED
python3 scripts/run_graph.py pipeline.yml --mock --mock-output 'prepare={"route": "light"}'
```

피드백 루프·조건 분기·루프 소진 경로가 의도대로 도는지 로그로 확인한다.

### 6. 실행 안내

사용자에게 안내한다:

```bash
python3 scripts/run_graph.py pipeline.yml --var requirement="..."
# 실패 시: 성공 노드는 캐시 재사용, 실패 지점부터 재개
python3 scripts/run_graph.py pipeline.yml --resume <RUN_ID>
```

- 산출물: `.graph-runs/<run-id>/` (state.json, 노드별 프롬프트/출력 전문)
- 실제 실행은 노드당 claude 세션 1개씩 뜬다 — 비용·소요시간을 미리 알린다
- 코드를 쓰는 파이프라인이면 `settings.claude_args` 의 permission-mode 를
  사용자와 확인한다 (기본 템플릿: `acceptEdits`)

## 참조

- `references/yml-spec.md` — pipeline.yml 전체 스키마·시맨틱·CLI
- `references/prompt-guide.md` — kind 별 프롬프트 작성 규칙, 하네스 스킬 변환 매핑
- `templates/dev-team/` — development 템플릿 (Fan-Out/In + 피드백 루프)
- `templates/workflow/` — workflow 템플릿 (OUTPUT 조건 분기 + join: any)
- `examples/leave-batch/` — 배치 태스크 체인 예제 (tasks/dependencies 형식 변환본)
- `examples/dev-harness-graph/` — 오케스트레이터 하네스 스킬의 그래프 변환 예제
