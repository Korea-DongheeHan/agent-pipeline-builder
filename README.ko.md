# graph-builder

**한 문장의 설명에서 프로젝트 전용 멀티 에이전트 개발 오케스트레이션을 만들어 냅니다.**

[English](README.md) · 한국어

![graph-builder: pipeline.yml 이 결정적 멀티 에이전트 그래프로 컴파일되는 모습](docs/hero.svg)

graph-builder 는 YAML 로 정의되는 독자 실행 에이전트 파이프라인을 저장소에
스캐폴딩해 주는 Claude Code 플러그인입니다. 도메인을 한 번 설명하면 플러그인이
오케스트레이션 스킬과 전용 에이전트 팀, 트리거 배선까지 생성합니다. 이후의
기능 요청은 결정적 그래프를 따라 흐릅니다. 분석하고, 스펙을 확정하고, 구현과
테스트를 병렬로 진행하고, 검증과 리뷰를 거치며, acceptance 를 통과할 때까지
수렴 루프를 돕니다.

```
graph-builder 플러그인
  ├─ graph-builder:build   # 오케스트레이션 구성 (6단계)
  └─ graph-builder:edit    # 설치된 파이프라인의 변경과 진단
        │
        ▼  "이 프로젝트에 개발 오케스트레이션 구성해 줘"
<프로젝트>/
  CLAUDE.md                              # 트리거 규칙 (자동 등록)
  .claude/
    skills/<도메인>-pipeline-dev/        # 오케스트레이션 스킬 (독자 실행)
      SKILL.md · pipeline.yml · prompts/ · scripts/run_graph.py
    agents/<접두어>-analyst.md ···       # 에이전트 팀 (역할, 모델, 도구)
```

산출물은 스스로 동작합니다. 스캐폴딩이 끝나면 이 플러그인 없이 Python 3 와
`claude` CLI 만으로 실행됩니다.

## 왜 graph-builder 인가

- **결정적 오케스트레이션.** 그래프를 스케줄링하는 주체가 LLM 이 아니라
  스크립트입니다. 같은 입력이면 같은 흐름이 나오고, 분기와 팬아웃, 피드백
  루프와 반복 상한이 기계적으로 강제됩니다.
- **파이프라인의 소유권은 YAML 에 있습니다.** 전체 흐름이 `pipeline.yml`
  하나에 담깁니다. 단계 순서를 바꾸거나 루프를 조이거나 보안 리뷰 노드를
  추가할 때 코드를 만질 필요가 없습니다.
- **스펙 주도가 기본값입니다.** 기본 파이프라인은 분석 뒤 스펙 게이트에서
  일시정지합니다. 구현이 한 줄이라도 시작되기 전에 범위와 acceptance 기준을
  직접 확정합니다.
- **컨텍스트 격리.** 모든 노드는 빈 컨텍스트의 독립 claude 세션으로
  시작합니다. 노드 사이에는 요약과 파일 경로만 오가므로 컨텍스트 오염이
  누적되지 않습니다.
- **다시 하지 말고 이어서 하세요.** 실행이 실패하면 원인을 고치고
  `--resume` 하면 됩니다. 성공한 노드는 캐시로 재사용되고 실패한 경로만
  다시 실행됩니다.
- **비용이 투명합니다.** 노드 1회 실행이 곧 claude 세션 1개입니다. 스킬이
  실행 전에 예상 세션 수를 먼저 알려 줍니다.

## 설치

```
/plugin marketplace add Korea-DongheeHan/graph-builder
/plugin install graph-builder@graph-builder-marketplace
```

## 이렇게 말하면 됩니다

원하는 일에 따라 이런 표현이 트리거됩니다.

- **새 오케스트레이션 구축** (`graph-builder:build`). "개발 오케스트레이션
  구성해 줘", "이 프로젝트에 파이프라인 구축해 줘", "하네스 만들어 줘",
  "우리 오케스트레이터 스킬을 그래프로 변환해 줘".
- **설치된 파이프라인 변경과 진단** (`graph-builder:edit`). "파이프라인에 보안
  검사 단계 추가해 줘", "수렴 루프 상한을 3으로 바꿔 줘", "qa 를 command
  노드로 바꿔 줘", "어제 파이프라인 실행이 왜 실패했는지 봐 줘".
- **스캐폴딩된 파이프라인 실행** (이 플러그인이 아니라 프로젝트의 CLAUDE.md 가
  트리거). "부분 환불 지원 추가해 줘" 같은 일반 개발 요구사항, 그리고 "아까
  실행 이어서 돌려 줘", "리뷰 피드백 반영해서 다시", "진행 보면서 세션 모드로
  돌려 줘" 같은 후속 요청.

단순 코드 질문, 오타 한 줄 수정, 빌드 진단은 의도적으로 아무것도 트리거하지
않습니다.

