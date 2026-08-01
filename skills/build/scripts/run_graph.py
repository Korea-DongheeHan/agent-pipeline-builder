#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
graph-builder 러너: pipeline.yml + 프롬프트 파일로 정의된 에이전트 그래프를 실행한다.

- 노드 = 서브 에이전트 (claude -p 헤드리스 세션)
- 엣지 = 트리거 (when 조건부 분기, loop 피드백 순환)
- Fan-Out(to 리스트) / Fan-In(join: all|any) / 조건 분기 / 피드백 루프 지원
- 상태는 <state_dir>/<run-id>/state.json 에 저장, --resume 으로 재개

사용법:
  python3 scripts/run_graph.py pipeline.yml                 # 실행
  python3 scripts/run_graph.py pipeline.yml --validate      # 검증만
  python3 scripts/run_graph.py pipeline.yml --dry-run       # 실행 계획 출력
  python3 scripts/run_graph.py pipeline.yml --mermaid       # mermaid 다이어그램 출력
  python3 scripts/run_graph.py pipeline.yml --mock          # claude 호출 없는 모의 실행
  python3 scripts/run_graph.py pipeline.yml --mock --mock-status review=FAILED,SUCCEEDED
  python3 scripts/run_graph.py pipeline.yml --resume RUN_ID
  python3 scripts/run_graph.py pipeline.yml --var ticket=ABC-123

의존성: Python 3 표준 라이브러리만 사용. PyYAML이 설치돼 있으면 우선 사용하고,
없으면 내장 미니 YAML 파서(이 파이프라인 스키마에 필요한 부분집합)로 폴백한다.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

START, END, FAIL = "START", "END", "FAIL"
STATUS_RE = re.compile(r"GRAPH_STATUS:\s*(SUCCEEDED|FAILED)", re.IGNORECASE)
OUTPUT_RE = re.compile(r"GRAPH_OUTPUT:\s*(\{.*\})")

# ---------------------------------------------------------------------------
# 메시지 카탈로그 — settings.lang(en|ko)으로 실행 로그와 프롬프트 주입 문구를 고른다.
# 상태 마커(GRAPH_STATUS 등)와 종료 코드는 언어와 무관하다.
# ---------------------------------------------------------------------------
MESSAGES = {
    "en": {
        "start": "▶ pipeline '%s' started — run_id=%s%s",
        "mock": " (mock)",
        "session_note": "ℹ settings.mode is 'session' but running via the runner"
                        " (session mode is interpreted by Claude with the Agent tool)",
        "cache": "⏩ %s reused from cache (SUCCEEDED in a previous run)",
        "gate_pass": "⏩ gate %s passed (confirmed in a previous run)",
        "gate_pause": "⏸ gate %s reached — paused",
        "node_start": "▶ %s started (iter %d)",
        "node_end": "%s %s %s (iter %d)",
        "feedback": "↻ feedback %s → %s (%d/%d)",
        "delegate": "⚠ loop exhausted %s → delegated to node '%s'",
        "retry": "↺ %s failed, retrying %d/%d",
        "no_marker": "⚠ missing GRAPH_STATUS marker — exit 0, assuming SUCCEEDED",
        "dead_end": "⚠ no matching edge after %s SUCCEEDED (path ends)",
        "end": "● END reached",
        "fail_route": "node %s routed to the FAIL terminal (%s)",
        "fail_after": "node '%s' finished — failing the pipeline as declared (goto: [..., FAIL])",
        "exhaust_done": "loop exhaustion handled — '%s' finished its report;"
                        " failing the pipeline (see its output)",
        "fail_no_edge": "node %s FAILED — no edge handles the failure",
        "loop_out": "feedback loop exhausted: %s (max %d exceeded)",
        "max_steps": "max_total_steps(%s) exceeded — aborted by the runaway guard",
        "deadlock": "no runnable node and END not reached (deadlock). waiting on: %s",
        "none": "none",
        "not_run": "not run",
        "ok": "✔ pipeline SUCCEEDED — artifacts: %s",
        "paused": "⏸ pipeline PAUSED — waiting at gate '%s'",
        "paused_review": "  review upstream outputs: %s/outputs/",
        "paused_resume": "  resume after confirming: python3 %s %s --resume %s [--var key=value ...]",
        "failed": "✘ pipeline FAILED — %s",
        "resume_hint": "  resume: python3 %s %s --resume %s",
        "timeout": "node timed out (over %ss)",
        "no_cli": "claude CLI not found: %s",
        "internal": "runner internal error: %r",
        "mock_text": "[MOCK] %s iter %d result",
        "ctx_header": "---\n## Upstream node outputs (context)\n\n",
        "ctx_item": "### upstream `%s` — %s (iter %d)\nfull output file: %s\n\n%s",
        "ctx_trunc": "\n...(truncated — see the full output file)",
        "protocol": "---\n"
                    "## Execution protocol (mandatory)\n"
                    "This is pipeline '%s'; you are its node `%s` (iteration %d, run_id=%s).\n"
                    "When your work is done, report on the very last line:\n\n"
                    "GRAPH_STATUS: SUCCEEDED   (success)  or  GRAPH_STATUS: FAILED   (failure)\n\n"
                    "If downstream routing needs values, put a one-line JSON right above it:\n\n"
                    "GRAPH_OUTPUT: {\"key\": \"value\"}\n",
        "validated": "validation passed: %d nodes, %d edges (%s)",
    },
    "ko": {
        "start": "▶ 파이프라인 '%s' 시작 — run_id=%s%s",
        "mock": " (mock)",
        "session_note": "ℹ settings.mode 는 session 이지만 러너로 실행한다"
                        " (세션 모드는 Claude 가 Agent 툴로 해석 실행)",
        "cache": "⏩ %s 캐시 재사용 (이전 실행 SUCCEEDED)",
        "gate_pass": "⏩ 게이트 %s 통과 (이전 실행에서 확인됨)",
        "gate_pause": "⏸ 게이트 %s 도달 — 일시정지",
        "node_start": "▶ %s 시작 (iter %d)",
        "node_end": "%s %s %s (iter %d)",
        "feedback": "↻ 피드백 %s → %s (%d/%d)",
        "delegate": "⚠ 루프 소진 %s → '%s' 노드로 위임",
        "retry": "↺ %s 실패, 재시도 %d/%d",
        "no_marker": "⚠ GRAPH_STATUS 마커가 없다 — exit 0 이므로 SUCCEEDED 로 간주",
        "dead_end": "⚠ %s SUCCEEDED 이후 매칭되는 엣지가 없다 (경로 종료)",
        "end": "● END 도달",
        "fail_route": "노드 %s 가 FAIL 종단으로 라우팅됐다 (%s)",
        "fail_after": "'%s' 완료 — 선언된 FAIL 라우팅(goto: [..., FAIL])에 따라 파이프라인을 실패로 종결한다",
        "exhaust_done": "루프 소진 처리 완료 — '%s' 수행 후 파이프라인을 실패로 종결한다 (산출물 확인)",
        "fail_no_edge": "노드 %s FAILED — 실패를 처리하는 엣지가 없다",
        "loop_out": "피드백 루프 소진: %s (max %d 초과)",
        "max_steps": "max_total_steps(%s) 초과 — 폭주 방지로 중단",
        "deadlock": "END 미도달 상태로 실행할 노드가 없다 (데드락). 대기 중: %s",
        "none": "없음",
        "not_run": "미실행",
        "ok": "✔ 파이프라인 SUCCEEDED — 산출물: %s",
        "paused": "⏸ 파이프라인 PAUSED — 게이트 '%s' 에서 확인 대기",
        "paused_review": "  선행 산출물 검토: %s/outputs/",
        "paused_resume": "  확인 후 재개: python3 %s %s --resume %s [--var key=확정값 ...]",
        "failed": "✘ 파이프라인 FAILED — %s",
        "resume_hint": "  재개: python3 %s %s --resume %s",
        "timeout": "노드 타임아웃 (%ss 초과)",
        "no_cli": "claude CLI를 찾을 수 없다: %s",
        "internal": "러너 내부 오류: %r",
        "mock_text": "[MOCK] %s iter %d 실행 결과",
        "ctx_header": "---\n## 선행 노드 출력 (컨텍스트)\n\n",
        "ctx_item": "### 선행 노드 `%s` — %s (iter %d)\n전체 출력 파일: %s\n\n%s",
        "ctx_trunc": "\n...(잘림 — 전체는 파일 참조)",
        "protocol": "---\n"
                    "## 실행 프로토콜 (반드시 준수)\n"
                    "너는 그래프 파이프라인 '%s'의 노드 `%s` 이다. (반복 %d회차, run_id=%s)\n"
                    "작업을 끝내면 응답의 **마지막 줄**에 반드시 다음 형식으로 상태를 보고하라:\n\n"
                    "GRAPH_STATUS: SUCCEEDED   (성공)  또는  GRAPH_STATUS: FAILED   (실패)\n\n"
                    "후속 노드의 분기 판정에 필요한 값이 있으면 그 **직전 줄**에 한 줄 JSON 으로:\n\n"
                    "GRAPH_OUTPUT: {\"key\": \"value\"}\n",
        "validated": "검증 통과: 노드 %d개, 엣지 %d개 (%s)",
    },
}


