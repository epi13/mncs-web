"""Harness unit tests: no MNCS execution, no CLI.

Guards the corpus-construction invariants that cross-backend validity
depends on. If these fail, every backend run that synthesizes records
is suspect.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from web_exec import REC, U64, synth_header, synth_header_block, synth_parser


def field_names(rec):
    return [k for k, _v in rec["record"]["fields"]]


def test_rec_emits_canonical_field_order():
    rec = REC("web.router.v1", "Route", [
        ("method", U64(0)),
        ("pattern", {"sequence": {"values": []}}),
        ("pattern_len", U64(0)),
        ("has_param", {"boolean": {"value": False}}),
        ("prefix_len", U64(0)),
        ("handler", U64(0)),
    ])
    assert field_names(rec) == sorted(field_names(rec))
    assert field_names(rec) == [
        "handler", "has_param", "method",
        "pattern", "pattern_len", "prefix_len",
    ]


def test_rec_sorts_nested_records():
    # synth_* helpers pass declaration order; the envelope must still
    # come out canonical at every nesting level (HeaderBlock contains
    # Header records; Parser contains a ParseOut record tree).
    block = synth_header_block([synth_header(0, 4, 6, 2)])
    assert field_names(block) == ["count", "headers"]
    nested = block["record"]["fields"][1][1]["sequence"]["values"][0]
    assert field_names(nested) == [
        "name_len", "name_start", "value_len", "value_start",
    ]
    parser = synth_parser()
    assert field_names(parser) == ["out", "settled", "staged", "staged_len"]
    out = dict(parser["record"]["fields"])["out"]
    assert field_names(out) == [
        "consumed", "error", "head", "is_response", "kind", "response",
    ]
