# pipeline.yml 스펙

그래프 파이프라인 정의 파일의 전체 스키마. 러너는 `scripts/run_graph.py`.

## 최상위

```yaml
name: my-pipeline        # 파이프라인 이름 (생략 시 파일명)
kind: development        # development | workflow — 스캐폴딩 시 프롬프트 성격 결정 (문서화 용도)
vars:                    # 프롬프트 변수. {{vars.KEY}} 로 치환. --var KEY=VALUE 가 덮어쓴다
  requirement: "..."
settings: { ... }        # 아래 참조
nodes: [ ... ]
edges: [ ... ]
```

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
    agent: point-reviewer      # 선택. claude --agent — 실행 저장소의
                               # .claude/agents/<이름> 정의(모델·도구·시스템 프롬프트)를 사용
    join: all                  # all(기본) | any — Fan-In 정책
    retry: 1                   # 선택. FAILED 시 즉시 재시도 횟수 (기본 0)
    allowed_tools: "Read Bash" # 선택. --allowedTools 로 전달
    context: [architect]       # 선택. 직접 선행이 아니어도 출력을 컨텍스트로 주입할 노드
    append_prompt: |           # 선택. 프롬프트 파일 뒤에 덧붙일 인라인 지시
      추가 지시...
```

- `join: all` — 모든 비-루프 인바운드 엣지가 도착해야 실행 (Fan-In 동기화)
- `join: any` — 하나라도 도착하면 실행 (조건 분기 합류점에 사용)
- **sticky 도착**: 한 번 충족된 선행 조건은 유지된다. 피드백 루프에서 실패한
  경로만 재실행돼도 Fan-In 노드는 (이전 도착 + 새 도착)으로 재트리거된다.

## edges

```yaml
edges:
  - from: review               # 노드 id | START | 리스트 (리스트 = 엣지 여러 개로 확장)
    to: [impl-a, impl-b]       # 노드 id | END | FAIL | 리스트 (리스트 = Fan-Out)
    when: FAILED               # 조건 (아래 참조). 생략 시 STATUS==SUCCEEDED
    loop:                      # 이 엣지를 피드백(순환) 엣지로 선언
      max: 3                   # 최대 발화 횟수
      on_exhausted: escalate   # FAIL(기본, 파이프라인 실패) | 위임할 노드 id
```

### when 조건

리스트로 쓰면 AND. 축약형: `when: SUCCEEDED` / `when: FAILED` / `when: ALWAYS`.

```yaml
when:
  - type: STATUS               # 노드 종료 상태로 판정
    status: SUCCEEDED          # SUCCEEDED | FAILED
  - type: OUTPUT               # 노드가 보고한 GRAPH_OUTPUT 값으로 판정
    key: route
    equals: heavy              # equals | not_equals | in: [a, b]
  - type: ALWAYS               # 무조건 발화
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
GRAPH_OUTPUT: {"key": "value"}   # 선택 — OUTPUT 조건 분기의 입력
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
