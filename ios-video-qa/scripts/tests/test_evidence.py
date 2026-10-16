"""근거 서명·실행 대조·결과 판정: 위조한 근거 줄은 세지 않고, 건너뜀은 통과가 아니다."""

import json
import os
import shutil
import tempfile
import unittest

from helpers import casefile, copy_example, human_approve, judge, load_tree

KEY = "a" * 32


class Evidence(unittest.TestCase):
    def setUp(self):
        self.tmp, self.qa = copy_example()
        self.out = tempfile.mkdtemp(prefix="qa-run-")
        self.ev = os.path.join(self.out, "evidence.jsonl")
        self.case = os.path.join(self.out, "case.json")
        open(self.case, "w").write(casefile("parse", os.path.join(self.qa, "cases", "QA-01-write-memo.md")).stdout)
        self.items = [it["id"] for s in json.load(open(self.case))["steps"] for it in s["items"]]

    def tearDown(self):
        shutil.rmtree(self.tmp)
        shutil.rmtree(self.out)

    def record_all(self, skip_last=False):
        tree = load_tree("list.json")
        for i, it in enumerate(self.items):
            rec = ["--evidence", self.ev, "--check-id", f"c{i}", "--items", it, "--step", "1", "--phase", "scenario"]
            if skip_last and i == len(self.items) - 1:
                rc, _ = judge(["skip", "--reason", "오늘은 해당 없음", *rec], key=KEY)
            else:
                rc, _ = judge(["expect", "present", "--save", os.path.join(self.out, "trees"), *rec, "--label", "장보기"], tree, key=KEY)
            self.assertEqual(rc, 0)

    def coverage(self, key=KEY):
        env = dict(os.environ, QA_EVID_KEY=key) if key else None
        r = casefile("coverage", self.case, self.ev, "--out", os.path.join(self.out, "coverage.json"), env=env)
        return r.returncode, json.load(open(os.path.join(self.out, "coverage.json")))["summary"]

    def verdict(self, rc="0"):
        return casefile("verdict", os.path.join(self.out, "coverage.json"), rc, self.qa,
                        os.path.join(self.qa, "cases", "QA-01-write-memo.md"), os.path.join(self.qa, "steps", "QA-01.sh")).stdout.strip()

    def test_signed_lines_count(self):
        self.record_all()
        rc, s = self.coverage()
        self.assertEqual((rc, s["executed"], s["rejected_lines"]), (0, len(self.items), 0))
        self.assertEqual(self.verdict(), "pass")
        self.assertEqual(self.verdict("1"), "fail")

    def test_forged_line_is_rejected(self):
        self.record_all()
        lines = open(self.ev).read().splitlines()
        e = json.loads(lines[-1]); e["result"] = "pass"; e["check_id"] = "forged"; e.pop("mac")
        unsigned = dict(e)
        e2 = dict(e, mac="0" * 64)
        open(self.ev, "w").write("\n".join(lines[:-1] + [json.dumps(unsigned), json.dumps(e2)]) + "\n")
        rc, s = self.coverage()
        self.assertEqual(rc, 1)
        self.assertEqual((s["not-run"], s["rejected_lines"]), (1, 2))
        self.assertEqual(self.verdict(), "incomplete")

    def test_wrong_key_rejects_everything(self):
        self.record_all()
        rc, s = self.coverage(key="b" * 32)
        self.assertEqual((rc, s["executed"]), (1, 0))

    def test_skip_is_not_pass_unless_human_approved(self):
        self.record_all(skip_last=True)
        rc, s = self.coverage()
        self.assertEqual((rc, s["skipped"]), (0, 1))
        self.assertEqual(self.verdict(), "skipped")
        human_approve(self.qa)
        self.assertEqual(self.verdict(), "pass")

    def test_missing_items_are_not_run(self):
        self.record_all()
        lines = open(self.ev).read().splitlines()
        open(self.ev, "w").write("\n".join(lines[:-2]) + "\n")
        rc, s = self.coverage()
        self.assertEqual((rc, s["not-run"]), (1, 2))
        self.assertEqual(self.verdict(), "incomplete")


if __name__ == "__main__":
    unittest.main()