# ---------------------------------------------------------------------------
# 미니 YAML 파서 (PyYAML 폴백)
# ---------------------------------------------------------------------------
class YamlError(Exception):
    pass


def _strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in ('"', "'"):
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(tok):
    tok = tok.strip()
    if tok == "":
        return None
    if tok[0] in ('"', "'") and len(tok) >= 2 and tok[-1] == tok[0]:
        return tok[1:-1]
    low = tok.lower()
    # yes/no 는 불리언으로 강제하지 않는다 (YAML 1.2 방식) — OUTPUT 비교값·케이스
    # 키가 문자열로 유지돼야 에이전트가 보고한 "yes" 와 어긋나지 않는다
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _flow(s):
    s = s.strip()

    def skip_ws(i):
        while i < len(s) and s[i] in " \t":
            i += 1
        return i

    def parse(i):
        i = skip_ws(i)
        if i >= len(s):
            raise YamlError("flow 표현식이 잘리다: %r" % s)
        if s[i] == "[":
            arr, i = [], i + 1
            while True:
                i = skip_ws(i)
                if i >= len(s):
                    raise YamlError("']' 누락: %r" % s)
                if s[i] == "]":
                    return arr, i + 1
                v, i = parse(i)
                arr.append(v)
                i = skip_ws(i)
                if i < len(s) and s[i] == ",":
                    i += 1
                elif i < len(s) and s[i] == "]":
                    return arr, i + 1
        if s[i] == "{":
            d, i = {}, i + 1
            while True:
                i = skip_ws(i)
                if i >= len(s):
                    raise YamlError("'}' 누락: %r" % s)
                if s[i] == "}":
                    return d, i + 1
                j = s.index(":", i)
                key = _scalar(s[i:j])
                v, i = parse(j + 1)
                d[key] = v
                i = skip_ws(i)
                if i < len(s) and s[i] == ",":
                    i += 1
                elif i < len(s) and s[i] == "}":
                    return d, i + 1
        if s[i] in ('"', "'"):
            q = s[i]
            j = s.index(q, i + 1)
            return s[i + 1 : j], j + 1
        j = i
        while j < len(s) and s[j] not in ",]}":
            j += 1
        return _scalar(s[i:j]), j

    v, _ = parse(0)
    return v


def _value(tok):
    tok = tok.strip()
    if tok[:1] in ("[", "{"):
        return _flow(tok)
    return _scalar(tok)


_MAP_START_RE = re.compile(r"^[^:{\[\s][^:]*:(\s|$)")


class _Mini:
    """pipeline.yml 스키마에 필요한 YAML 부분집합 파서.

    지원: 블록 매핑/시퀀스, flow([], {}), 스칼라, 주석, 리터럴 블록(|, |-).
    미지원: 앵커/앨리어스, 멀티 도큐먼트, folded(>) — 필요하면 PyYAML 설치.
    """

    def __init__(self, text):
        self.raw = text.split("\n")
        self.toks = []  # (raw_idx, indent, stripped_content)
        for idx, raw in enumerate(self.raw):
            line = _strip_comment(raw.rstrip())
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            if "\t" in line[: indent + 1]:
                raise YamlError("탭 들여쓰기는 지원하지 않는다 (line %d)" % (idx + 1))
            self.toks.append((idx, indent, line.strip()))

    def parse(self):
        if not self.toks:
            return {}
        val, _ = self._block(0, len(self.toks), self.toks[0][1])
        return val

    def _block(self, i, end, indent):
        txt = self.toks[i][2]
        if txt == "-" or txt.startswith("- "):
            return self._seq(i, end, indent)
        return self._map(i, end, indent)

    def _map(self, i, end, indent):
        d = {}
        while i < end:
            idx, ind, txt = self.toks[i]
            if ind < indent:
                break
            if ind > indent:
                raise YamlError("들여쓰기 오류 (line %d): %r" % (idx + 1, txt))
            if ":" not in txt:
                raise YamlError("매핑이 아니다 (line %d): %r" % (idx + 1, txt))
            key_part, rest = txt.split(":", 1)
            if rest and not rest.startswith(" "):
                raise YamlError("'key: value' 형식이 아니다 (line %d): %r" % (idx + 1, txt))
            key = _scalar(key_part)
            rest = rest.strip()
            j = i + 1
            while j < end and self.toks[j][1] > ind:
                j += 1
            if rest == "":
                if j == i + 1:
                    d[key] = None
                else:
                    d[key], _ = self._block(i + 1, j, self.toks[i + 1][1])
                i = j
            elif rest in ("|", "|-"):
                d[key] = self._literal(idx, ind, keep_nl=(rest == "|"))
                i = j
            else:
                if j != i + 1:
                    raise YamlError(
                        "스칼라 값 아래에 들여쓰인 줄이 있다 (line %d): %r" % (idx + 1, txt)
                    )
                d[key] = _value(rest)
                i += 1
        return d, i

    def _seq(self, i, end, indent):
        arr = []
        while i < end:
            idx, ind, txt = self.toks[i]
            if ind != indent or not (txt == "-" or txt.startswith("- ")):
                break
            rest = txt[1:].strip()
            j = i + 1
            while j < end and self.toks[j][1] > ind:
                j += 1
            if rest == "":
                if j == i + 1:
                    arr.append(None)
                else:
                    v, _ = self._block(i + 1, j, self.toks[i + 1][1])
                    arr.append(v)
            elif _MAP_START_RE.match(rest):
                rest_col = ind + (len(txt) - len(rest))
                sub = _Mini.__new__(_Mini)
                sub.raw = self.raw
                sub.toks = [(idx, rest_col, rest)] + self.toks[i + 1 : j]
                v, _ = sub._map(0, len(sub.toks), rest_col)
                arr.append(v)
            else:
                if j != i + 1:
                    raise YamlError("시퀀스 항목 파싱 오류 (line %d)" % (idx + 1))
                arr.append(_value(rest))
            i = j
        return arr, i

    def _literal(self, idx, ind, keep_nl):
        out, base = [], None
        k = idx + 1
        while k < len(self.raw):
            raw = self.raw[k].rstrip("\n")
            if raw.strip() == "":
                out.append("")
                k += 1
                continue
            rind = len(raw) - len(raw.lstrip(" "))
            if rind <= ind:
                break
            if base is None:
                base = rind
            out.append(raw[base:] if rind >= base else raw.lstrip())
            k += 1
        while out and out[-1] == "":
            out.pop()
        text = "\n".join(out)
        return text + ("\n" if keep_nl else "")


def load_yaml(text):
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _Mini(text).parse()


# ---------------------------------------------------------------------------
# 파이프라인 모델 + 검증
# ---------------------------------------------------------------------------
class PipelineError(Exception):
    pass


