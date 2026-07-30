---
name: {{pipeline_name}}
description: {{이 파이프라인의 목적과 트리거 — "…한 요청 시 이 스킬을 사용" 형태로 메타 스킬이 작성. 예: "기능 개발·수정 요구사항을 설계→구현→테스트→리뷰 파이프라인으로 수행할 때 사용"}}
---

# {{pipeline_name}} — 그래프 파이프라인 하네스

graph-builder 로 생성된 **독자 실행 하네스**다. 이 디렉토리만으로 동작하며
graph-builder 설치가 필요 없다. 그래프 정의는 `pipeline.yml`(SSOT),
노드별 역할은 `prompts/*.md`, 러너는 `scripts/run_graph.py`.

## 실행 모드 선택

| 모드 | 방식 | 특징 |
|---|---|---|
| **러너 (기본)** | `python3 scripts/run_graph.py pipeline.yml` | 결정적 실행·상태 저장·resume. 각 노드는 독립 claude 세션(컨텍스트 격리). 진행은 콘솔 로그 |
| **세션** | `references/session-mode.md` 규칙에 따라 Claude 가 Agent 툴로 노드 실행 | 트리 UI 에 노드별 서브에이전트 표시(실시간 관찰). resume 없음, 메인 세션에 요약이 쌓임 |

무인·배치 실행이나 규모가 큰 작업은 러너, 사용자가 진행을 지켜보고 싶어하면 세션.

## 절차 (Claude 가 이 스킬을 실행할 때)

이 스킬 디렉토리를 **HARNESS** 라 한다 (`.claude/skills/{{pipeline_name}}`).

1. **입력 정리** — 사용자 요구사항을 `--var requirement="..."` 로 정리한다.
   모호하면 구현 전에 확정 질문을 한다 (headless 노드는 질문할 수 없다).
2. **비용 고지** — 노드 1회 실행 = claude 세션 1개다. 노드 수·루프 상한 기준
   예상 세션 수를 사용자에게 알린다.
3. **러너 모드 실행:**
   ```bash
   python3 HARNESS/scripts/run_graph.py HARNESS/pipeline.yml --validate
   python3 HARNESS/scripts/run_graph.py HARNESS/pipeline.yml --var requirement="..."
   ```
   장시간 실행은 백그라운드로 돌리고 로그를 관찰한다. 완료 후
   `.graph-runs/<run-id>/` 산출물(노드별 출력·판정)을 요약 보고한다.
4. **실패 시** — state.json 의 실패 노드·사유를 보고하고, 원인 수정 후
   `--resume <RUN_ID>` (성공 노드는 캐시 재사용)를 안내한다.
5. **세션 모드 요청 시** — `references/session-mode.md` 의 해석 규칙을 따라
   Agent 툴로 그래프를 직접 오케스트레이션한다.

## 유지보수

- 흐름(순서·분기·루프) 변경: `pipeline.yml` 의 workflow 블록
  (`if/goto` = 상태 체크 점프, `parallel` = 병렬, `loop` = 피드백 루프,
  `branch` = 다중 케이스 분기)
- 역할·판정 기준 변경: `prompts/*.md`
- 변경 후 반드시: `--validate` → `--mock` 으로 그래프 로직 검증
