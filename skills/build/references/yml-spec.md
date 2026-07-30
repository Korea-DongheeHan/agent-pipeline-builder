# pipeline.yml 스펙

그래프 파이프라인 정의 파일의 전체 스키마. 러너는 `scripts/run_graph.py`.

## 최상위

```yaml
name: my-pipeline        # 파이프라인 이름 (생략 시 파일명)
kind: development        # development | workflow — 스캐폴딩 시 프롬프트 성격 결정 (문서화 용도)
vars:                    # 프롬프트 변수. {{vars.KEY}} 로 치환. --var KEY=VALUE 가 덮어쓴다
  requirement: "..."
settings: { ... }        # 아래 참조
nodes: [ ... ]           # 노드(에이전트) 정의
workflow: [ ... ]        # 권장 — 중첩 블록 DSL (아래 참조)
edges: [ ... ]           # 저수준 — 엣지 직접 정의 (workflow 와 병용 가능)
```

## workflow — 중첩 블록 DSL (권장)

워크플로우를 **위에서 아래로 읽히는 중첩 구조**로 쓴다. 러너가 내부적으로
엣지로 컴파일한다. START/END 는 자동 연결된다 (첫 스텝 앞 START, 마지막
스텝의 SUCCEEDED 뒤 END).

```yaml
workflow:
  - analyst                            # 문자열 = 노드 순차 실행 (선행 SUCCEEDED 시)
  - parallel: [implement, test]        # Fan-Out. 항목 = 노드 | 시퀀스 | 중첩 블록
  - qa:                                # Fan-In — 병렬 갈래가 모두 끝나야 실행
      if: FAILED                       # 노드 부착 라우팅: 이 노드의 상태·출력 체크 후 점프
      goto: implement                  # 이미 나온 노드로 = 피드백 루프 (자동 판정)
      max: 2                           # 루프 상한 (뒤로 goto 기본 3)
      exhausted: [escalate, FAIL]      # 소진 시 경로: FAIL(기본) | 노드 | 시퀀스
  - review
  - branch:                            # 다중 케이스 분기 (단일 선행 노드 뒤에만)
      on: route                        # GRAPH_OUTPUT 키. 생략 시 케이스 키가
      cases:                           # SUCCEEDED|FAILED|ALWAYS (STATUS 분기)
        heavy: process-heavy           # 케이스 값 = 노드 | 시퀀스 (END/FAIL 터미널 허용)
        light: [process-light]
  - finalize                           # 분기 합류점 — 자동으로 join: any
```

블록 시맨틱:

- **순차**: 리스트 순서대로. 각 연결의 기본 조건은 선행 SUCCEEDED.
- **parallel**: 갈래를 동시에 실행. 다음 스텝은 모든 갈래 완료를 기다린다
  (join: all). 갈래 안에 시퀀스·중첩 블록을 넣을 수 있다.
- **if/goto** (권장 — 상태 체크 분기·루프): 노드에 라우팅 규칙을 부착한다.
  상태(`if: FAILED`)나 출력(`if: route == heavy`)을 체크해 점프한다.
  ```yaml
  - qa:                          # 규칙 여러 개는 리스트로:
      if: FAILED                 #   - qa:
      goto: implement            #       - {if: FAILED, goto: implement, max: 2}
      max: 2                     #       - {if: risk == high, goto: security}
  ```
  - **뒤로 goto** (이미 나온 노드) = 피드백 루프. `max`(기본 3) 초과 시
    `exhausted` 경로로 위임. goto 에 리스트를 주면 여러 노드 재작업.
  - **앞·측면·END·FAIL 로 goto** = 조건 분기. 대상 노드는 자동 `join: any`.
  - `if` 를 생략하면 무조건 점프이고 순차 흐름은 거기서 끊긴다.
  - OUTPUT 조건(`==`/`!=`)이면 다음 스텝의 기본 엣지에 부정 조건이 자동
    주입돼 배타가 보장된다 (`in` 은 자동 배타 미지원 — branch 를 써라).