DEFAULT_SETTINGS = {
    "mode": "runner",  # runner | session — 기본 실행 모드 선언 (session 은 Claude 가 해석)
    "lang": "en",  # en | ko — 실행 로그·프롬프트 주입 문구 언어
    "parallelism": 4,
    "state_dir": ".graph-runs",
    "node_timeout": 3600,
    "max_total_steps": 100,
    "context_max_chars": 8000,
    "claude_args": [],
    "model": None,
    "claude_bin": None,
}
VALID_STATUS = ("SUCCEEDED", "FAILED")


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


_EXPR_RE = re.compile(r"^([\w.-]+)\s*(==|!=)\s*(.+)$")
_EXPR_IN_RE = re.compile(r"^([\w.-]+)\s+in\s+(.+)$")


def _expr_operand(raw):
    """표현식 비교값은 타입 강제 없이 문자열 원문으로 다룬다 (따옴표만 제거)."""
    s = raw.strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        return s[1:-1]
    return s


def _normalize_when(when):
    """when 정규화. 생략 시 STATUS==SUCCEEDED.

    문자열 축약형: SUCCEEDED | FAILED | ALWAYS
    표현식(GRAPH_OUTPUT 비교): "route == heavy" | "route != heavy" | "route in [a, b]"
    """
    if when is None:
        return [{"type": "STATUS", "status": "SUCCEEDED"}]
    conds = []
    for c in _as_list(when):
        if isinstance(c, str):
            s = c.strip()
            u = s.upper()
            if u == "ALWAYS":
                conds.append({"type": "ALWAYS"})
            elif u in VALID_STATUS:
                conds.append({"type": "STATUS", "status": u})
            elif _EXPR_RE.match(s):
                key, op, raw = _EXPR_RE.match(s).groups()
                field = "equals" if op == "==" else "not_equals"
                conds.append({"type": "OUTPUT", "key": key, field: _expr_operand(raw)})
            elif _EXPR_IN_RE.match(s):
                key, raw = _EXPR_IN_RE.match(s).groups()
                r = raw.strip()
                if r.startswith("[") and r.endswith("]"):
                    vals = [_expr_operand(x) for x in r[1:-1].split(",") if x.strip()]
                else:
                    vals = [_expr_operand(r)]
                conds.append({"type": "OUTPUT", "key": key, "in": vals})
            else:
                raise PipelineError("알 수 없는 when 표현식: %r" % c)
        elif isinstance(c, dict):
            c = dict(c)
            c["type"] = str(c.get("type", "STATUS")).upper()
            if c["type"] == "STATUS":
                c["status"] = str(c.get("status", "SUCCEEDED")).upper()
            conds.append(c)
        else:
            raise PipelineError("when 조건 형식 오류: %r" % c)
    return conds


def _sugar_get(d, key):
    """PyYAML 이 'on' 을 불리언 True 키로 파싱하는 문제를 흡수한다."""
    if key == "on":
        return d.get("on", d.get(True))
    return d.get(key)


def _seq_node_ids(steps):
    """workflow 스텝 트리에 등장하는 실행 노드 id 를 순서대로 수집 (터미널 제외)."""
    ids = []
    for step in _as_list(steps):
        if isinstance(step, str):
            if step.strip() not in (END, FAIL):
                ids.append(step.strip())
        elif isinstance(step, dict) and len(step) == 1:
            kind, spec = next(iter(step.items()))
            if kind == "parallel":
                for br in _as_list(spec):
                    ids += _seq_node_ids(br if isinstance(br, list) else [br])
            elif kind == "loop":
                ids += _seq_node_ids((spec or {}).get("body"))
            elif kind == "branch":
                for cseq in ((spec or {}).get("cases") or {}).values():
                    ids += _seq_node_ids(cseq if isinstance(cseq, list) else [cseq])
    return ids


def _exhausted_value(spec):
    exh = spec.get("exhausted", "FAIL")
    if isinstance(exh, (list, dict)):
        raise PipelineError(
            "exhausted 는 FAIL 또는 노드 id 하나다 — 노드는 실행 후 "
            "(후속 엣지가 없으면) 자동으로 실패 종결된다: %r" % exh
        )
    return str(exh)


