---
name: build
description: 개발 오케스트레이션 구성 메타 스킬. 사용자가 "개발 오케스트레이션/에이전트 팀/파이프라인/워크플로우 구성해줘", "하네스 만들어줘" 라고 하거나 개발 파이프라인(분석→구현→테스트→QA→리뷰)·배치 태스크 체인을 프로젝트에 구축하고 싶을 때 사용. 산출물: 프로젝트의 CLAUDE.md 트리거 + .claude/skills/<파이프라인> 오케스트레이션 스킬(yml+러너) + .claude/agents 에이전트 정의. 이미 설치된 파이프라인의 변경은 graph-builder:edit.
---

# graph-builder:build — 개발 오케스트레이션 구성

도메인 설명 한 문장에서 **프로젝트에서 독자적으로 동작하는 개발 오케스트레이션**을
만든다. 이 스킬은 구성할 때만 쓰이고, 산출물은 플러그인 없이 실행된다.

## 산출물 구조 (최종 output — 이 구조를 반드시 완성한다)

```
<project>/
  CLAUDE.md                              # ① 개발 요청 시 오케스트레이션 사용 명시
  .claude/
    skills/<파이프라인명>/                # ② 메인 오케스트레이션 스킬 (기본명: pipeline-skill)
      SKILL.md                           #    실행 절차 (러너/세션 모드)
      pipeline.yml                       #    흐름 SSOT — 사용자가 yml 로 추가·변경
      prompts/*.md                       #    노드별 태스크 입력·판정 기준
      scripts/run_graph.py               #    세션을 수행하는 실행 엔진 (복사본)
      references/session-mode.md         #    트리 UI 모드 해석 규칙 (복사본)
    agents/<prefix>-*.md                 # ③ 에이전트 구성 (역할·모델·도구)
```

역할 분담: **흐름 = yml, 역할 = agents, 태스크 입력 = prompts** — 상세 기준은
`references/agent-guide.md`. 같은 내용을 두 곳에 쓰지 않는다.

## Phase 0: 현황 감사 (실행 모드 판별)

무엇이든 만들기 전에 기존 산출물을 감사하고 실행 모드를 정한다:

- 확인: `.claude/skills/*/pipeline.yml`(설치된 파이프라인), `.claude/agents/`,
  CLAUDE.md 의 `graph-builder:*` 마커 블록
- **정합성(drift) 점검** — 발견한 산출물끼리 어긋나면(yml 의 `agent:` 가
  없는 에이전트를 가리킴, 마커는 있는데 스킬 디렉토리가 없음 등) 먼저 보고한다

| 상태 | 모드 |
|---|---|
| 산출물 없음 | **신규 구축** — Phase 1 부터 진행 |
| 파이프라인 있음 + 새 파이프라인/노드·에이전트 추가 요구 | **확장** — 기존 이름·에이전트와 충돌하지 않게 Phase 1 부터 진행 (중복 생성 금지) |
| 파이프라인 있음 + 변경·수정·진단 요구 | **유지보수 — 이 스킬을 쓰지 말고 `graph-builder:edit` 로 라우팅한다** |

## Phase 1: 프로젝트 분석

스캐폴딩 전에 프로젝트 사실을 수집한다 (에이전트 플레이스홀더의 입력):

- 기술 스택, 빌드·테스트 실제 명령 (README/빌드 파일에서 확인, 추측 금지)
- 레이어 구조·의존 방향·컨벤션 (CLAUDE.md, 컨벤션 문서, 코드 샘플)
- **컨벤션 문서의 로드 범위 판별** — CLAUDE.md(@참조)·`.claude/rules/`·도메인
  스킬 안에 있으면 노드 세션에 자동 로드되므로 추가 조치 불필요. **자동 로드
  밖**의 문서(docs/ 등)에 있으면 Phase 3 에서 역할별 lazy-read 포인터로
  매핑한다 (`references/agent-guide.md` 의 컨벤션 참조 규칙)
- **기존 `.claude/agents/` 확인** — 역할이 겹치는 정의가 있으면 재사용 대상

## Phase 2: 팀 설계 (사용자 확인 게이트)

`references/team-patterns.md` 의 패턴에서 출발해 노드·에이전트·흐름을 설계한다.
**표준 기능 개발 요청이면 기본 템플릿을 그대로 쓰는 것이 기본값이다** —
분석 → **SDD 스펙 게이트(⏸ AskUserQuestion 확정)** → 구현‖테스트 → QA →
리뷰 + 수렴 루프. 요구가 다를 때만 변형하며, 사람 확인이 필요한 지점에는
`gate: true` 노드를 쓴다.

노드는 **3~8개를 권장**한다 — 그보다 크면 파이프라인을 나누거나(단계별 별도
파이프라인) 노드를 병합한다. 노드가 많을수록 세션 비용과 루프 폭이 커진다.

