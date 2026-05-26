import gzip
import json
import os
import tempfile

from pwgen.rule_compiler import compile_rules
from pwgen.io import write_candidates


def _rules(cfg=None):
    return compile_rules(cfg or {})


def test_txt_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.txt")
        candidates = ["abc", "def", "ghi"]
        write_candidates(candidates, _rules(), path=path, fmt="txt", include_header=False)
        with open(path) as f:
            lines = [l.rstrip() for l in f if l.strip()]
        assert lines == candidates


def test_txt_with_header():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.txt")
        write_candidates(["abc"], _rules(), path=path, fmt="txt", include_header=True)
        content = open(path).read()
        assert "AUTHORIZED" in content
        assert "abc" in content


def test_csv_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.csv")
        write_candidates(["abc", "123"], _rules(), path=path, fmt="csv", include_header=False)
        lines = open(path).readlines()
        assert lines[0].startswith("candidate")
        data = [l.split(",")[0] for l in lines[1:]]
        assert "abc" in data
        assert "123" in data


def test_json_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.json")
        write_candidates(["abc", "xyz"], _rules(), path=path, fmt="json", include_header=True)
        payload = json.loads(open(path).read())
        pws = [c["pw"] for c in payload["candidates"]]
        assert "abc" in pws
        assert "xyz" in pws


def test_gzip_output():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.txt.gz")
        write_candidates(["abc", "def"], _rules(), path=path, fmt="txt",
                         compress=True, include_header=False)
        with gzip.open(path, "rt") as f:
            content = f.read()
        assert "abc" in content
        assert "def" in content