def compile_workflow(wf, mark_join_any, mark_fail_after):
    """중첩 workflow 블록을 edges 목록으로 컴파일한다.

    스텝 종류:
      - "노드id" | "END" | "FAIL"          순차 실행 / 터미널
      - parallel: [a, b, [c1, c2]]         Fan-Out (항목 = 노드 | 시퀀스 | 블록),
                                           다음 스텝이 Fan-In(join: all)
      - loop: {body: [...], max: N,        피드백 루프. body 안 redo 이후 노드가
              redo: 노드|리스트,            FAILED 면 redo 로 재작업. redo 생략 시
              exhausted: FAIL|노드id}       body 첫 노드. 소진 시: FAIL=즉시 실패,
                                           노드id=그 노드 실행(보고 등) 후 자동 실패 종결
      - branch: {on: 출력키, cases: {...}}  조건 분기. on 생략 시 케이스 키는
                                           SUCCEEDED|FAILED|ALWAYS (STATUS 분기).
                                           케이스 값 = 노드 | 시퀀스. 분기 다음
                                           스텝은 자동으로 join: any (합류점)
      - if: <조건> / goto: <대상>           직전 노드의 상태·출력 체크 후 점프.
                                           조건: FAILED | route == heavy 등.
                                           위(이미 나온 노드)로 goto = 피드백 루프
                                           (max 기본 3, exhausted 지정 가능),
                                           아래/측면/END/FAIL 로 goto = 조건 분기.
                                           if 생략 = 무조건 점프(시퀀스 종료)

    START/END 는 자동 연결된다 (첫 스텝 앞 START, 마지막 exits 뒤 END).
    """
    edges = []
    placed = set()  # 지금까지 배치된 노드 — goto 의 루프(뒤로)/분기(앞으로) 판정

    def connect(srcs, dsts, when=None, loop=None):
        for s in srcs:
            for d in dsts:
                e = {"from": s, "to": d}
                if when is not None:
                    e["when"] = when
                if loop is not None:
                    e["loop"] = dict(loop)
                edges.append(e)

    def compile_step(step, merge_point):
        """단일 스텝 → (entries, exits). merge_point 면 진입 노드를 join: any 로."""
        if isinstance(step, str):
            s = step.strip()
            if s in (END, FAIL):
                return [s], []
            if merge_point:
                mark_join_any(s)
            placed.add(s)
            return [s], [s]
        if not isinstance(step, dict) or len(step) != 1:
            raise PipelineError("workflow 스텝 형식 오류: %r" % step)
        kind, spec = next(iter(step.items()))
        if kind == "parallel":
            entries, exits = [], []
            for br in _as_list(spec):
                en, ex = compile_seq(br if isinstance(br, list) else [br], None, merge_point)
                entries += en
                exits += ex
            if not entries:
                raise PipelineError("parallel 블록이 비어 있다")
            return entries, exits
        if kind == "loop":
            spec = spec or {}
            body = spec.get("body") or []
            if not body:
                raise PipelineError("loop 블록에는 body 가 필요하다")
            en, ex = compile_seq(body, None, merge_point)
            redo = [str(r) for r in _as_list(spec.get("redo"))] or list(en)
            loop_cfg = {
                "max": int(spec.get("max", 3)),
                "on_exhausted": _exhausted_value(spec),
            }
            body_ids = _seq_node_ids(body)
            missing = [r for r in redo if r not in body_ids]
            if missing:
                raise PipelineError("loop redo 대상이 body 에 없다: %s" % ", ".join(missing))
            # redo 대상이 속한 스텝 '이후' 스텝의 노드들이 FAILED 면 redo 로 피드백
            redo_step = 0
            for i, st in enumerate(body):
                if set(redo) & set(_seq_node_ids([st])):
                    redo_step = i
                    break
            fb_srcs = _seq_node_ids(body[redo_step + 1 :])
            for s in fb_srcs:
                connect([s], redo, when="FAILED", loop=loop_cfg)
            return en, ex
        if kind == "branch":
            raise PipelineError("branch 는 선행 노드가 필요하다 — 시퀀스 안에서만 쓸 수 있다")
        raise PipelineError("알 수 없는 workflow 블록: %r" % kind)

    def compile_seq(steps, prev_exits, merge_first):
        """스텝 시퀀스 → (첫 스텝 entries, 마지막 exits). prev_exits 와 자동 연결."""
        first_entries = None
        merge_next = merge_first
        pending_neg = []  # if/goto(OUTPUT 조건)의 부정 — 다음 스텝 엣지에 주입해 배타 보장

        def apply_goto(src, spec):
            """src 노드에 라우팅 규칙 1개 적용. 순차 흐름 유지 여부를 반환."""
            cond = spec.get("if", "ALWAYS")
            targets = [str(t) for t in _as_list(spec["goto"])]
            if FAIL in targets and len(targets) > 1:
                # 노드와 FAIL 이 함께 오면 "노드 수행 후 실패 종결" 의도다 —
                # FAIL 엣지를 동시에 걸면 노드 활성화가 선점당하므로 분리한다
                targets = [t for t in targets if t != FAIL]
                for t in targets:
                    mark_fail_after(t)
            backward = any(t in placed for t in targets)
            loop_cfg = None
            if backward or "max" in spec:
                loop_cfg = {
                    "max": int(spec.get("max", 3)),
                    "on_exhausted": _exhausted_value(spec),
                }
            else:
                for t in targets:  # 앞으로 점프 = 분기 합류 가능성 → join: any
                    if t not in (END, FAIL):
                        mark_join_any(t)
            connect([src], targets, when=cond, loop=loop_cfg)
            if "if" not in spec:
                return False  # 무조건 점프 — 순차 흐름은 여기서 끊긴다
            for c in _normalize_when(cond):
                if c["type"] == "OUTPUT" and "equals" in c:
                    pending_neg.append(
                        {"type": "OUTPUT", "key": c["key"], "not_equals": c["equals"]}
                    )
                elif c["type"] == "OUTPUT" and "not_equals" in c:
                    pending_neg.append(
                        {"type": "OUTPUT", "key": c["key"], "equals": c["not_equals"]}
                    )
                # STATUS FAILED 는 기본 성공 엣지와 이미 배타, in 은 자동 배타 미지원
            return True

        for step in _as_list(steps):
            # 노드 부착 라우팅: - test: {if: FAILED, goto: ...} (규칙 리스트 허용)
            routes = None
            if isinstance(step, dict) and len(step) == 1:
                k0, v0 = next(iter(step.items()))
                if k0 not in ("parallel", "loop", "branch"):
                    if isinstance(v0, dict) and "goto" in v0:
                        routes = [v0]
                    elif (
                        isinstance(v0, list)
                        and v0
                        and all(isinstance(r, dict) and "goto" in r for r in v0)
                    ):
                        routes = v0
                    if routes is not None:
                        step = str(k0)
            if isinstance(step, dict) and "goto" in step:
                # (호환) 형제 스텝 형태: - if: ... / goto: ... — 직전 노드에 적용
                if not prev_exits or len(prev_exits) != 1 or prev_exits[0] == START:
                    raise PipelineError("if/goto 는 단일 선행 노드 바로 뒤에만 올 수 있다")
                if not apply_goto(prev_exits[0], step):
                    prev_exits = []
                continue
            if isinstance(step, dict) and len(step) == 1 and next(iter(step)) == "branch":
                spec = step["branch"] or {}
                if not prev_exits or len(prev_exits) != 1 or prev_exits[0] == START:
                    raise PipelineError("branch 는 단일 선행 노드 바로 뒤에만 올 수 있다")
                src = prev_exits[0]
                key = _sugar_get(spec, "on")
                cases = spec.get("cases") or {}
                if not cases:
                    raise PipelineError("branch 블록에는 cases 가 필요하다")
                exits = []
                for ck, cseq in cases.items():
                    if key is not None:
                        when = [{"type": "OUTPUT", "key": str(key), "equals": ck}]
                    else:
                        u = str(ck).upper()
                        if u == "ALWAYS":
                            when = [{"type": "ALWAYS"}]
                        elif u in VALID_STATUS:
                            when = [{"type": "STATUS", "status": u}]
                        else:
                            raise PipelineError(
                                "branch(on 없음) 케이스 키는 SUCCEEDED|FAILED|ALWAYS: %r" % ck
                            )
                    en, ex = compile_seq(cseq if isinstance(cseq, list) else [cseq], None, False)
                    connect([src], en, when=when)
                    exits += ex
                prev_exits = exits
                merge_next = True  # 분기 합류점은 한 케이스만 도착 — join: any
                continue
            en, ex = compile_step(step, merge_next)
            if first_entries is None:
                first_entries = en
            if prev_exits:
                connect(prev_exits, en, when=(["SUCCEEDED"] + pending_neg) if pending_neg else None)
            pending_neg = []
            prev_exits = ex
            merge_next = False
            if routes:
                for r in routes:
                    if not apply_goto(ex[0], r):
                        prev_exits = []
        return first_entries or [], prev_exits or []

    _, final_exits = compile_seq(wf, [START], False)
    if final_exits:
        connect(final_exits, [END])
    return edges


