#!/usr/bin/env python3
"""게이트 투과와 exhausted 위임 보정이 살아 있는지 확인한다.

세 보정(게이트 투과, 셸 단계 투과, exhausted 위임)은 프롬프트에 무엇이
주입되는지로만 드러나서, 깨져도 --validate 와 --mock 이 전부 통과한다.
이 스크립트가 그 구멍을 막는다.

    python3 tests/context_preds_check.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/build/scripts"))
from run_graph import Pipeline, load_yaml  # noqa: E402

YML = """
name: check
nodes:
  - id: analyst
    prompt: p.md
  - id: spec-gate
    gate: true
  - id: implement
    prompt: p.md
  - id: build-check
    type: command
    run: "true"
  - id: qa
    prompt: p.md
    context: [analyst]
  - id: escalate
    prompt: p.md
workflow:
  - analyst
  - spec-gate
  - implement
  - build-check
  - qa:
      if: FAILED
      goto: implement
      max: 2
      exhausted: escalate
"""

CASES = {
    # 게이트는 산출물이 없다 — analyst 가 게이트를 건너 implement 까지 와야 한다
    "implement": ["analyst", "qa"],
    # 셸 단계는 자기 출력을 더할 뿐 체인을 끊지 않는다
    "qa": ["implement", "build-check"],
    # exhausted 위임 노드는 in-edge 가 없다 — 루프 양 끝과 그 선행을 받아야 한다
    "escalate": ["analyst", "qa", "implement", "build-check"],
}

pipe = Pipeline(load_yaml(YML), Path("check.yml"))
failed = []
for nid, expected in CASES.items():
    got = pipe.context_preds(nid)
    if sorted(got) != sorted(expected):
        failed.append("%s: expected %s, got %s" % (nid, expected, got))

if failed:
    print("FAIL\n  " + "\n  ".join(failed), file=sys.stderr)
    sys.exit(1)
print("context_preds ok (%d nodes checked)" % len(CASES))
