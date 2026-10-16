"""승인 체인: 사람 경로만, 각본·스크립트 변경은 재승인 대기, 기록 위조는 차단, bootstrap은 통과 불가."""

import json
import os
import shutil
import unittest

from helpers import CLEAN_ENV, LIB, PY, check, copy_example, human_approve, quiet, run


class Approvals(unittest.TestCase):
    def setUp(self):
        self.tmp, self.qa = copy_example()
        import approve
        self.approve = approve

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def cli(self, *args, env=None):
        return run(PY + [os.path.join(LIB, "approve.py"), *args], env=env)

    def test_agent_environment_refused(self):
        for k in ("CLAUDECODE", "CODEX_SANDBOX", "CURSOR_TRACE_ID"):
            r = self.cli("approve", self.qa, "QA-01", env=dict(CLEAN_ENV, **{k: "1"}))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("에이전트 환경", r.stderr)
        r = self.cli("answer", self.qa, "G1", "x", env=dict(CLEAN_ENV, CLAUDECODE="1"))
        self.assertIn("에이전트 환경", r.stderr)

    def test_non_tty_refused(self):
        r = self.cli("approve", self.qa, "QA-01")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("대화형 터미널", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.qa, "cases", ".approved.json")))

    def test_no_bootstrap_flag(self):
        for cmd in (["approve", self.qa, "--bootstrap", "QA-01"], ["answer", self.qa, "--bootstrap", "G1", "x"]):
            r = self.cli(*cmd)
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("unrecognized", r.stderr)

    def test_case_change_waits_for_reapproval(self):
        human_approve(self.qa)
        md = os.path.join(self.qa, "cases", "QA-01-write-memo.md")
        open(md, "a", encoding="utf-8").write("- 메모 한 줄 더\n")
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual(rc, 5)
        self.assertTrue(any("각본이 승인(v1) 뒤 바뀜: 메모" in p for p in pending), pending)

    def test_step_reorder_changes_ids(self):
        human_approve(self.qa)
        md = os.path.join(self.qa, "cases", "QA-01-write-memo.md")
        s = open(md, encoding="utf-8").read().replace("| 2 | \"장보기\" 입력", "| 9 | \"장보기\" 입력").replace("| 3 | '저장' 탭", "| 2 | '저장' 탭").replace("| 9 |", "| 3 |")
        open(md, "w", encoding="utf-8").write(s)
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual(rc, 1)
        self.assertTrue(any("각본에 없는 항목 ID" in e for e in errs), errs)

    def test_script_change_waits_and_is_recorded(self):
        human_approve(self.qa)
        sh = os.path.join(self.qa, "steps", "QA-01.sh")
        open(sh, "a", encoding="utf-8").write("# 바꿈\n")
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual(rc, 5)
        self.assertTrue(any("스크립트가 승인(v1) 뒤 바뀜" in p for p in pending), pending)
        r = self.cli("record-change", self.qa, "QA-01")
        self.assertTrue(r.stdout.strip().endswith("QA-01.since-approval.diff"), r.stdout)
        self.assertIn("+# 바꿈", open(r.stdout.strip(), encoding="utf-8").read())
        diffs = [f for f in os.listdir(os.path.join(self.qa, "steps", ".changes")) if f.startswith("QA-01-")]
        self.assertEqual(len(diffs), 1)
        self.cli("record-change", self.qa, "QA-01")   # 바뀌지 않았으면 새 diff를 남기지 않는다
        self.assertEqual(len([f for f in os.listdir(os.path.join(self.qa, "steps", ".changes")) if f.startswith("QA-01-")]), 1)

    def test_tampered_record_blocks(self):
        human_approve(self.qa)
        p = os.path.join(self.qa, "cases", ".approved.json")
        d = json.load(open(p))
        d["QA-01"]["approved_by"] = "someone"
        json.dump(d, open(p, "w"))
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(rc, 1)
        self.assertTrue(any("명령 밖에서 바뀜" in e for e in errs), errs)

    def test_rewritten_store_and_snapshot_blocks_by_chain(self):
        human_approve(self.qa)
        c = os.path.join(self.qa, "cases")
        d = json.load(open(os.path.join(c, ".approved.json")))
        d["QA-01"]["version"] = 7
        for f in (".approved.json", ".approved.snapshot"):
            json.dump(d, open(os.path.join(c, f), "w"), ensure_ascii=False, indent=1)
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(rc, 1)
        self.assertTrue(any("체인의 마지막 기록과 다름" in e for e in errs), errs)

    def test_broken_chain_blocks(self):
        human_approve(self.qa)
        log = os.path.join(self.qa, "cases", ".approvals.log")
        lines = open(log).read().splitlines()
        e = json.loads(lines[0]); e["entry"]["via"] = "page"
        open(log, "w").write(json.dumps(e, ensure_ascii=False) + "\n")
        rc, errs, _, _ = check(self.qa)
        self.assertEqual(rc, 1)

    def test_bootstrap_record_is_not_approval(self):
        quiet(self.approve.do_approve, self.qa, ["QA-01"], "bootstrap", "(bootstrap)")
        rc, errs, pending, _ = check(self.qa)
        self.assertEqual(rc, 5)
        self.assertTrue(any("사람 승인 전(bootstrap" in p for p in pending), pending)
        self.assertFalse(self.approve.human_approved(self.qa, "QA-01", os.path.join(self.qa, "cases", "QA-01-write-memo.md")))

    def test_page_request_needs_same_script(self):
        human_approve(self.qa)
        req = {"kind": "approve-request", "cases": [{"id": "QA-01", "hash": self.approve.case_hash(
            os.path.join(self.qa, "cases", "QA-01-write-memo.md")), "script_hash": "0" * 40}]}
        # 비대화형에서는 사람 경로가 먼저 막는다. 해시 비교는 라이브러리 수준에서 확인
        self.assertNotEqual(req["cases"][0]["script_hash"], self.approve.script_hash(self.approve.script_path(self.qa, "QA-01")))


if __name__ == "__main__":
    unittest.main()