class Pipeline:
    def __init__(self, doc, yml_path):
        if not isinstance(doc, dict):
            raise PipelineError("pipeline.yml 최상위는 매핑이어야 한다")
        self.yml_path = Path(yml_path)
        self.name = doc.get("name") or self.yml_path.stem
        self.kind = doc.get("kind", "workflow")
        self.vars = doc.get("vars") or {}
        self.settings = dict(DEFAULT_SETTINGS)
        for k, v in (doc.get("settings") or {}).items():
            self.settings[k] = v
        if isinstance(self.settings["claude_args"], str):
            self.settings["claude_args"] = shlex.split(self.settings["claude_args"])

        self.nodes = {}
        explicit_join = set()
        for nd in doc.get("nodes") or []:
            if not isinstance(nd, dict) or not nd.get("id"):
                raise PipelineError("노드에는 id가 필요하다: %r" % nd)
            nid = str(nd["id"])
            if nid in (START, END, FAIL):
                raise PipelineError("노드 id로 %s 는 예약어다" % nid)
            if nid in self.nodes:
                raise PipelineError("노드 id 중복: %s" % nid)
            if "join" in nd:
                explicit_join.add(nid)
            self.nodes[nid] = {
                "id": nid,
                "type": str(nd.get("type", "agent")).lower(),  # agent | command
                "run": nd.get("run"),          # type: command 의 셸 명령
                "timeout": nd.get("timeout"),  # 노드별 타임아웃(초) — 생략 시 settings
                "gate": bool(nd.get("gate")),  # 게이트: 도달 시 일시정지, resume 으로 통과
                "prompt": nd.get("prompt"),
                "model": nd.get("model") or self.settings["model"],
                "agent": nd.get("agent"),  # claude --agent (프로젝트 .claude/agents 정의)
                "join": str(nd.get("join", "all")).lower(),
                "retry": int(nd.get("retry", 0)),
                "allowed_tools": nd.get("allowed_tools"),
                "append_prompt": nd.get("append_prompt"),
                "context": [str(c) for c in _as_list(nd.get("context"))],
            }

        # workflow(중첩 DSL) → edges 컴파일. 분기 합류점은 join: any 로 (명시 설정 우선)
        auto_any = set()
        fail_after = set()
        raw_edges = []
        if doc.get("workflow"):
            raw_edges += compile_workflow(doc["workflow"], auto_any.add, fail_after.add)
        self.fail_after = fail_after
        raw_edges += doc.get("edges") or []
        for nid in auto_any:
            if nid in self.nodes and nid not in explicit_join:
                self.nodes[nid]["join"] = "any"

        self.edges = []
        seen_sig = set()  # 완전 동일 엣지 중복 제거 (loop 중복은 카운터가 2배가 되므로 실해악)
        for i, ed in enumerate(raw_edges):
            if not isinstance(ed, dict):
                raise PipelineError("엣지 형식 오류: %r" % ed)
            srcs = [str(s) for s in _as_list(ed.get("from"))]
            dsts = [str(t) for t in _as_list(ed.get("to"))]
            if not srcs or not dsts:
                raise PipelineError("엣지에는 from/to 가 필요하다: %r" % ed)
            when = _normalize_when(ed.get("when"))
            loop = ed.get("loop")
            if loop is not None:
                if not isinstance(loop, dict) or int(loop.get("max", 0)) < 1:
                    raise PipelineError("loop 에는 max(>=1)가 필요하다: %r" % ed)
                loop = {
                    "max": int(loop["max"]),
                    "on_exhausted": str(loop.get("on_exhausted", "FAIL")),
                }
            for s in srcs:
                for t in dsts:
                    sig = json.dumps([s, t, when, loop], ensure_ascii=False, sort_keys=True)
                    if sig in seen_sig:
                        continue
                    seen_sig.add(sig)
                    self.edges.append(
                        {
                            "key": "%s->%s#%d" % (s, t, i),
                            "src": s,
                            "dst": t,
                            "when": when,
                            "loop": loop,
                        }
                    )

        self.out_edges = {}
        self.in_edges = {}
        for e in self.edges:
            self.out_edges.setdefault(e["src"], []).append(e)
            self.in_edges.setdefault(e["dst"], []).append(e)

    # -- 프롬프트 경로: 실행 위치(cwd) 기준, 없으면 yml 위치 기준 폴백 --
    def resolve_prompt(self, rel):
        p = Path(rel)
        if p.is_file():
            return p
        alt = self.yml_path.parent / rel
        if alt.is_file():
            return alt
        return None

    def validate(self):
        errors, warnings = [], []
        ids = set(self.nodes) | {START, END, FAIL}
        for e in self.edges:
            if e["src"] not in ids or e["src"] in (END, FAIL):
                errors.append("엣지 %s: 잘못된 from '%s'" % (e["key"], e["src"]))
            if e["dst"] not in ids or e["dst"] == START:
                errors.append("엣지 %s: 잘못된 to '%s'" % (e["key"], e["dst"]))
            for c in e["when"]:
                t = c.get("type")
                if t == "STATUS":
                    if c.get("status") not in VALID_STATUS:
                        errors.append("엣지 %s: status 는 SUCCEEDED|FAILED" % e["key"])
                elif t == "OUTPUT":
                    if not c.get("key"):
                        errors.append("엣지 %s: OUTPUT 조건에 key 필요" % e["key"])
                    if not any(k in c for k in ("equals", "not_equals", "in")):
                        errors.append(
                            "엣지 %s: OUTPUT 조건에 equals|not_equals|in 필요" % e["key"]
                        )
                elif t != "ALWAYS":
                    errors.append("엣지 %s: 알 수 없는 조건 type %r" % (e["key"], t))
            if e["loop"] and e["loop"]["on_exhausted"] not in ("FAIL",) and e["loop"][
                "on_exhausted"
            ] not in self.nodes:
                errors.append(
                    "엣지 %s: on_exhausted 는 FAIL 또는 노드 id" % e["key"]
                )
        if str(self.settings["lang"]) not in MESSAGES:
            errors.append("settings.lang 는 %s (현재: %r)" % ("|".join(sorted(MESSAGES)), self.settings["lang"]))
        if str(self.settings["mode"]) not in ("runner", "session"):
            errors.append("settings.mode 는 runner | session (현재: %r)" % self.settings["mode"])
        if not self.nodes:
            errors.append("노드가 없다")
        for nid, nd in self.nodes.items():
            if nd["join"] not in ("all", "any"):
                errors.append("노드 %s: join 은 all|any" % nid)
            if nd["gate"]:
                continue  # 게이트 노드는 prompt 불필요
            if nd["type"] not in ("agent", "command"):
                errors.append("노드 %s: type 은 agent | command" % nid)
                continue
            if nd["type"] == "command":
                # 신뢰 경계: run 은 러너가 그대로 실행한다 — yml 은 코드와 동일한 리뷰 대상
                if not nd["run"]:
                    errors.append("노드 %s: type: command 에는 run 이 필요하다" % nid)
                if nd["prompt"]:
                    errors.append("노드 %s: type: command 는 prompt 대신 run 을 쓴다" % nid)
                continue
            if not nd["prompt"]:
                errors.append("노드 %s: prompt 가 필요하다" % nid)
            elif self.resolve_prompt(nd["prompt"]) is None:
                errors.append(
                    "노드 %s: 프롬프트 파일을 찾을 수 없다 — %s (cwd 및 yml 위치 기준)"
                    % (nid, nd["prompt"])
                )
        if not self.out_edges.get(START):
            errors.append("START 에서 나가는 엣지가 없다")

        # 도달성: START 에서 모든 노드/END 도달 확인
        seen = set()
        stack = [START]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for e in self.out_edges.get(cur, []):
                stack.append(e["dst"])
                if e["loop"] and e["loop"]["on_exhausted"] != "FAIL":
                    stack.append(e["loop"]["on_exhausted"])
        for nid in self.nodes:
            if nid not in seen:
                errors.append("노드 %s: START 에서 도달 불가" % nid)
        if END not in seen:
            errors.append("END 에 도달하는 경로가 없다")

        # 사이클 검증: loop 없는 엣지만으로는 DAG 여야 한다
        indeg = {n: 0 for n in list(self.nodes) + [START, END, FAIL]}
        plain = [e for e in self.edges if not e["loop"]]
        for e in plain:
            if e["dst"] in indeg:
                indeg[e["dst"]] += 1
        queue = [n for n, d in indeg.items() if d == 0]
        visited = 0
        while queue:
            cur = queue.pop()
            visited += 1
            for e in plain:
                if e["src"] == cur:
                    indeg[e["dst"]] -= 1
                    if indeg[e["dst"]] == 0:
                        queue.append(e["dst"])
        if visited < len(indeg):
            stuck = [n for n, d in indeg.items() if d > 0]
            errors.append(
                "loop 설정 없는 사이클 발견: %s — 피드백 엣지에는 loop: {max: N} 을 붙여라"
                % ", ".join(sorted(stuck))
            )
        return errors, warnings


# ---------------------------------------------------------------------------
# 조건 평가
# ---------------------------------------------------------------------------
def eval_when(conds, status, outputs):
    for c in conds:
        t = c["type"]
        if t == "ALWAYS":
            continue
        if t == "STATUS":
            if status != c["status"]:
                return False
        elif t == "OUTPUT":
            val = outputs.get(c["key"])
            sval = None if val is None else str(val)
            if "equals" in c and sval != str(c["equals"]):
                return False
            if "not_equals" in c and sval == str(c["not_equals"]):
                return False
            if "in" in c and sval not in [str(x) for x in _as_list(c["in"])]:
                return False
    return True