- **loop**: 루프 범위를 블록으로 명시하고 싶을 때. `body` 안에서 **redo 스텝
  이후의 노드가 FAILED** 를 보고하면 redo 노드로 피드백한다. redo 스텝
  이전(포함) 노드의 FAILED 는 파이프라인 실패. `max` 초과 시 `exhausted` 위임.
  ```yaml
  - loop:
      max: 2
      exhausted: [escalate, FAIL]
      redo: implement                  # 생략 시 body 첫 노드
      body:
        - parallel: [implement, test]
        - qa
        - review
  ```
- **branch**: 선행 노드의 GRAPH_OUTPUT(`on` 키) 또는 STATUS 로 케이스를
  고른다. 매칭되는 케이스가 없으면 데드락으로 파이프라인 실패 — 케이스를
  전수 정의하라. 합류점(다음 스텝)은 자동으로 `join: any` 가 된다
  (노드에 join 을 명시했으면 그 값을 존중).
- **합류점 주의**: 여러 경로 중 일부만 도착하는 노드에 수동 `edges:` 로
  들어오는 엣지를 섞으면 `join: any` 를 노드에 명시해야 한다.

## settings

| 키 | 기본값 | 설명 |
|---|---|---|
| `parallelism` | 4 | 동시에 실행할 최대 노드 수 |
| `state_dir` | `.graph-runs` | 실행 상태·산출물 저장 위치 |
| `node_timeout` | 3600 | 노드(에이전트) 1회 실행 제한(초) |
| `max_total_steps` | 100 | 총 노드 활성화 횟수 상한 (루프 폭주 방지) |
| `context_max_chars` | 8000 | 선행 노드 출력을 프롬프트에 주입할 때 노드당 최대 길이 |
| `claude_args` | `[]` | 모든 노드의 claude CLI 에 붙일 공통 인자. 예: `["--permission-mode", "acceptEdits"]` |
| `model` | (없음) | 기본 모델. 노드별 `model` 이 우선 |
| `claude_bin` | `claude` | claude 실행 파일 경로 (env `CLAUDE_BIN` 도 지원) |

## nodes

```yaml
nodes:
  - id: review                 # 필수, 고유. START/END/FAIL 은 예약어
    prompt: prompts/review.md  # 필수. 스크립트 실행 위치(cwd) 기준 상대경로.
                               # 없으면 pipeline.yml 위치 기준으로 폴백
    model: opus                # 선택. 노드별 모델
    agent: my-reviewer         # 선택. claude --agent — 실행 저장소의
                               # .claude/agents/<이름> 정의(모델·도구·시스템 프롬프트)를 사용
    join: all                  # all(기본) | any — Fan-In 정책 (workflow DSL 이 자동 설정)
    retry: 1                   # 선택. FAILED 시 즉시 재시도 횟수 (기본 0)
    allowed_tools: "Read Bash" # 선택. --allowedTools 로 전달
    context: [architect]       # 선택. 직접 선행이 아니어도 출력을 컨텍스트로 주입할 노드
    append_prompt: |           # 선택. 프롬프트 파일 뒤에 덧붙일 인라인 지시
      추가 지시...
```

- `join: all` — 모든 비-루프 인바운드 엣지가 도착해야 실행 (Fan-In 동기화)
- `join: any` — 하나라도 도착하면 실행 (조건 분기 합류점)
- **sticky 도착**: 한 번 충족된 선행 조건은 유지된다. 피드백 루프에서 실패한
  경로만 재실행돼도 Fan-In 노드는 (이전 도착 + 새 도착)으로 재트리거된다.
  단, 업스트림이 아직 실행/대기 중이면 완료까지 기다렸다가 1회만 재실행한다.

## edges — 저수준 정의

workflow DSL 로 표현하기 어려운 특수 위상이 필요할 때 쓴다. workflow 와
병용하면 컴파일된 엣지에 더해진다.