## 오케스트레이션 구성하기

아무 프로젝트에서 "개발 오케스트레이션 구성해 줘"라고 말하면 `build` 스킬이
여섯 단계를 진행하며, 중요한 지점마다 사용자 확인을 받습니다.

1. **감사.** 기존 파이프라인과 에이전트, CLAUDE.md 마커를 감지합니다. 변경
   요청이면 새로 만들지 않고 `graph-builder:edit` 로 라우팅합니다.
2. **분석.** 기술 스택과 실제 빌드·테스트 명령, 컨벤션 문서를 읽습니다.
   추측하지 않습니다.
3. **설계 확인.** 노드와 에이전트 표, 흐름 mermaid 다이어그램을 제시하고
   파이프라인 이름(기본 `<도메인>-pipeline-dev`), 에이전트 접두어, 기본 실행
   모드, 산출물 언어를 확정받습니다.
4. **에이전트 생성.** 실제 명령과 컨벤션 출처 포인터를 담아
   `.claude/agents/<접두어>-*.md` 를 작성합니다. 기존 에이전트는 재사용하며
   중복 생성하지 않습니다.
5. **파이프라인 스킬 생성과 트리거 등록.** 스킬 디렉토리를 스캐폴딩하고
   CLAUDE.md 에 마커 블록을 추가합니다.
6. **검증.** 그래프를 검증하고, 게이트와 수렴 루프를 mock 으로 돌려 보고,
   플레이스홀더 잔존 여부를 확인합니다.

## 생성되는 것

프로젝트 이름이 `order-service`, 접두어가 `order` 라면 다음이 생성됩니다.

```
order-service/
  CLAUDE.md                            # 트리거 블록 추가 (마커로 구분, 교체 가능)
  .claude/
    skills/order-pipeline-dev/
      SKILL.md                         # 실행 방법: 모드, 스펙 게이트, resume, 진화
      pipeline.yml                     # 흐름 정의. 오케스트레이션 변경은 이 파일에서
      prompts/                         # 노드별 태스크 입력과 판정 기준
        analyst.md · implement.md · test.md · qa.md · review.md · escalate.md
      scripts/run_graph.py             # 실행 엔진 (표준 라이브러리 단독 Python)
      references/session-mode.md       # 관찰형 세션 모드의 해석 규칙
    agents/
      order-analyst.md                 # 역할, 작업 방식, 프로젝트 사실
      order-implementer.md
      order-test-engineer.md
      order-qa.md
      order-reviewer.md
```

생성된 에이전트에는 첫날부터 쓸모 있게 만드는 사실들이 담깁니다.

```markdown
---
name: order-implementer
description: order-service 구현 전문가. implement 노드 담당.
---
## 프로젝트 컨텍스트
- 스택: Kotlin + Spring Boot 멀티모듈 Gradle
- 빌드: ./gradlew classes testClasses --parallel
- 컨벤션: AGENTS.md 가 단일 출처이고 도메인 규칙은 .claude/skills/<도메인>/ 에 있다
```

## 예제: 기능 요청 하나의 처음부터 끝까지

```bash
$ PL=.claude/skills/order-pipeline-dev
$ python3 $PL/scripts/run_graph.py $PL/pipeline.yml \
    --var requirement="주문 API 에 부분 환불 지원 추가"

[10:02:11] ▶ analyst 시작 (iter 1)
[10:03:24] ✔ analyst SUCCEEDED (iter 1)
[10:03:24] ⏸ 게이트 spec-gate 도달 — 일시정지        # 종료 코드 3
```

analyst 가 스펙 초안과 확정할 질문을 만들어 두었습니다. Claude 가 이를 읽고
AskUserQuestion 한 라운드로 스펙을 확정한 뒤, 결정 사항을 주입해 재개합니다.

```bash
$ python3 $PL/scripts/run_graph.py $PL/pipeline.yml --resume 20260731-100211-ab12 \
    --var requirement="..." \
    --var decisions="범위: 정산 이후 환불 제외. API: 기존 엔드포인트 확장"

[10:07:02] ⏩ analyst 캐시 재사용 (이전 실행 SUCCEEDED)
[10:07:02] ⏩ 게이트 spec-gate 통과 (이전 실행에서 확인됨)
[10:07:02] ▶ implement 시작 (iter 1)     # test 와 병렬로 실행
[10:07:02] ▶ test 시작 (iter 1)
[10:14:40] ▶ qa 시작 (iter 1)
[10:18:03] ✘ qa FAILED (iter 1)          # acceptance A3 실패
[10:18:03] ↻ 피드백 qa → implement (1/2)
[10:21:47] ✔ qa SUCCEEDED (iter 2)
[10:24:12] ✔ review SUCCEEDED (iter 1)
[10:24:12] ● END 도달
[10:24:12] ✔ 파이프라인 SUCCEEDED — 산출물: .graph-runs/20260731-100211-ab12
```