# ---------------------------------------------------------------------------
# 오케스트레이션 엔진
# ---------------------------------------------------------------------------
class Runner:
    def __init__(self, pipe, args):
        self.pipe = pipe
        self.args = args
        self.msg = MESSAGES.get(str(pipe.settings.get("lang", "en")), MESSAGES["en"])
        self.mock = args.mock
        self.mock_plan = {}
        for spec in args.mock_status or []:
            if "=" not in spec:
                raise PipelineError("--mock-status 형식: node=STATUS[,STATUS...]")
            nid, seq = spec.split("=", 1)
            self.mock_plan[nid.strip()] = [s.strip().upper() for s in seq.split(",")]
        self.mock_outputs = {}
        for spec in getattr(args, "mock_output", None) or []:
            if "=" not in spec:
                raise PipelineError("--mock-output 형식: node={\"key\": \"value\"}")
            nid, payload = spec.split("=", 1)
            self.mock_outputs[nid.strip()] = json.loads(payload)
        self.run_id = args.resume or (
            time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        )
        self.run_dir = Path(pipe.settings["state_dir"]) / self.run_id
        self.prev_nodes = {}
        if args.resume:
            sf = self.run_dir / "state.json"
            if not sf.is_file():
                raise PipelineError("재개할 상태 파일이 없다: %s" % sf)
            self.prev_nodes = json.loads(sf.read_text()).get("nodes", {})
        (self.run_dir / "prompts").mkdir(parents=True, exist_ok=True)
        (self.run_dir / "outputs").mkdir(parents=True, exist_ok=True)

        self.results = {}  # node -> {status, outputs, text, output_file, iteration}
        self.edge_fired = {}  # edge key -> count (loop 엣지)
        self.arrived = {n: set() for n in pipe.nodes}
        # sticky: 한 번 충족된 선행 조건은 유지 — 피드백 루프에서 실패 경로만
        # 재실행돼도 Fan-In(join: all) 노드가 재트리거될 수 있다
        self.ever_arrived = {n: set() for n in pipe.nodes}
        self.required = {
            n: {e["key"] for e in pipe.in_edges.get(n, []) if not e["loop"]}
            for n in pipe.nodes
        }
        self.iteration = {n: 0 for n in pipe.nodes}
        self.live = set()  # resume 시 캐시를 쓰면 안 되는(재실행 필요) 노드
        self.futures = {}
        self.end_reached = False
        self.paused_at = None  # 게이트 일시정지
        self.exhaust_nodes = set()  # on_exhausted 로 위임된 노드 — 완료 후 자동 실패 종결
        self.fail_reason = None
        self.steps = 0
        self.lock = threading.Lock()
        self.pool = None

    # ---- 로그 (콘솔 + <run_dir>/run.log 자동 기록 — 리다이렉트 불필요) ----
    def log(self, msg):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        try:
            with (self.run_dir / "run.log").open("a") as f:
                f.write(line + "\n")
        except OSError:
            pass  # 로그 파일 실패가 실행을 막아선 안 된다

    # ---- 상태 저장 ----
    def save_state(self, result="RUNNING"):
        state = {
            "run_id": self.run_id,
            "pipeline": self.pipe.name,
            "result": result,
            "steps": self.steps,
            "fail_reason": self.fail_reason,
            "nodes": {
                n: {
                    "status": r["status"],
                    "iteration": r["iteration"],
                    "outputs": r["outputs"],
                    "output_file": r["output_file"],
                }
                for n, r in self.results.items()
            },
            "edges": self.edge_fired,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        (self.run_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=2)
        )

    # ---- 메인 루프 ----
    def run(self):
        self.log(self.msg["start"]
                 % (self.pipe.name, self.run_id, self.msg["mock"] if self.mock else ""))
        if str(self.pipe.settings["mode"]) == "session":
            self.log(self.msg["session_note"])
        self.pool = ThreadPoolExecutor(max_workers=int(self.pipe.settings["parallelism"]))
        try:
            self._on_complete(START, "SUCCEEDED", {}, "")
            while self.futures:
                done, _ = wait(list(self.futures), return_when=FIRST_COMPLETED)
                for f in done:
                    node = self.futures.pop(f)
                    status, outputs, text = f.result()
                    self._on_complete(node, status, outputs, text)
        finally:
            self.pool.shutdown(wait=True)

        if self.end_reached and not self.fail_reason:
            result = "SUCCEEDED"
        elif self.paused_at and not self.fail_reason:
            result = "PAUSED"
        else:
            if not self.fail_reason:
                waiting = {
                    n: sorted(self.required[n] - self.ever_arrived[n])
                    for n in self.pipe.nodes
                    if self.ever_arrived[n] and self.required[n] - self.ever_arrived[n]
                }
                self.fail_reason = self.msg["deadlock"] % (
                    json.dumps(waiting, ensure_ascii=False) if waiting else self.msg["none"]
                )
            result = "FAILED"
        self.save_state(result)
        self.log("─" * 60)
        for n in self.pipe.nodes:
            r = self.results.get(n)
            self.log(
                "  %-28s %s"
                % (n, "%s (iter %d)" % (r["status"], r["iteration"]) if r else self.msg["not_run"])
            )
        self.log("─" * 60)
        if result == "SUCCEEDED":
            self.log(self.msg["ok"] % self.run_dir)
        elif result == "PAUSED":
            self.log(self.msg["paused"] % self.paused_at)
            self.log(self.msg["paused_review"] % self.run_dir)
            self.log(self.msg["paused_resume"] % (sys.argv[0], self.pipe.yml_path, self.run_id))
        else:
            self.log(self.msg["failed"] % self.fail_reason)
            self.log(self.msg["resume_hint"] % (sys.argv[0], self.pipe.yml_path, self.run_id))
        return result

    # ---- 완료 처리 (메인 스레드 전용) ----
    def _on_complete(self, node, status, outputs, text):
        if node != START:
            self.log(self.msg["node_end"]
                     % ("✔" if status == "SUCCEEDED" else "✘", node, status,
                        self.iteration[node]))
            self.save_state()
        if self.fail_reason:
            return
        matched = False
        for e in self.pipe.out_edges.get(node, []):
            if not eval_when(e["when"], status, outputs):
                continue
            matched = True
            if e["loop"]:
                fired = self.edge_fired.get(e["key"], 0) + 1
                self.edge_fired[e["key"]] = fired
                if fired > e["loop"]["max"]:
                    on_ex = e["loop"]["on_exhausted"]
                    if on_ex == "FAIL":
                        self.fail_reason = self.msg["loop_out"] % (e["key"], e["loop"]["max"])
                        return
                    self.log(self.msg["delegate"] % (e["key"], on_ex))
                    self.live.add(on_ex)
                    self.exhaust_nodes.add(on_ex)
                    self._activate(on_ex)
                    continue
                self.log(self.msg["feedback"]
                         % (e["src"], e["dst"], fired, e["loop"]["max"]))
            self._deliver(e)
        if not matched and node != START:
            if node in self.exhaust_nodes:
                # 소진 처리 노드는 보고 후 파이프라인을 실패로 종결하는 것이 계약
                self.fail_reason = self.msg["exhaust_done"] % node
            elif node in self.pipe.fail_after:
                self.fail_reason = self.msg["fail_after"] % node
            elif status == "FAILED":
                self.fail_reason = self.msg["fail_no_edge"] % node
            else:
                self.log(self.msg["dead_end"] % node)
        self._schedule()

    def _deliver(self, e):
        """엣지 발화를 기록만 한다. 활성화 판단은 _schedule 이 일괄 수행."""
        if self.fail_reason or self.end_reached or self.paused_at:
            return
        dst = e["dst"]
        if dst == END:
            self.end_reached = True
            self.log(self.msg["end"])
            return
        if dst == FAIL:
            self.fail_reason = self.msg["fail_route"] % (e["src"], e["key"])
            return
        if e["src"] in self.live or e["loop"]:
            self.live.add(dst)
        self.arrived[dst].add(e["key"])
        self.ever_arrived[dst].add(e["key"])

    def _is_active(self, node):
        """실행 중이거나, 새 도착이 있어 곧 실행될 노드 — Fan-In 이 기다려야 한다."""
        return node in self.futures.values() or bool(self.arrived.get(node))

    def _schedule(self):
        """새 도착(arrived)이 있는 노드 중 준비된 것을 활성화한다.

        join=all 은 (sticky 포함) 전체 선행 조건 충족에 더해, 비-루프 업스트림이
        아직 활동 중이면 대기한다 — 피드백 웨이브에서 업스트림 일부만 끝난
        시점에 조기 재실행되는 것을 막는다.
        """
        if self.fail_reason or self.end_reached or self.paused_at:
            return
        progressed = True
        while (
            progressed
            and not self.fail_reason
            and not self.end_reached
            and not self.paused_at
        ):
            progressed = False
            for dst in list(self.pipe.nodes):
                if not self.arrived[dst] or dst in self.futures.values():
                    continue
                join = self.pipe.nodes[dst]["join"]
                if join != "any":
                    if not self.required[dst] <= self.ever_arrived[dst]:
                        continue
                    upstream_busy = any(
                        self._is_active(e["src"])
                        for e in self.pipe.in_edges.get(dst, [])
                        if not e["loop"] and e["src"] != START and e["src"] != dst
                    )
                    if upstream_busy:
                        continue
                self._activate(dst)
                progressed = True
                break  # 활성화가 arrived 를 바꾸므로 처음부터 재스캔

    def _activate(self, node):
        self.steps += 1
        if self.steps > int(self.pipe.settings["max_total_steps"]):
            self.fail_reason = self.msg["max_steps"] % self.pipe.settings["max_total_steps"]
            return
        self.arrived[node].clear()
        self.iteration[node] += 1
        it = self.iteration[node]
        # 게이트: 처음 도달하면 일시정지, resume 시(사람/오케스트레이터 확인 후) 통과
        if self.pipe.nodes[node]["gate"]:
            record = {
                "outputs": {},
                "text": "",
                "output_file": None,
                "iteration": it,
            }
            prev = self.prev_nodes.get(node)
            if prev and prev.get("status") in ("PAUSED", "SUCCEEDED") and it == 1:
                self.log(self.msg["gate_pass"] % node)
                self.results[node] = dict(record, status="SUCCEEDED")
                self._on_complete(node, "SUCCEEDED", {}, "")
                return
            self.log(self.msg["gate_pause"] % node)
            self.results[node] = dict(record, status="PAUSED")
            self.paused_at = node
            return
        # resume 캐시: 이전 실행에서 SUCCEEDED 였고 업스트림이 변하지 않았으면 재사용
        prev = self.prev_nodes.get(node)
        if (
            prev
            and not self.mock
            and node not in self.live
            and it == 1
            and prev.get("status") == "SUCCEEDED"
        ):
            self.log(self.msg["cache"] % node)
            text = ""
            of = prev.get("output_file")
            if of and Path(of).is_file():
                text = Path(of).read_text()
            self.results[node] = {
                "status": "SUCCEEDED",
                "outputs": prev.get("outputs") or {},
                "text": text,
                "output_file": of,
                "iteration": it,
            }
            self._on_complete(node, "SUCCEEDED", prev.get("outputs") or {}, text)
            return
        self.live.add(node)
        self.log(self.msg["node_start"] % (node, it))
        fut = self.pool.submit(self._run_node, node, it)
        self.futures[fut] = node

    # ---- 노드 실행 (워커 스레드) ----
    def _run_node(self, node, it):
        try:
            nd = self.pipe.nodes[node]
            is_cmd = nd["type"] == "command"
            prompt = None
            if not is_cmd:
                prompt = self._build_prompt(nd, it)
                pfile = self.run_dir / "prompts" / ("%s.iter%d.prompt.md" % (node, it))
                pfile.write_text(prompt)
            attempts = nd["retry"] + 1
            status, outputs, text = "FAILED", {}, ""
            for attempt in range(1, attempts + 1):
                if self.mock:
                    status, outputs, text = self._exec_mock(node, it)
                elif is_cmd:
                    status, outputs, text = self._exec_command(nd, it)
                else:
                    status, outputs, text = self._exec_claude(nd, prompt)
                if status == "SUCCEEDED" or attempt == attempts:
                    break
                self.log(self.msg["retry"] % (node, attempt, nd["retry"]))
            ofile = self.run_dir / "outputs" / ("%s.iter%d.md" % (node, it))
            ofile.write_text(text)
            with self.lock:
                self.results[node] = {
                    "status": status,
                    "outputs": outputs,
                    "text": text,
                    "output_file": str(ofile),
                    "iteration": it,
                }
            return status, outputs, text
        except Exception as ex:  # 워커에서는 절대 예외를 전파하지 않는다
            text = self.msg["internal"] % ex
            with self.lock:
                self.results[node] = {
                    "status": "FAILED",
                    "outputs": {},
                    "text": text,
                    "output_file": None,
                    "iteration": it,
                }
            return "FAILED", {}, text

    def _substitute(self, text, it, node_id):
        subs = {"run.id": self.run_id, "node.id": node_id, "node.iteration": str(it)}
        for k, v in (self.pipe.vars or {}).items():
            subs["vars.%s" % k] = str(v)
        for k, v in (self.args.var or {}).items():
            subs["vars.%s" % k] = str(v)
        for k, v in subs.items():
            text = text.replace("{{%s}}" % k, v)
        return text

    def _exec_command(self, nd, it):
        """type: command — 셸 명령 실행. exit 0 = SUCCEEDED, GRAPH_OUTPUT 은 stdout 에서 파싱."""
        cmd = self._substitute(str(nd["run"]), it, nd["id"])
        timeout = int(nd["timeout"] or self.pipe.settings["node_timeout"])
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return "FAILED", {}, self.msg["timeout"] % timeout
        text = proc.stdout or ""
        if proc.stderr:
            text += "\n[stderr]\n" + proc.stderr.strip()[-2000:]
        outputs = {}
        for m in OUTPUT_RE.findall(text):
            try:
                parsed = json.loads(m)
                if isinstance(parsed, dict):
                    outputs = parsed
            except json.JSONDecodeError:
                pass
        return ("SUCCEEDED" if proc.returncode == 0 else "FAILED"), outputs, text

    def _exec_mock(self, node, it):
        seq = self.mock_plan.get(node)
        status = seq[min(it - 1, len(seq) - 1)] if seq else "SUCCEEDED"
        outputs = self.mock_outputs.get(node, {})
        text = self.msg["mock_text"] % (node, it) + "\nGRAPH_STATUS: %s" % status
        time.sleep(0.05)
        return status, outputs, text

    def _exec_claude(self, nd, prompt):
        s = self.pipe.settings
        bin_ = s["claude_bin"] or os.environ.get("CLAUDE_BIN", "claude")
        cmd = [bin_, "-p", "--output-format", "json"]
        if nd["agent"]:
            cmd += ["--agent", str(nd["agent"])]
        if nd["model"]:
            cmd += ["--model", str(nd["model"])]
        if nd["allowed_tools"]:
            cmd += ["--allowedTools", str(nd["allowed_tools"])]
        cmd += [str(a) for a in s["claude_args"]]
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=int(nd["timeout"] or s["node_timeout"]),
            )
        except subprocess.TimeoutExpired:
            return "FAILED", {}, self.msg["timeout"] % s["node_timeout"]
        except FileNotFoundError:
            return "FAILED", {}, self.msg["no_cli"] % bin_
        text = proc.stdout
        try:
            data = json.loads(proc.stdout)
            text = data.get("result") or ""
            if data.get("is_error"):
                return "FAILED", {}, text or "claude 세션 오류"
        except (json.JSONDecodeError, AttributeError):
            pass
        if proc.returncode != 0:
            tail = (proc.stderr or "").strip()[-2000:]
            return "FAILED", {}, (text or "") + "\n[stderr]\n" + tail
        status, outputs = self._parse_markers(text)
        return status, outputs, text

    def _parse_markers(self, text):
        statuses = STATUS_RE.findall(text or "")
        outputs = {}
        for m in OUTPUT_RE.findall(text or ""):
            try:
                parsed = json.loads(m)
                if isinstance(parsed, dict):
                    outputs = parsed
            except json.JSONDecodeError:
                pass
        if statuses:
            return statuses[-1].upper(), outputs
        self.log(self.msg["no_marker"])
        return "SUCCEEDED", outputs

    # ---- 프롬프트 조립 ----
    def _build_prompt(self, nd, it):
        path = self.pipe.resolve_prompt(nd["prompt"])
        if path is None:
            raise PipelineError("프롬프트 파일 없음: %s" % nd["prompt"])
        content = self._substitute(path.read_text(), it, nd["id"])

        parts = [content]
        if nd["append_prompt"]:
            parts.append(str(nd["append_prompt"]))

        preds = []
        for e in self.pipe.in_edges.get(nd["id"], []):
            if e["src"] != START and e["src"] not in preds:
                preds.append(e["src"])
        for c in nd["context"]:
            if c not in preds:
                preds.append(c)
        ctx = []
        limit = int(self.pipe.settings["context_max_chars"])
        with self.lock:
            for p in preds:
                r = self.results.get(p)
                if not r:
                    continue
                body = (r["text"] or "").strip()
                if len(body) > limit:
                    body = body[:limit] + self.msg["ctx_trunc"]
                ctx.append(
                    self.msg["ctx_item"]
                    % (p, r["status"], r["iteration"], r["output_file"], body)
                )
        if ctx:
            parts.append(self.msg["ctx_header"] + "\n\n".join(ctx))

        parts.append(self.msg["protocol"] % (self.pipe.name, nd["id"], it, self.run_id))
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 시각화 / 실행 계획
# ---------------------------------------------------------------------------
def _cond_label(e):
    labels = []
    for c in e["when"]:
        if c["type"] == "STATUS" and c["status"] != "SUCCEEDED":
            labels.append(c["status"])
        elif c["type"] == "OUTPUT":
            if "equals" in c:
                labels.append("%s=%s" % (c["key"], c["equals"]))
            elif "in" in c:
                labels.append("%s in %s" % (c["key"], c["in"]))
            else:
                labels.append("%s!=%s" % (c["key"], c.get("not_equals")))
        elif c["type"] == "ALWAYS":
            labels.append("always")
    if e["loop"]:
        labels.append("loop≤%d" % e["loop"]["max"])
    return ", ".join(labels)


