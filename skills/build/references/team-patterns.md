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
기본 골격** — templates/pipeline-dev 가 이 패턴(+Fan-Out)이다.

```yaml
workflow:
  - implement
  - review:
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate            # 반복 실패 → 보고 노드 실행 후 자동 실패 종결
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

## 6. Fan-out & Synthesize (분할 후 종합)

작업을 컨텍스트가 격리된 갈래로 쪼개 병렬 수행하고, 배리어에서 병합한다.
갈래가 서로 간섭하면 안 되는 감사·조사류에 적합하다.

```yaml
workflow:
  - plan-slices                                     # 갈래별 브리프 파일 작성
  - parallel: [audit-api, audit-batch, audit-web]   # 각자 독립 세션
  - synthesize                                      # join: all 배리어 — 전 갈래 병합
```

## 7. Adversarial Verification (적대적 검증)

생성 노드마다 독립 반증 노드를 짝지어, 검증을 통과한 결과만 종합한다.
자기 선호 편향을 세션 격리로 구조적으로 차단한다.

```yaml
workflow:
  - parallel:
      - [draft-a, refute-a]     # 반증 노드는 GRAPH_OUTPUT {"refuted": "yes|no"} 보고
      - [draft-b, refute-b]
  - synthesize                  # 이 노드에 context: [draft-a, draft-b] 를 지정해
                                # 원문과 반증 판정을 함께 받는다
```

같은 골격에서 반증 노드를 채점 노드로 바꾸면 **생성 후 필터링**
(Generate-and-Filter)이 된다: `parallel: [ideate-a, ideate-b, ideate-c]` 뒤에
filter 노드 하나.

## 8. Loop until Done (완료까지 반복)

작업량을 미리 모를 때, 노드가 잔여 여부를 보고하는 동안 자기 루프를 돈다.
`max` 는 무한 반복이 아니라 비용 상한이다 — 초과 시 exhausted 경로로 위임된다.

```yaml
workflow:
  - sweep:                      # 배치 1회 수행, GRAPH_OUTPUT {"remaining": "yes|no"}
      if: remaining == yes
      goto: sweep               # 자기 루프
      max: 20
  - report                      # remaining 이 no 가 되면 진행
```

## 미지원 패턴 (정직하게 알려라)

- **동적 Fan-out / Supervisor**: 노드는 yml 에 정적 선언된다. 런타임에 작업
  개수에 따라 노드를 늘릴 수 없다 — 갈래 폭을 미리 고정하거나 세션 모드에서
  Claude 가 직접 Agent 를 늘리는 방식으로 우회한다.
- **쌍별 토너먼트**: 승자 진출식 반복 대진은 동적 흐름이라 표현할 수 없다.
  N개 병렬 시도 뒤 판정 노드 1개가 한 번에 비교하는 형태(7과 동일 골격)로
  근사한다.
- **무상한 루프**: 모든 루프에는 `max` 가 필수다 — 정지 조건이 영영 오지
  않을 때 비용이 무한히 새는 것을 막는 설계다.
- **실시간 팀 통신**: 노드 간 대화(SendMessage)는 없다. 결함은 피드백
  엣지로 순환한다 — 결정적·재현 가능하지만 왕복이 느리다.

## 선택 기준

| 요구 | 패턴 |
|---|---|
| "기능 개발 파이프라인" | 3 + 2 (기본 템플릿 그대로) |
| "배치·순차 작업 자동화" | 1 (+ 5 의 실패 분기) |
| "요청 유형별로 다르게 처리 (분류 후 실행)" | 4 |
| "머지 전 품질 검사 자동화" | 5 |
| "대규모 감사·조사를 나눠서" | 6 |
| "결과를 반증·채점으로 걸러서" | 7 |
| "남은 작업이 없어질 때까지" | 8 |