모든 노드의 프롬프트와 출력 전문이 `.graph-runs/<run-id>/` 아래에 감사
추적용으로 보존됩니다. 커밋은 사람의 몫으로 남습니다.

## 기본 파이프라인

```yaml
workflow:
  - analyst                          # 분석, SDD 스펙 초안, 확정 질문 도출
  - spec-gate                        # ⏸ 일시정지 후 AskUserQuestion 으로 스펙 확정
  - parallel: [implement, test]      # 구현과 테스트 작성을 병렬로 (팬아웃)
  - qa:                              # 팬인. 빌드와 실행으로 acceptance 판정
      if: FAILED                     # 수렴 루프. 실패한 것만 재작업
      goto: implement
      max: 2
      exhausted: escalate            # 반복 실패는 보고 후 실행을 실패로 종결
  - review:                          # 정적 리뷰. 승인이면 종료, 커밋은 사람이
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate
```

각 노드는 `.claude/agents/` 의 프로젝트 전용 에이전트 정의로 실행되며, 실제
빌드 명령과 테스트 명령, 컨벤션 포인터를 갖고 움직입니다.

## 그래프 엔지니어링 쿡북

기본 파이프라인은 범용 그래프 언어의 한 사례일 뿐입니다. 아래 패턴을 자유롭게
중첩해 조합하세요.

**순차 체인.** 배치 잡과 마이그레이션에 씁니다.

```yaml
workflow:
  - extract
  - transform
  - load
```

**분류 후 실행 (조건 라우팅).** 분류 노드가 `GRAPH_OUTPUT` 으로 라우팅 키를
보고하고, 유형별로 다른 흐름을 탑니다.

```yaml
workflow:
  - triage                    # GRAPH_OUTPUT: {"kind": "bug" | "feature" | "docs"}
  - branch:
      on: kind
      cases:
        bug: [reproduce, fix]
        feature: [design, implement]
        docs: update-docs
  - verify                    # 합류점. 먼저 도착한 쪽으로 진행
```

**품질 게이트 체인.** 실패를 즉시 명시적으로 종결합니다.

```yaml
nodes:
  - {id: build-check, type: command, run: "./gradlew classes testClasses --parallel"}
  - {id: security-scan, type: command, run: "./gradlew dependencyCheckAnalyze"}
  - {id: deploy-ready, prompt: prompts/deploy-ready.md}
  - {id: report-failure, prompt: prompts/report-failure.md}
workflow:
  - build-check:
      if: FAILED
      goto: [report-failure, FAIL]   # 보고 노드 실행 후 실패 종결
  - security-scan:
      if: FAILED
      goto: [report-failure, FAIL]
  - deploy-ready
```

**사람 확인 게이트.** 사람이 결정해야 하는 지점 어디든 일시정지를 둡니다.

```yaml
nodes:
  - id: approve-plan
    gate: true
workflow:
  - plan
  - approve-plan              # 일시정지. resume 시 확정 값을 주입
  - execute
```

**펼치고 종합.** 작업을 컨텍스트가 격리된 갈래로 나누고 배리어에서 병합합니다.

```yaml
workflow:
  - plan-slices                                     # 갈래별 브리프 작성
  - parallel: [audit-api, audit-batch, audit-web]   # 각자 독립 세션
  - synthesize                                      # 전 갈래를 기다려 병합
```

**적대적 검증.** 생성마다 독립 반증 노드를 짝지어 통과한 것만 남깁니다.

```yaml
workflow:
  - parallel:
      - [draft-a, refute-a]    # 반증 노드는 GRAPH_OUTPUT {"refuted": "yes|no"} 보고
      - [draft-b, refute-b]
  - synthesize                 # 이 노드에 context: [draft-a, draft-b] 를 지정
```

**생성 후 필터링.** 관점이 다른 생성 노드 여럿과 필터 하나로 구성합니다.

```yaml
workflow:
  - parallel: [ideate-risk, ideate-ux, ideate-cost]
  - filter                     # 중복 제거와 기준 채점 후 최선만 반환
```

**완료까지 반복.** 잔여 작업이 있다고 보고하는 동안 상한이 있는 자기 루프를
돕니다.

```yaml
workflow:
  - sweep:                     # 배치 1회 수행, GRAPH_OUTPUT {"remaining": "yes|no"}
      if: remaining == yes
      goto: sweep              # 자기 루프
      max: 20                  # 설계상 필수인 비용 상한
  - report
```

이 그래프들은 정적입니다. 노드 집합은 YAML 을 작성하는 시점에 고정됩니다.
런타임에 에이전트 수를 정하는 동적 팬아웃, 무상한 루프, 승자 진출식 쌍별
토너먼트는 설계상 범위 밖입니다. 고정 폭 팬아웃과 상한 있는 자기 루프, 병렬
시도를 한 번에 비교하는 판정 노드로 근사하세요.