def mermaid(pipe):
    safe = {START: "S", END: "E", FAIL: "F"}
    for i, n in enumerate(pipe.nodes):
        safe[n] = "n%d" % i
    # 소진 위임 대상 노드 (실행 후 후속 엣지 없으면 자동 실패 종결)
    exhaust_targets = {
        e["loop"]["on_exhausted"]
        for e in pipe.edges
        if e["loop"] and e["loop"]["on_exhausted"] != "FAIL"
    }
    auto_fail = {t for t in exhaust_targets if not pipe.out_edges.get(t)}
    auto_fail |= {t for t in getattr(pipe, "fail_after", set()) if not pipe.out_edges.get(t)}
    lines = ["flowchart TD", "  S([START])", "  E([END])"]
    if auto_fail or any(e["dst"] == FAIL for e in pipe.edges):
        lines.append("  F([FAIL])")
    for n in pipe.nodes:
        if pipe.nodes[n]["gate"]:
            lines.append('  %s[["%s ⏸"]]' % (safe[n], n))
        elif pipe.nodes[n]["type"] == "command":
            lines.append('  %s{{"%s"}}' % (safe[n], n))
        else:
            lines.append('  %s["%s"]' % (safe[n], n))
    for e in pipe.edges:
        label = _cond_label(e)
        if e["loop"]:
            arrow = ("-. %s .->" % label) if label else "-.->"
        else:
            arrow = ("-->|%s|" % label) if label else "-->"
        lines.append("  %s %s %s" % (safe[e["src"]], arrow, safe[e["dst"]]))
    seen = set()
    for e in pipe.edges:  # 소진 위임 경로 시각화
        if e["loop"] and e["loop"]["on_exhausted"] != "FAIL":
            line = "  %s -. exhausted .-> %s" % (safe[e["src"]], safe[e["loop"]["on_exhausted"]])
            if line not in seen:
                seen.add(line)
                lines.append(line)
    for t in sorted(auto_fail):
        lines.append("  %s -.-> F" % safe[t])
    return "\n".join(lines)


