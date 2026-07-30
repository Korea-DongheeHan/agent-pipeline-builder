# graph-builder 설계 문서

날짜: 2026-07-31

## 목적

사용자가 **yml + 프롬프트 파일**만 작성하면 멀티 에이전트 그래프 파이프라인(그래프(루프(하네스)))을
구축·실행할 수 있게 하는 **메타 스킬**과 **오케스트레이션 러너**를 제공한다.

- 메타 스킬(SKILL.md): 팀 성격(development / workflow)에 따라 다른 베이스 프롬프트로
  pipeline.yml + prompts/ 를 스캐폴딩하도록 Claude를 지휘한다.
- 러너(scripts/run_graph.py): yml을 읽어 노드(에이전트)를 실행하고,
  상태 관리·조건 분기·병렬·루프를 책임진다.

## 역할 분담

| 담당 | 책임 |
|---|---|
| 사용자 | pipeline.yml + prompts/*.md 작성 (스킬이 스캐폴딩 지원) |
| run_graph.py | 실행, 상태 관리, 조건 분기, 병렬/파이프라인, 루프, 재개(resume) |
| 서브 에이전트 | `claude -p` 헤드리스 세션. 작업 수행 후 GRAPH_STATUS/GRAPH_OUTPUT 보고 |

## 아키텍처 결정

1. **러너 언어**: Python 3 표준 라이브러리 단독. PyYAML이 있으면 사용, 없으면 내장
   미니 YAML 파서로 폴백 → 어떤 머신에서도 `python3 scripts/run_graph.py` 만으로 동작.
   (대안이던 Node+js-yaml은 npm install 필요, PyYAML 필수화는 이식성 저하로 기각)
2. **에이전트 실행**: `claude -p --output-format json` 서브프로세스. 병렬은
   ThreadPoolExecutor(`settings.parallelism`).
3. **상태 판정 프로토콜**: 러너가 모든 프롬프트 끝에 보고 규약을 자동 주입한다.
   - `GRAPH_STATUS: SUCCEEDED|FAILED` (필수)
   - `GRAPH_OUTPUT: {"key": "value"}` (선택 — OUTPUT 조건 분기용)
   마커가 없고 exit 0이면 SUCCEEDED로 간주(경고 로그).
4. **그래프 시맨틱**
   - 노드: 에이전트 1개(프롬프트 파일 + 모델/도구 옵션). `join: all|any` 로 Fan-In 정책 결정.
   - 엣지: `from`/`to`(리스트 허용 → Fan-Out/In), `when`(조건 리스트, AND),
     `loop: {max, on_exhausted}` — loop가 붙은 엣지만 순환(피드백) 허용.
   - `when` 생략 시 기본값은 `STATUS == SUCCEEDED` (사용자 예시 yml의 의미와 동일).
   - 사이클 검증: loop 엣지를 제외한 그래프는 DAG여야 한다.
   - END 도달 = 파이프라인 성공. 실행 중 노드는 완료까지 대기, 신규 활성화는 중단.
   - 데드락(실행 중 없음 + END 미도달) = 파이프라인 실패 + 원인 진단 출력.
5. **컨텍스트 전달**: 선행 노드의 출력(요약 아님, 최대 길이 제한)을 후속 노드 프롬프트에
   자동 주입. 전체 출력 파일 경로도 함께 제공.
6. **프롬프트 경로**: 스크립트 실행 위치(cwd) 기준 상대경로. 없으면 pipeline.yml 위치 기준 폴백.
7. **상태 저장**: `.graph-runs/<run-id>/state.json` + 노드별 프롬프트/출력 파일.
   `--resume` 시 SUCCEEDED 노드는 캐시 재사용, 실패/다운스트림은 재실행(베스트 에포트).
8. **모의 실행**: `--mock` (+ `--mock-status node=FAILED,SUCCEEDED`)으로 claude 호출 없이
   그래프 로직(분기·루프·병렬) 검증 가능. 스킬의 스캐폴딩 검증 단계에서 사용.

## 팀 성격별 프롬프트 차별화

- **development**: 설계 → (Fan-Out) 구현 → (Fan-In) 테스트 → 리뷰, 리뷰/테스트 실패 시
  구현으로 피드백 루프. 프롬프트에 역할·산출물·완료 기준·리뷰 지적 형식 포함.
- **workflow**: 태스크 체인(사용자 예시의 point-leave와 동일한 형태). 프롬프트에
  절차·멱등성·실패 판정 기준 포함. 실패 시 on-failure 노드로 분기하는 템플릿 제공.

## 디렉토리 구조 (이 저장소 = 스킬 패키지)

```
graph-builder/
  SKILL.md                 # 메타 스킬: 스캐폴딩 절차 지시
  scripts/run_graph.py     # 오케스트레이션 러너 (단일 파일)
  references/yml-spec.md   # pipeline.yml 전체 스펙
  references/prompt-guide.md # kind별 베이스 프롬프트 가이드
  templates/dev-team/      # development 템플릿 (yml + prompts)
  templates/workflow/      # workflow 템플릿 (yml + prompts)
  examples/leave-batch/    # 사용자 예시 yml의 변환본
  examples/dev-harness-graph/  # 오케스트레이터 하네스 스킬 변환 예제
  README.md
```

## 추가 결정 (구현 중 사용자 피드백 반영)

- 예제에 사내 프로젝트 고유 명칭을 쓰지 않는다 (일반화된 이름 사용).
- 워크플로우 표기는 평면 엣지 나열이 아니라 **중첩 블록 DSL**(`workflow:` 의
  parallel/loop/branch, START/END 자동 연결)을 권장 문법으로 하고, 러너가
  엣지로 컴파일한다. 저수준 `edges:` 는 특수 위상용으로 유지.

## 테스트 계획 (--mock 기반)

1. point-leave 예시: 순차 실행 순서 검증
2. dev-team 템플릿: Fan-Out/In + `test=FAILED,SUCCEEDED` 로 피드백 루프 1회 검증
3. 루프 소진: max 초과 시 on_exhausted=FAIL 동작 검증
4. `--validate` / `--dry-run` / `--mermaid` 출력 검증
