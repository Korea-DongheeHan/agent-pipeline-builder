---
name: edit
description: 프로젝트에 설치된 그래프 파이프라인(개발 오케스트레이션)의 구성 변경 지원 스킬. "파이프라인에 노드/단계 추가", "루프 횟수·분기 조건 변경", "이 단계 빼줘", "에이전트 모델 바꿔", "파이프라인이 왜 실패했는지 봐줘" 등 .claude/skills/*/pipeline.yml 과 .claude/agents 를 수정·진단할 때 사용. 새 오케스트레이션 구축은 graph-builder:build.
---

# graph-builder:edit — 파이프라인 구성 변경·진단

설치된 오케스트레이션의 **yml·프롬프트·에이전트를 안전하게 바꾼다.**
원칙: 변경은 3계층(흐름=yml, 태스크 입력=prompts, 역할=agents)을 동기화하고,
반드시 mock 으로 검증한 뒤 끝낸다.

## 절차

### 1. 대상 파악

`.claude/skills/*/pipeline.yml` 을 찾는다. 여러 개면 사용자에게 확인.
DSL 문법이 필요하면 이 스킬 기준 `../build/references/yml-spec.md` 를 읽는다.
현재 구조를 `--mermaid` 로 확인하고, 변경 전 상태로 기억해 둔다.

### 2. 변경 설계 — 유형별 체크리스트

| 요청 | 변경할 것 |
|---|---|
| 노드(단계) 추가 | ① yml `nodes` 항목 + `workflow` 내 위치 ② `prompts/<노드>.md` 생성 ③ 전용 역할이 필요하면 `.claude/agents/<prefix>-*.md` (build 스킬의 `templates/agents/` 참고) |
| 노드 제거 | yml 에서 노드·해당 스텝 제거 + goto/branch 가 그 노드를 가리키지 않는지 확인 (`--validate` 가 잡는다) + 고아 프롬프트 삭제 |
| 루프 조정 | 해당 노드의 `max` / `exhausted` 값 (if/goto 부착 또는 loop 블록) |
| 분기 추가·변경 | 상태 체크는 노드 부착 `{if, goto}`, 다중 케이스는 `branch:` — 케이스 전수 정의(미매칭 = 데드락), 합류점 `join: any` 확인 |
| 병렬화 | 순차 노드를 `parallel: [...]` 로 묶고 인터페이스 확정 책임을 선행 노드 프롬프트에 명시 |
| 판정 기준 변경 | `prompts/<노드>.md` 의 판정 절 + GRAPH_OUTPUT 키를 쓰는 엣지 조건 동기화 |
| 에이전트 변경 | `.claude/agents/<이름>.md` (모델·도구·역할) — yml `agent:` 값과 name 일치 유지 |
| 실패 진단 | `.graph-runs/<run-id>/state.json` 의 실패 노드·사유 → `outputs/<노드>.iterN.md` 전문 확인 → 원인이 프롬프트/에이전트/흐름 중 어디인지 판정 |

### 3. 적용 및 검증 (필수)

```bash
PL=.claude/skills/<파이프라인명>
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --validate
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mermaid    # 변경 후 구조를 사용자에게 제시
# 바뀐 경로를 mock 으로 통과시킨다 (분기·루프가 실제로 그 길로 도는지):
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock --mock-status <노드>=FAILED,SUCCEEDED
python3 $PL/scripts/run_graph.py $PL/pipeline.yml --mock --mock-output '<노드>={"key": "값"}'
```

### 4. 보고

변경 전/후 mermaid 비교, 수정 파일 목록, mock 검증 결과, 트리거 문구가
바뀌어야 하면 CLAUDE.md 마커 블록 갱신 여부를 보고한다.

## 주의

- `scripts/run_graph.py` 는 수정하지 않는다 — 엔진 버그·기능 요구는
  graph-builder 플러그인 쪽 이슈다.
- 노드 실패를 처리하는 엣지가 없으면 파이프라인 즉시 실패가 **기본 동작**이다
  — 무조건 실패 분기를 추가하지 말고 그 동작이 맞는지 먼저 판단한다.
- 검증 없이 변경을 끝내지 않는다. mock 을 건너뛴 변경은 미완성이다.
