# 에이전트 정의(.claude/agents) 작성 가이드

산출물 파이프라인의 각 노드는 프로젝트 에이전트 정의를 사용한다
(`nodes[].agent` → `claude --agent`, 세션 모드에선 `subagent_type`).
템플릿: `templates/agents/*.md`.

## 역할 분담 (반드시 지켜라)

| 위치 | 담는 것 | 바뀌는 빈도 |
|---|---|---|
| `.claude/agents/<prefix>-*.md` | **역할·전문성**: 시스템 프롬프트(작업 방식·금지사항), 프로젝트 사실(빌드·테스트 명령, 컨벤션), 모델·도구 제한 | 낮음 (프로젝트 특성) |
| `prompts/*.md` | **태스크 입력·판정 기준**: 무엇을 받고 무엇이면 성공인지, GRAPH_OUTPUT 키 규약 | 중간 (파이프라인 설계) |
| `pipeline.yml` | **흐름**: 순서·병렬·분기·루프 | 높음 (운영하며 조정) |

같은 내용을 두 곳에 쓰지 마라 — 역할이 프롬프트에도 있으면 수정 시 어긋난다.

## frontmatter

```markdown
---
name: {{prefix}}-analyst          # 필수. 파이프라인 yml 의 agent: 값과 일치
description: ...                  # 필수. 언제 이 에이전트를 쓰는지 (자동 위임 판단 기준)
model: sonnet                     # 선택. 생략 시 세션 모델 상속
tools: Read, Grep, Glob, Bash     # 선택. 생략 시 전체 도구
---
(본문 = 시스템 프롬프트)
```

## 플레이스홀더 치환 (스캐폴딩 시 필수)

Phase 1 프로젝트 분석에서 얻은 사실로 치환한다. 하나라도 남기면 안 된다:

| 플레이스홀더 | 채우는 값 |
|---|---|
| `{{prefix}}` | 에이전트 접두어 (프로젝트 슬러그, 예: `pay`) |
| `{{project_name}}` | 프로젝트 이름 |
| `{{tech_stack}}` | 언어·프레임워크 (예: Kotlin + Spring Boot 멀티모듈) |
| `{{build_command}}` / `{{test_command}}` | 실제 명령 (예: `./gradlew build`) |
| `{{conventions}}` | 레이어 규칙·의존 방향·네이밍 등 핵심 컨벤션 요약 |
| `{{test_conventions}}` | 테스트 프레임워크·배치 규칙 |

## 모델 배정 권고

- analyst / reviewer: 판단 품질이 결과를 좌우 — 상위 모델 유지(생략 = 상속)
- test-engineer / qa: 절차적 — `model: sonnet` 등 경량화로 비용 절감 가능
- 확신 없으면 생략(상속)이 안전하다

## 기존 에이전트가 있는 프로젝트

`.claude/agents/` 에 역할이 겹치는 정의가 이미 있으면 **새로 만들지 말고
재사용**한다 — pipeline.yml 의 `agent:` 값만 기존 이름으로 맞춘다.
부족한 역할만 템플릿으로 보충한다.