사용자에게 확인받을 것: ① 노드/에이전트 표(역할·모델) ② 흐름 mermaid
(pipeline.yml 초안으로 `--mermaid` 생성) ③ 파이프라인명(기본 `pipeline-skill`)과
에이전트 접두어(기본: 프로젝트 슬러그).

## Phase 3: 에이전트 정의 생성 (`.claude/agents/`)

`templates/agents/*.md` 를 복사해 `<prefix>-<역할>.md` 로 만들고, Phase 1 의
사실로 **모든 플레이스홀더를 치환**한다 (규칙: `references/agent-guide.md`).
기존 에이전트가 있으면 생성 대신 재사용하고 yml 의 `agent:` 만 맞춘다.

## Phase 4: 오케스트레이션 스킬 생성 (`.claude/skills/<파이프라인명>/`)

`templates/pipeline-skill/` 전체를 복사한 뒤:

1. `SKILL.md`·`pipeline.yml`·`prompts/*.md` 의 플레이스홀더
   (`{{pipeline_name}}`, `{{prefix}}`, `{{project_name}}`)를 치환한다.
   산출물 SKILL.md 의 description 은 **구체적 트리거 상황 + 후속 작업
   키워드(재실행·수정·보완·피드백 반영)** 를 포함해야 한다 — 템플릿 기본값을
   프로젝트 용어로 다듬는다
2. Phase 2 설계가 기본 템플릿과 다르면 workflow·nodes·prompts 를 조정한다
   (DSL 스펙: `references/yml-spec.md`, 프롬프트 규칙: `references/prompt-guide.md`)
3. 이 스킬의 `scripts/run_graph.py` 와 `references/session-mode.md` 를
   그대로 복사한다 (러너 수정 금지 — 독립 실행 보장)

## Phase 5: CLAUDE.md 등록 (필수)

프로젝트 ROOT 의 CLAUDE.md 에 트리거 블록을 추가한다 (없으면 생성,
같은 마커가 있으면 교체):

```markdown
<!-- graph-builder:<파이프라인명> start -->
## 개발 오케스트레이션: <파이프라인명>
개발·기능 수정·테스트 보강·리뷰 요구사항 요청 시
`.claude/skills/<파이프라인명>` 스킬(개발 오케스트레이션)을 사용해 수행하라.
단일 파일 수준의 얇은 변경은 직접 수행한다.
<!-- graph-builder:<파이프라인명> end -->
```

## Phase 6: 검증·인계 (필수 — 건너뛰지 마라)

```bash
PL=.claude/skills/<파이프라인명>
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --validate
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock          # 스펙 게이트 PAUSED(exit 3) 확인
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock \
  --resume <RUN_ID> --mock-status qa=FAILED,SUCCEEDED             # 게이트 통과 + 수렴 루프 확인
# 스캐폴딩 플레이스홀더 잔존 = 미완성 ({{vars.*}} 등 런타임 변수는 정상이므로 제외)
grep -rn "{{" $PL .claude/agents/<prefix>-*.md | grep -v "{{vars\.\|{{run\.\|{{node\."
```

**트리거 검증** — 산출물 SKILL.md 의 description 을 놓고 사고 점검한다:

- should-trigger 5개: 이 프로젝트에서 실제로 나올 개발 요청 문장
  (예: "X 기능 추가해줘", "리뷰 피드백 반영해서 다시")이 트리거되는가
- should-NOT-trigger 5개: **near-miss** 중심 — "이 함수 뭐하는 거야"(질문),
  "오타 하나 고쳐줘"(얇은 변경), "빌드 왜 깨져"(진단) 등이 트리거되지 않는가
- 어긋나면 description 을 수정한다 (트리거 조건과 제외 조건을 명시)

인계 보고에 포함: 생성 파일 트리, CLAUDE.md 등록 내용, **비용 특성**(노드
1회 = claude 세션 1개, 최대 세션 수 추정), 실행 모드 2가지(러너=결정적·resume /
세션=트리 UI 관찰), 컨텍스트 격리 특성, permission-mode 확인, 이후 구성 변경은
`graph-builder:edit` 사용 안내.

## 참조

- `references/team-patterns.md` — 팀 아키텍처 패턴 ↔ 그래프 DSL 대응
- `references/agent-guide.md` — 에이전트 정의 작성·치환 규칙
- `references/yml-spec.md` — pipeline.yml 전체 스키마·DSL·CLI
- `references/prompt-guide.md` — 프롬프트 작성 규칙, 기존 하네스 변환 매핑
- `references/session-mode.md` — 세션 오케스트레이션(트리 UI) 해석 규칙
- `templates/pipeline-skill/` — 산출물 스킬 골격 / `templates/agents/` — 에이전트 골격
