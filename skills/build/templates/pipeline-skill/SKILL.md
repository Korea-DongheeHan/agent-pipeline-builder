---
name: {{pipeline_name}}
description: {{project_name}} 개발 오케스트레이션 스킬. 기능 개발·구현·수정·리팩토링, 테스트 보강, 코드 리뷰 요구사항 요청 시 이 스킬로 멀티 에이전트 파이프라인(분석→구현‖테스트→QA→리뷰, 실패 시 수렴 루프)을 실행한다. 후속 작업(재실행, 피드백 반영)에도 사용.
---

# {{pipeline_name}} — 개발 오케스트레이션 스킬

graph-builder 로 생성된 **독자 실행 오케스트레이션**이다. 이 디렉토리와
`.claude/agents/{{prefix}}-*.md` 만으로 동작한다 (graph-builder 설치 불필요).

- 흐름(SSOT): `pipeline.yml` — 노드·병렬·분기·피드백 루프
- 역할·전문성: `.claude/agents/{{prefix}}-*.md` (모델·도구·시스템 프롬프트)
- 태스크 입력·판정 기준: `prompts/*.md`
- 실행 엔진: `scripts/run_graph.py` (상태 관리·분기·병렬·재개)

## 실행 모드 선택

| 모드 | 방식 | 특징 |
|---|---|---|
| **러너 (기본)** | `python3 scripts/run_graph.py pipeline.yml` | 결정적 실행·상태 저장·resume. 각 노드는 독립 claude 세션(컨텍스트 격리). 진행은 콘솔 로그 |
| **세션** | `references/session-mode.md` 규칙에 따라 Claude 가 Agent 툴로 노드 실행 | 트리 UI 에 노드별 서브에이전트 표시(실시간 관찰). resume 없음 |

무인·배치 실행이나 규모가 큰 작업은 러너, 사용자가 진행을 지켜보고 싶어하면 세션.

## 절차 (Claude 가 이 스킬을 실행할 때)

이 스킬 디렉토리를 **GRAPH_PIPELINE**(`.claude/skills/{{pipeline_name}}`)라 한다.
프로젝트 루트에서 실행한다 (에이전트 정의·빌드 명령이 루트 기준).

0. **실행 컨텍스트 판별** — `.graph-runs/` 의 최근 run(state.json)을 확인해
   이번 요청의 성격을 정한다:
   - 이전 실행 없음 / 무관한 새 요구 → **신규 실행** (1번부터)
   - 직전 실행이 PAUSED/FAILED 이고 같은 작업의 계속 → **`--resume <RUN_ID>`**
   - 직전 실행 결과에 대한 부분 수정·피드백 반영 → 수정 범위를 정리해
     **새 실행** 으로 돌리되, requirement 에 "이전 결과(경로) 기반 증분 수정"을
     명시하고 이전 run 의 산출물 경로를 함께 전달한다
1. **입력 정리** — 사용자 요구사항을 `--var requirement="..."` 로 정리한다.
   모호하면 실행 전에 확정 질문을 한다 (headless 노드는 질문할 수 없다).
2. **비용 고지** — 노드 1회 실행 = claude 세션 1개. 노드 수·루프 상한 기준
   예상 세션 수를 사용자에게 알린다. 단일 파일 수준의 얇은 변경이면
   파이프라인 대신 직접 수행을 제안한다.
3. **러너 모드 실행:**
   ```bash
   python3 GRAPH_PIPELINE/scripts/run_graph.py GRAPH_PIPELINE/pipeline.yml --validate
   python3 GRAPH_PIPELINE/scripts/run_graph.py GRAPH_PIPELINE/pipeline.yml --var requirement="..."
   ```
   장시간 실행은 백그라운드로 돌리고 로그를 관찰한다. 실행 로그는
   `.graph-runs/<run-id>/run.log` 에 자동 기록되므로 리다이렉트가 필요 없다.
   (주의: `> .graph-runs/...` 리다이렉트는 첫 실행 시 디렉토리가 아직 없어
   실패한다 — 리다이렉트가 꼭 필요하면 이미 존재하는 경로를 쓰라.)