```yaml
edges:
  - from: review               # 노드 id | START | 리스트 (리스트 = 엣지 여러 개로 확장)
    to: [impl-a, impl-b]       # 노드 id | END | FAIL | 리스트 (리스트 = Fan-Out)
    when: FAILED               # 조건. 생략 시 STATUS==SUCCEEDED
    loop:                      # 이 엣지를 피드백(순환) 엣지로 선언
      max: 3
      on_exhausted: escalate   # FAIL(기본) | 위임할 노드 id
```

### when 조건

리스트로 쓰면 AND. 문자열 축약형과 표현식을 지원한다:

```yaml
when: FAILED                   # STATUS 축약형: SUCCEEDED | FAILED | ALWAYS
when: route == heavy           # GRAPH_OUTPUT 표현식: == | != | in [a, b]
when:
  - type: STATUS               # 명시형
    status: SUCCEEDED
  - type: OUTPUT
    key: route
    equals: heavy              # equals | not_equals | in: [a, b]
```

### 그래프 규칙

- `loop` 없는 엣지만으로는 사이클이 없어야 한다(DAG). 순환(피드백)은 반드시
  `loop` 를 붙인 엣지로만 만든다 — `--validate` 가 위반을 잡는다.
- `to: END` 도달 = 파이프라인 성공. 이후 신규 활성화는 멈추고 실행 중 노드만 마무리.
- `to: FAIL` 도달 = 파이프라인을 의도적으로 실패로 종결 (에스컬레이션 보고 후 등).
- 노드가 FAILED 인데 매칭되는 엣지가 없으면 파이프라인 즉시 FAILED.
- 실행할 노드가 없는데 END 미도달이면 데드락으로 FAILED + 대기 원인 출력.

## 에이전트 상태 보고 프로토콜

러너가 모든 프롬프트 끝에 자동 주입한다 (프롬프트 파일에 다시 쓸 필요 없음):

```
GRAPH_OUTPUT: {"key": "value"}   # 선택 — branch/OUTPUT 조건의 입력
GRAPH_STATUS: SUCCEEDED          # 필수 — SUCCEEDED | FAILED
```

마커가 없고 exit 0 이면 SUCCEEDED 로 간주(경고 로그). 프롬프트 파일에는
**판정 기준**(무엇이 성공/실패인지)과 **GRAPH_OUTPUT 키 규약**만 쓴다.

## 프롬프트 변수 치환

`{{vars.KEY}}`, `{{run.id}}`, `{{node.id}}`, `{{node.iteration}}`

## 컨텍스트 주입

노드 실행 시 직접 선행 노드(+ `context` 로 지정한 노드)의 최신 출력이
"선행 노드 출력" 섹션으로 프롬프트에 자동 주입된다. `context_max_chars`
초과분은 잘리고 전체 출력 파일 경로가 함께 제공된다.

## CLI

```
python3 scripts/run_graph.py pipeline.yml            # 실행
  --validate                                         # 검증만 (스키마·도달성·사이클)
  --dry-run                                          # 병렬 wave 실행 계획 출력
  --mermaid                                          # mermaid 다이어그램 출력
  --mock                                             # claude 호출 없는 모의 실행
  --mock-status NODE=FAILED,SUCCEEDED                # mock 상태 시퀀스 (iter 별, 마지막 값 유지)
  --mock-output 'NODE={"route": "light"}'            # mock GRAPH_OUTPUT 주입
  --resume RUN_ID                                    # 재개: SUCCEEDED 노드 캐시 재사용
  --var KEY=VALUE                                    # 프롬프트 변수 주입
```

종료 코드: 성공 0, 실패 1, 로드/검증 실패 2.

## 실행 산출물

```
<state_dir>/<run-id>/
  state.json                  # 노드 상태·outputs·루프 카운터 (resume 입력)
  prompts/<node>.iterN.prompt.md   # 실제 주입된 프롬프트 (디버깅)
  outputs/<node>.iterN.md          # 노드 출력 전문
```