def dry_run(pipe):
    """loop 엣지를 제외한 위상 정렬 wave 를 출력한다."""
    plain = [e for e in pipe.edges if not e["loop"]]
    indeg = {n: 0 for n in pipe.nodes}
    for e in plain:
        if e["dst"] in indeg and e["src"] != START:
            indeg[e["dst"]] += 1
    started = {e["dst"] for e in plain if e["src"] == START}
    for n in indeg:
        if n in started:
            indeg[n] = 0
        elif indeg[n] == 0:
            indeg[n] = -1  # START 직결도 선행도 없는 노드 (도달성 검증에서 걸림)
    waves, done = [], set()
    frontier = sorted(n for n, d in indeg.items() if d == 0)
    while frontier:
        waves.append(frontier)
        done.update(frontier)
        nxt = {}
        for e in plain:
            if e["src"] in done and e["dst"] in indeg and e["dst"] not in done:
                nxt.setdefault(e["dst"], set()).add(e["src"])
        frontier = sorted(
            d
            for d in nxt
            if all(
                e["src"] in done
                for e in plain
                if e["dst"] == d and e["src"] != START
            )
        )
    out = ["실행 계획 (병렬 wave, 피드백 루프 제외):"]
    for i, w in enumerate(waves, 1):
        out.append("  wave %d: %s" % (i, ", ".join(w)))
    loops = [e for e in pipe.edges if e["loop"]]
    if loops:
        out.append("피드백 루프:")
        for e in loops:
            out.append(
                "  %s → %s  [%s]" % (e["src"], e["dst"], _cond_label(e))
            )
    conds = [
        e
        for e in pipe.edges
        if not e["loop"] and _cond_label(e)
    ]
    if conds:
        out.append("조건 분기:")
        for e in conds:
            out.append("  %s → %s  [%s]" % (e["src"], e["dst"], _cond_label(e)))
    return "\n".join(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="yml + 프롬프트 기반 에이전트 그래프 러너")
    ap.add_argument("pipeline", help="pipeline.yml 경로")
    ap.add_argument("--validate", action="store_true", help="검증만 수행")
    ap.add_argument("--dry-run", action="store_true", help="실행 계획 출력")
    ap.add_argument("--mermaid", action="store_true", help="mermaid 다이어그램 출력")
    ap.add_argument("--mock", action="store_true", help="claude 호출 없는 모의 실행")
    ap.add_argument(
        "--mock-status",
        action="append",
        metavar="NODE=S1,S2",
        help="mock 상태 시퀀스 (반복 시 마지막 값 유지). 예: review=FAILED,SUCCEEDED",
    )
    ap.add_argument(
        "--mock-output",
        action="append",
        metavar="NODE=JSON",
        help='mock GRAPH_OUTPUT 주입. 예: prepare={"route": "light"}',
    )
    ap.add_argument("--resume", metavar="RUN_ID", help="이전 실행 재개")
    ap.add_argument(
        "--var",
        action="append",
        metavar="KEY=VALUE",
        default=[],
        help="프롬프트 변수 {{vars.KEY}} 주입 (yml vars 를 덮어씀)",
    )
    args = ap.parse_args(argv)
    args.var = dict(v.split("=", 1) for v in args.var)

    yml = Path(args.pipeline)
    if not yml.is_file():
        print("pipeline 파일이 없다: %s" % yml, file=sys.stderr)
        return 2
    try:
        pipe = Pipeline(load_yaml(yml.read_text()), yml)
    except (YamlError, PipelineError, ValueError) as ex:
        print("파이프라인 로드 실패: %s" % ex, file=sys.stderr)
        return 2

    errors, warnings = pipe.validate()
    for w in warnings:
        print("경고: %s" % w, file=sys.stderr)
    if errors:
        print("검증 실패 (%d건):" % len(errors), file=sys.stderr)
        for e in errors:
            print("  - %s" % e, file=sys.stderr)
        return 2
    if args.validate:
        lang_msgs = MESSAGES.get(str(pipe.settings.get("lang", "en")), MESSAGES["en"])
        print(lang_msgs["validated"] % (len(pipe.nodes), len(pipe.edges), pipe.name))
        return 0
    if args.mermaid:
        print(mermaid(pipe))
        return 0
    if args.dry_run:
        print(dry_run(pipe))
        return 0

    try:
        runner = Runner(pipe, args)
    except PipelineError as ex:
        print(str(ex), file=sys.stderr)
        return 2
    result = runner.run()
    # 종료 코드: 0 성공, 1 실패, 2 로드/검증 오류, 3 게이트 일시정지
    return {"SUCCEEDED": 0, "PAUSED": 3}.get(result, 1)


if __name__ == "__main__":
    sys.exit(main())