4. **SDD 스펙 게이트 (exit 3 / `⏸ PAUSED` 시 — 반드시 수행):**
   analyst 완료 후 파이프라인이 `spec-gate` 에서 일시정지한다.
   1. `.graph-runs/<run-id>/outputs/analyst.iter1.md` 를 읽는다 —
      스펙 초안과 `## 확정 필요 질문` 섹션이 있다.
   2. 확정 필요 질문을 **AskUserQuestion 1라운드(최대 4문항)** 로 사용자에게
      묻는다. analyst 의 권장안을 첫 옵션으로 두고 `(권장)` 을 붙인다.
      질문이 "없음"이면 스펙 초안 요약만 보여주고 진행 동의를 받는다.
   3. 확정 결과를 한 단락으로 정리해 재개한다:
      ```bash
      python3 GRAPH_PIPELINE/scripts/run_graph.py GRAPH_PIPELINE/pipeline.yml \
        --resume <RUN_ID> --var requirement="..." \
        --var decisions="① 범위: ... ② 아키텍처: ... ③ 완료 기준: ..."
      ```
      (성공한 analyst 는 캐시 재사용되고, 확정 스펙이 구현·테스트·QA·리뷰
      프롬프트에 주입된다. **스펙 확정 없이 구현을 진행하지 않는다.**)
5. **완료 시** — `.graph-runs/<run-id>/` 산출물(노드별 출력·acceptance 판정)을
   요약 보고한다. **실패 시** — state.json 의 실패 노드·사유를 보고하고, 원인
   수정 후 `--resume <RUN_ID>` 를 안내한다.
6. **세션 모드 요청 시** — `references/session-mode.md` 의 해석 규칙을 따라
   Agent 툴(subagent_type = 노드의 agent)로 그래프를 직접 오케스트레이션한다.
   게이트 노드는 그 자리에서 AskUserQuestion 으로 수행한다.
7. **마무리** — 커밋·머지는 사람 게이트다. 결과 검토 후 사용자 확인을 받아
   진행한다. 완료 보고 끝에 **개선 피드백을 선택적으로 묻는다** (강요 금지):
   "결과물이나 파이프라인 동작에서 아쉬운 점이 있었나요?" — 받은 피드백은
   아래 진화 표에 따라 수정 대상을 짚어 반영을 제안한다.

## 진화 (피드백 → 수정 대상)

이 파이프라인은 정적 산출물이 아니라 운영하며 다듬는 시스템이다.
같은 피드백이 2회 이상 반복되면 먼저 수정을 제안하라.

| 피드백 유형 | 수정 대상 |
|---|---|
| 결과물 품질 (누락·기준 미달) | `prompts/*.md` 판정 기준·acceptance 규약 |
| 역할 수행 방식 (엉뚱한 접근·컨벤션 위반) | `.claude/agents/{{prefix}}-*.md` |
| 순서·분기·루프가 어색함 | `pipeline.yml` workflow |
| 너무 느리거나 비쌈 | 노드 병합, 에이전트 `model:` 경량화, 루프 `max` 축소 |
| 질문이 부족/과다 (스펙 게이트) | `prompts/analyst.md` 확정 질문 규약 |

변경은 `graph-builder:edit` 스킬(플러그인 설치 시)로 수행하고, 수동 변경 시에도
`CHANGELOG.md` 에 한 줄(날짜·요청·변경 파일)을 남긴다.

## 구성 변경

- 흐름 변경: `pipeline.yml` (문법: yml 상단 주석 및 graph-builder 스펙)
- 판정 기준·태스크 입력: `prompts/*.md` / 역할·모델: `.claude/agents/{{prefix}}-*.md`
- 변경 후 필수: `--validate` → `--mock` 으로 그래프 로직 검증
- graph-builder 플러그인이 설치돼 있으면 **`graph-builder:edit` 스킬**이
  노드 추가·루프 조정·에이전트 변경을 안전하게 대신한다 ("파이프라인에 X 추가해줘")