## YAML 로 표현하는 것

| 기능 | 문법 |
|---|---|
| 순차와 병렬 단계 | 나열 순서 / `parallel: [a, b]` |
| 상태 기반 점프와 루프 | 노드에 `{if: FAILED, goto: ...}` 부착. 뒤로 goto 하면 피드백 루프 |
| 다중 케이스 라우팅 | `branch: {on: <출력 키>, cases: ...}` |
| 범위형 루프 블록 | `loop: {body, redo, max, exhausted}` |
| 사람 확인 지점 | `gate: true` 노드. 일시정지(종료 코드 3) 후 확정 값과 함께 resume |
| 결정적 셸 단계 | `type: command` 노드. 에이전트 세션 없이 실행하며 exit code 로 판정하고 stdout 의 `GRAPH_OUTPUT` 이 분기에 쓰임 |
| 저수준 엣지 | `edges:` 와 `route == heavy` 같은 when 표현식, `to: FAIL` 종결 |
| 상태와 재개 | `.graph-runs/<run-id>/state.json`, 성공 노드를 캐시하는 `--resume` |
| 사전 검증 | `--validate`, `--dry-run`, `--mermaid`, 상태·출력 대본을 주는 `--mock` |
| 로그 언어 | `settings.lang: en \| ko`. 로그와 주입 프로토콜이 현지화되며 마커는 언어 중립 |

에이전트는 마지막 줄에 `GRAPH_STATUS: SUCCEEDED|FAILED` 를, 필요하면
`GRAPH_OUTPUT: {"key": "value"}` 를 보고합니다. 러너가 이 프로토콜을
프롬프트에 자동 주입하고 모든 조건 엣지를 이 값으로 판정합니다.

## 두 가지 실행 모드

| | 러너 (기본) | 세션 |
|---|---|---|
| 오케스트레이터 | `run_graph.py` 스크립트 | Agent 툴을 쓰는 Claude |
| 보장 | 결정적이고 재개 가능하며 오케스트레이션 비용 없음 | 같은 YAML 을 해석해 수행 |
| 관찰 | 콘솔 로그, `run.log`, 노드별 출력 파일 | Claude Code UI 의 실시간 서브에이전트 트리 |
| 적합 | 무인, 대규모, 반복 실행 | 관찰, 디버깅, 중간 개입 |

기본값은 `pipeline.yml` 의 `settings.mode` 로 정하고, 실행할 때 "세션 모드로
돌려 줘"라고 말하면 그때만 바뀝니다.

## 운영 참고

- **비용 상한.** 최대 세션 수는 대략 노드 수에 피드백 노드 수와 루프 상한의
  곱을 더한 값입니다. 등록되는 트리거는 얇은 단일 파일 변경을 기본으로
  제외합니다.
- **사람 게이트.** headless 노드는 질문할 수 없습니다. 스펙 확정은 게이트에서
  이루어지고, 커밋과 머지는 실행이 끝난 뒤 사람이 합니다.
- **진화 루프.** 피드백은 구체적인 수정 대상(프롬프트, 에이전트, YAML)으로
  매핑되며, `graph-builder:edit` 가 검증과 변경 이력 기록을 포함해 반영합니다.

## 평가 스위트

스킬 계층은 `evals/` 아래에 자체 평가 스위트를 갖습니다. 스캐폴딩 완전성,
설치된 파이프라인의 제자리 수정(중복 생성 금지), 그리고 일반 코드 질문에는
아무것도 만들지 않는 트리거 절제를 검사합니다.

```
claude plugin eval graph-builder@graph-builder-marketplace --scaffold --runs 1
```

`plugin eval` 은 아직 얼리 액세스입니다. 결정적 그래프 엔진은 별도로
`--validate` 와 `--mock` 회귀(릴리스마다 22건)로 검증합니다.

## 플러그인 구조

```
.claude-plugin/                     # 매니페스트와 셀프 호스팅 마켓플레이스
skills/
  build/                            # graph-builder:build — 구성 담당
    SKILL.md                        # 6단계 절차
    scripts/run_graph.py            # 실행 엔진 (모든 산출물에 복사됨)
    templates/pipeline-dev/         # 산출물 스킬 골격 (SKILL.md, yml, prompts)
    templates/agents/               # 에이전트 정의 골격 (5개 역할)
    references/                     # yml 스펙, 팀 패턴, 에이전트 가이드,
                                    # 프롬프트 가이드, 세션 모드 규칙
  edit/                             # graph-builder:edit — 변경과 진단
evals/                              # 스킬 계층 평가 케이스 (build / edit / 트리거)
```
