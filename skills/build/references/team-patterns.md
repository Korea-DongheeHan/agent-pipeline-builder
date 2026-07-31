# 팀 아키텍처 패턴 — 그래프 DSL 대응표

요구사항에서 팀 구조를 고를 때 이 패턴에서 출발한다. 모든 패턴은
pipeline.yml 의 workflow DSL 로 표현되며 조합 가능하다.

## 1. Pipeline (순차 체인)

작업이 선후 관계로만 이어질 때. 배치 잡 체인, 마이그레이션 단계.

```yaml
workflow:
  - extract
  - transform
  - load
```

## 2. Fan-Out / Fan-In (병렬 분업)

독립 작업을 동시에 진행하고 합류점에서 동기화. 다갈래 구현, 다차원 검사.

```yaml
workflow:
  - plan
  - parallel: [impl-api, impl-batch, impl-admin]
  - integrate            # join: all (기본) — 전 갈래 완료 대기
```

## 3. Producer–Reviewer (생성 → 검수 + 수렴 루프)

산출물을 만들고 독립 검수자가 판정, 실패 시 재작업. **개발 오케스트레이션의
기본 골격** — templates/pipeline-skill 이 이 패턴(+Fan-Out)이다.

```yaml
workflow:
  - implement
  - review:
      if: FAILED
      goto: implement
      max: 2
      exhausted: [escalate, FAIL]   # 반복 실패는 사람에게 위임
```

## 4. Expert Pool (조건 라우팅)

입력 특성에 따라 다른 전문가에게 위임. 분류 노드가 GRAPH_OUTPUT 으로
라우팅 키를 보고한다.

```yaml
workflow:
  - triage                          # GRAPH_OUTPUT: {"kind": "bug"|"feature"|"docs"}
  - branch:
      on: kind
      cases:
        bug: [reproduce, fix]
        feature: [design, implement]
        docs: update-docs
  - verify                          # 합류점 — 자동 join: any
```

## 5. Gate (품질 게이트 체인)

단계마다 통과/탈락을 판정하고 탈락 시 즉시 실패 경로로. 검증 위주 파이프라인.

```yaml
workflow:
  - build-check:
      if: FAILED
      goto: [report-failure, FAIL]  # 앞으로 goto = 분기 (report 후 실패 종결)
  - security-scan:
      if: FAILED
      goto: [report-failure, FAIL]
  - deploy-ready
```

## 미지원 패턴 (정직하게 알려라)

- **Supervisor(동적 작업 분배)**: 노드는 yml 에 정적 선언된다. 런타임에
  작업 개수에 따라 노드를 늘릴 수 없다 — 갈래를 미리 고정하거나 세션 모드에서
  Claude 가 직접 Agent 를 늘리는 방식으로 우회한다.
- **실시간 팀 통신**: 노드 간 대화(SendMessage)는 없다. 결함은 피드백
  엣지로 순환한다 — 결정적·재현 가능하지만 왕복이 느리다.

## 선택 기준

| 요구 | 패턴 |
|---|---|
| "기능 개발 파이프라인" | 3 + 2 (기본 템플릿 그대로) |
| "배치·순차 작업 자동화" | 1 (+ 5 의 실패 분기) |
| "요청 유형별로 다르게 처리" | 4 |
| "머지 전 품질 검사 자동화" | 5 |
