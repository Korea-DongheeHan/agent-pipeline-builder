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
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
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


def _normalize_when(when):
    """when 정규화. 생략 시 STATUS==SUCCEEDED. 문자열 축약형 지원."""
    if when is None:
        return [{"type": "STATUS", "status": "SUCCEEDED"}]
    conds = []
    for c in _as_list(when):
        if isinstance(c, str):
            u = c.upper()
            if u == "ALWAYS":
                conds.append({"type": "ALWAYS"})
            elif u in VALID_STATUS:
                conds.append({"type": "STATUS", "status": u})
            else:
                raise PipelineError("알 수 없는 when 축약형: %r" % c)
        elif isinstance(c, dict):
            c = dict(c)
            c["type"] = str(c.get("type", "STATUS")).upper()
            if c["type"] == "STATUS":
                c["status"] = str(c.get("status", "SUCCEEDED")).upper()
            conds.append(c)
        else:
            raise PipelineError("when 조건 형식 오류: %r" % c)
    return conds


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
        for nd in doc.get("nodes") or []:
            if not isinstance(nd, dict) or not nd.get("id"):
                raise PipelineError("노드에는 id가 필요하다: %r" % nd)
            nid = str(nd["id"])
            if nid in (START, END, FAIL):
                raise PipelineError("노드 id로 %s 는 예약어다" % nid)
            if nid in self.nodes:
                raise PipelineError("노드 id 중복: %s" % nid)
            self.nodes[nid] = {
                "id": nid,
                "prompt": nd.get("prompt"),
                "model": nd.get("model") or self.settings["model"],
                "agent": nd.get("agent"),  # claude --agent (프로젝트 .claude/agents 정의)
                "join": str(nd.get("join", "all")).lower(),
                "retry": int(nd.get("retry", 0)),
                "allowed_tools": nd.get("allowed_tools"),
                "append_prompt": nd.get("append_prompt"),
                "context": [str(c) for c in _as_list(nd.get("context"))],
            }

        self.edges = []
        for i, ed in enumerate(doc.get("edges") or []):
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
        if not self.nodes:
            errors.append("노드가 없다")
        for nid, nd in self.nodes.items():
            if nd["join"] not in ("all", "any"):
                errors.append("노드 %s: join 은 all|any" % nid)
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
        self.rerun = set()
        self.futures = {}
        self.end_reached = False
        self.fail_reason = None
        self.steps = 0
        self.lock = threading.Lock()
        self.pool = None

    # ---- 로그 ----
    def log(self, msg):
        print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

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
        self.log("▶ 파이프라인 '%s' 시작 — run_id=%s%s"
                 % (self.pipe.name, self.run_id, " (mock)" if self.mock else ""))
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

        ok = self.end_reached and not self.fail_reason
        if not ok and not self.fail_reason:
            waiting = {
                n: sorted(self.required[n] - self.ever_arrived[n])
                for n in self.pipe.nodes
                if self.ever_arrived[n] and self.required[n] - self.ever_arrived[n]
            }
            self.fail_reason = (
                "END 미도달 상태로 실행할 노드가 없다 (데드락). 대기 중: %s"
                % (json.dumps(waiting, ensure_ascii=False) if waiting else "없음")
            )
        result = "SUCCEEDED" if ok else "FAILED"
        self.save_state(result)
        self.log("─" * 60)
        for n in self.pipe.nodes:
            r = self.results.get(n)
            self.log(
                "  %-28s %s"
                % (n, "%s (iter %d)" % (r["status"], r["iteration"]) if r else "미실행")
            )
        self.log("─" * 60)
        if ok:
            self.log("✔ 파이프라인 SUCCEEDED — 산출물: %s" % self.run_dir)
        else:
            self.log("✘ 파이프라인 FAILED — %s" % self.fail_reason)
            self.log("  재개: python3 %s %s --resume %s"
                     % (sys.argv[0], self.pipe.yml_path, self.run_id))
        return ok

    # ---- 완료 처리 (메인 스레드 전용) ----
    def _on_complete(self, node, status, outputs, text):
        if node != START:
            self.log("%s %s %s (iter %d)"
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
                        self.fail_reason = (
                            "피드백 루프 소진: %s (max %d 초과)" % (e["key"], e["loop"]["max"])
                        )
                        return
                    self.log("⚠ 루프 소진 %s → '%s' 노드로 위임" % (e["key"], on_ex))
                    self.live.add(on_ex)
                    self._activate(on_ex)
                    continue
                self.log("↻ 피드백 %s → %s (%d/%d)"
                         % (e["src"], e["dst"], fired, e["loop"]["max"]))
            self._deliver(e)
        if not matched and node != START:
            if status == "FAILED":
                self.fail_reason = "노드 %s FAILED — 실패를 처리하는 엣지가 없다" % node
            else:
                self.log("⚠ %s SUCCEEDED 이후 매칭되는 엣지가 없다 (경로 종료)" % node)
        if node in self.rerun:
            self.rerun.discard(node)
            self._activate(node)

    def _deliver(self, e):
        if self.fail_reason or self.end_reached:
            return
        dst = e["dst"]
        if dst == END:
            self.end_reached = True
            self.log("● END 도달")
            return
        if dst == FAIL:
            self.fail_reason = "노드 %s 가 FAIL 종단으로 라우팅됐다 (%s)" % (
                e["src"],
                e["key"],
            )
            return
        if e["src"] in self.live or e["loop"]:
            self.live.add(dst)
        self.arrived[dst].add(e["key"])
        self.ever_arrived[dst].add(e["key"])
        join = self.pipe.nodes[dst]["join"]
        ready = join == "any" or self.required[dst] <= self.ever_arrived[dst]
        if not ready:
            return
        if dst in self.futures.values():
            self.rerun.add(dst)
            return
        self._activate(dst)

    def _activate(self, node):
        self.steps += 1
        if self.steps > int(self.pipe.settings["max_total_steps"]):
            self.fail_reason = (
                "max_total_steps(%s) 초과 — 폭주 방지로 중단"
                % self.pipe.settings["max_total_steps"]
            )
            return
        self.arrived[node].clear()
        self.iteration[node] += 1
        it = self.iteration[node]
        # resume 캐시: 이전 실행에서 SUCCEEDED 였고 업스트림이 변하지 않았으면 재사용
        prev = self.prev_nodes.get(node)
        if (
            prev
            and not self.mock
            and node not in self.live
            and it == 1
            and prev.get("status") == "SUCCEEDED"
        ):
            self.log("⏩ %s 캐시 재사용 (이전 실행 SUCCEEDED)" % node)
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
        self.log("▶ %s 시작 (iter %d)" % (node, it))
        fut = self.pool.submit(self._run_node, node, it)
        self.futures[fut] = node

    # ---- 노드 실행 (워커 스레드) ----
    def _run_node(self, node, it):
        try:
            nd = self.pipe.nodes[node]
            prompt = self._build_prompt(nd, it)
            pfile = self.run_dir / "prompts" / ("%s.iter%d.prompt.md" % (node, it))
            pfile.write_text(prompt)
            attempts = nd["retry"] + 1
            status, outputs, text = "FAILED", {}, ""
            for attempt in range(1, attempts + 1):
                if self.mock:
                    status, outputs, text = self._exec_mock(node, it)
                else:
                    status, outputs, text = self._exec_claude(nd, prompt)
                if status == "SUCCEEDED" or attempt == attempts:
                    break
                self.log("↺ %s 실패, 재시도 %d/%d" % (node, attempt, nd["retry"]))
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
            text = "러너 내부 오류: %r" % ex
            with self.lock:
                self.results[node] = {
                    "status": "FAILED",
                    "outputs": {},
                    "text": text,
                    "output_file": None,
                    "iteration": it,
                }
            return "FAILED", {}, text

    def _exec_mock(self, node, it):
        seq = self.mock_plan.get(node)
        status = seq[min(it - 1, len(seq) - 1)] if seq else "SUCCEEDED"
        outputs = self.mock_outputs.get(node, {})
        text = "[MOCK] %s iter %d 실행 결과\nGRAPH_STATUS: %s" % (node, it, status)
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
                timeout=int(s["node_timeout"]),
            )
        except subprocess.TimeoutExpired:
            return "FAILED", {}, "노드 타임아웃 (%ss 초과)" % s["node_timeout"]
        except FileNotFoundError:
            return "FAILED", {}, "claude CLI를 찾을 수 없다: %s" % bin_
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
        self.log("⚠ GRAPH_STATUS 마커가 없다 — exit 0 이므로 SUCCEEDED 로 간주")
        return "SUCCEEDED", outputs

    # ---- 프롬프트 조립 ----
    def _build_prompt(self, nd, it):
        path = self.pipe.resolve_prompt(nd["prompt"])
        if path is None:
            raise PipelineError("프롬프트 파일 없음: %s" % nd["prompt"])
        content = path.read_text()
        subs = {"run.id": self.run_id, "node.id": nd["id"], "node.iteration": str(it)}
        for k, v in (self.pipe.vars or {}).items():
            subs["vars.%s" % k] = str(v)
        for k, v in (self.args.var or {}).items():
            subs["vars.%s" % k] = str(v)
        for k, v in subs.items():
            content = content.replace("{{%s}}" % k, v)

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
                    body = body[:limit] + "\n...(잘림 — 전체는 파일 참조)"
                ctx.append(
                    "### 선행 노드 `%s` — %s (iter %d)\n전체 출력 파일: %s\n\n%s"
                    % (p, r["status"], r["iteration"], r["output_file"], body)
                )
        if ctx:
            parts.append("---\n## 선행 노드 출력 (컨텍스트)\n\n" + "\n\n".join(ctx))

        parts.append(
            "---\n"
            "## 실행 프로토콜 (반드시 준수)\n"
            "너는 그래프 파이프라인 '%s'의 노드 `%s` 이다. (반복 %d회차, run_id=%s)\n"
            "작업을 끝내면 응답의 **마지막 줄**에 반드시 다음 형식으로 상태를 보고하라:\n\n"
            "GRAPH_STATUS: SUCCEEDED   (성공)  또는  GRAPH_STATUS: FAILED   (실패)\n\n"
            "후속 노드의 분기 판정에 필요한 값이 있으면 그 **직전 줄**에 한 줄 JSON 으로:\n\n"
            "GRAPH_OUTPUT: {\"key\": \"value\"}\n"
            % (self.pipe.name, nd["id"], it, self.run_id)
        )
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
    lines = ["flowchart TD", "  S([START])", "  E([END])"]
    if any(e["dst"] == FAIL for e in pipe.edges):
        lines.append("  F([FAIL])")
    for n in pipe.nodes:
        lines.append('  %s["%s"]' % (safe[n], n))
    for e in pipe.edges:
        label = _cond_label(e)
        if e["loop"]:
            arrow = ("-. %s .->" % label) if label else "-.->"
        else:
            arrow = ("-->|%s|" % label) if label else "-->"
        lines.append("  %s %s %s" % (safe[e["src"]], arrow, safe[e["dst"]]))
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
        print("검증 통과: 노드 %d개, 엣지 %d개 (%s)"
              % (len(pipe.nodes), len(pipe.edges), pipe.name))
        return 0
    if args.mermaid:
        print(mermaid(pipe))
        return 0
    if args.dry_run:
        print(dry_run(pipe))
        return 0

    runner = Runner(pipe, args)
    return 0 if runner.run() else 1


if __name__ == "__main__":
    sys.exit(main())
