# 태스크: prepare (입력 준비 + 경로 결정)

## 절차
1. 처리 대상 입력을 수집·검증하라. (이 템플릿을 실제 태스크에 맞게 수정)
2. 입력 규모·특성에 따라 처리 경로를 결정하라:
   - `heavy`: 대량/복잡 — process-heavy 노드가 처리
   - `light`: 소량/단순 — process-light 노드가 처리

## 규칙
- 이 태스크는 멱등해야 한다 — 재실행해도 결과가 같아야 한다.
- 입력이 유효하지 않으면 FAILED 로 판정하라.

## 판정
후속 분기를 위해 결정한 경로를 반드시 GRAPH_OUTPUT 으로 보고하라:

GRAPH_OUTPUT: {"route": "heavy"}
GRAPH_STATUS: SUCCEEDED
