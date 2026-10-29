"""End-to-end: server process <-> page (HTTP) <-> agent (CLI process)."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EX = ROOT / "examples" / "synthetic"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        for f in ("paper.tex", "reviews.md", "energy_error.svg"):
            shutil.copy(EX / f, cls.tmp / f)
        cls.port = free_port()
        (cls.tmp / "review-desk.json").write_text(json.dumps(
            {"paper": "paper.tex", "reviews": "reviews.md", "port": cls.port}))
        cls.env = {**os.environ, "PYTHONPATH": str(ROOT)}
        cls.srv = subprocess.Popen([sys.executable, "-m", "review_desk", "serve"], cwd=cls.tmp,
                                   env=cls.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + "/api/state", timeout=1)
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.terminate()
        cls.srv.wait(5)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # helpers ---------------------------------------------------------
    def req(self, path, body=None, headers=None, raw=False):
        h = {"Origin": self.base} if body is not None else {}
        if body is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        r = urllib.request.Request(self.base + path, headers=h,
                                   data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(r, timeout=10) as resp:
            data = resp.read()
        return data if raw else json.loads(data)

    def status(self, path, body=None, headers=None):
        try:
            self.req(path, body, headers, raw=True)
            return 200
        except urllib.error.HTTPError as e:
            return e.code

    def cli(self, *args, input=None):
        r = subprocess.run([sys.executable, "-m", "review_desk", *args], cwd=self.tmp, env=self.env,
                           capture_output=True, text=True, timeout=60, input=input)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def note(self, nid):
        return next(n for n in self.req("/api/state")["notes"] if n["id"] == nid)

    # tests -----------------------------------------------------------
    def test_1_mailbox_roundtrip(self):
        waiter = subprocess.Popen([sys.executable, "-m", "review_desk", "wait", "--timeout", "30"],
                                  cwd=self.tmp, env=self.env, stdout=subprocess.PIPE, text=True)
        for _ in range(50):                       # page shows the agent as listening
            if self.req("/api/state")["agent"]["listening"]:
                break
            time.sleep(0.1)
        self.assertTrue(self.req("/api/state")["agent"]["listening"])
        n = self.req("/api/notes", {"text": "Define the modified energy here.", "comment": "R1.1",
                                    "block": "b3", "quote": "keeps the energy error"})
        out, _ = waiter.communicate(timeout=30)
        got = json.loads(out)
        self.assertEqual([g["id"] for g in got], [n["id"]])
        self.assertEqual(got[0]["status"], "working")
        self.assertIn("keeps the energy error", got[0]["context"])
        self.assertEqual(got[0]["line"], 13)
        self.assertTrue(got[0]["comment_text"].startswith("The abstract claims"))

        self.cli("reply", n["id"], "--title", "Abstract: define energy", "--reply", "-",
                 input="Added the definition.")
        note = self.note(n["id"])
        self.assertEqual((note["status"], note["reply"]), ("done", "Added the definition."))

        # the author follows up -> back to the agent, thread kept
        self.req("/api/answer", {"id": n["id"], "text": "Also in Sec. 2 please."})
        got = json.loads(self.cli("wait", "--no-block"))
        self.assertEqual(got[0]["id"], n["id"])
        self.assertEqual([m["who"] for m in got[0]["thread"]], ["agent", "user"])
        self.assertEqual(json.loads(self.cli("wait", "--no-block")), [])

    def test_2_comment_decisions(self):
        self.cli("comment", "R1.2", "--status", "revised", "--root-cause", "structure",
                 "--response", "We now motivate the symmetric splitting.")
        c = next(c for c in self.req("/api/state")["comments"] if c["id"] == "R1.2")
        self.assertEqual((c["status"], c["root_cause"], c["updated_by"]), ("revised", "structure", "agent"))
        # only the author may mark a comment as replied
        self.assertEqual(self.status("/api/comment", {"id": "R1.2", "status": "replied", "actor": "agent"}), 400)
        self.assertEqual(self.status("/api/comment", {"id": "R1.2", "status": "replied"}), 200)
        self.assertEqual(self.status("/api/comment", {"id": "R1.2", "root_cause": "nonsense"}), 400)
        self.assertEqual(self.status("/api/comment", {"id": "R9.9", "status": "todo"}), 400)
        md = self.req("/api/export?format=md", raw=True).decode()
        self.assertIn("We now motivate the symmetric splitting.", md)
        self.assertIn("## Reviewer 2", md)
        tex = self.req("/api/export?format=tex", raw=True).decode()
        self.assertIn(r"\subsection*{Reviewer 1}", tex)
        listing = self.cli("list")
        self.assertNotIn("R1.2 ", listing)            # replied -> out of the inbox

    def test_3_proposal(self):
        p = json.loads(self.cli("propose", "--title", "Add inset", "--text", "Show phase error.",
                                "--quote", "smaller slope by a factor of three", "--comment", "R2.2"))
        self.assertEqual(p["status"], "hold")
        self.assertEqual(p["author"], "agent")
        self.assertIsNotNone(p["block"])
        self.req("/api/answer", {"id": p["id"], "text": "Go ahead"})
        self.assertEqual(self.note(p["id"])["status"], "new")
        self.req("/api/dismiss", {"id": p["id"]})
        self.assertEqual(self.note(p["id"])["status"], "done")

    def test_4_security(self):
        self.assertEqual(self.status("/api/state", headers={"Host": "evil.example:80"}), 403)
        self.assertEqual(self.status("/api/notes", {"text": "x"}, {"Origin": "http://evil.example"}), 403)
        self.assertEqual(self.status("/api/notes", {"text": "x"}, {"Sec-Fetch-Site": "cross-site"}), 403)
        self.assertEqual(self.status("/api/notes", {"text": "x"}, {"Content-Type": "text/plain"}), 415)
        self.assertEqual(self.status("/api/notes", {"text": "  "}), 400)
        for bad in ("/static/../server.py", "/static/%2e%2e/server.py", "/figures/../review-desk.json",
                    "/figures/paper.tex", "/review-desk.json"):
            self.assertEqual(self.status(bad), 404, bad)
        self.assertEqual(self.status("/figures/energy_error.svg"), 200)
        self.assertEqual(self.status("/static/vendor/katex/katex.min.js"), 200)

    def test_5_auto_rebuild(self):
        b0 = self.req("/api/state")["build_id"]
        p = self.tmp / "paper.tex"
        p.write_text(p.read_text().replace("such as Langevin dynamics without noise",
                                           "such as Langevin dynamics with zero noise"))
        s = self.req("/api/state")
        self.assertNotEqual(s["build_id"], b0)
        self.assertEqual(s["report"], [])            # the stale anchor matches again

    def test_6_offline_mode(self):
        """Agent in a sandbox without localhost access: CLI works on the state file."""
        n = self.req("/api/notes", {"text": "offline please", "comment": "R2.1"})
        got = json.loads(self.cli("--offline", "wait", "--no-block"))
        self.assertEqual([g["id"] for g in got], [n["id"]])
        self.assertTrue(got[0]["comment_text"].startswith("The phrase"))
        self.cli("--offline", "reply", n["id"], "--title", "T", "--reply", "done offline")
        self.cli("--offline", "comment", "R2.1", "--status", "analyzing")
        s = self.req("/api/state")                    # the server sees it at once
        self.assertEqual(next(x for x in s["notes"] if x["id"] == n["id"])["reply"], "done offline")
        self.assertEqual(next(c for c in s["comments"] if c["id"] == "R2.1")["status"], "analyzing")
        self.assertIsNotNone(s["agent"]["last_poll"])

    def test_7_concurrent_writers(self):
        """Page (HTTP) and an offline agent writing at once lose nothing."""
        from concurrent.futures import ThreadPoolExecutor
        before = len(self.req("/api/state")["notes"])
        cfgfile = self.tmp / "review-desk.json"
        code = ("import sys; from review_desk.core import Desk; from review_desk.store import load_config;"
                "d = Desk(load_config(sys.argv[1]));"
                "[d.propose({'title': 't', 'text': 'p%d' % i}) for i in range(15)]")
        proc = subprocess.Popen([sys.executable, "-c", code, str(cfgfile)], env=self.env)
        with ThreadPoolExecutor(8) as ex:
            list(ex.map(lambda i: self.req("/api/notes", {"text": f"u{i}"}), range(15)))
        proc.wait(30)
        self.assertEqual(len(self.req("/api/state")["notes"]), before + 30)


class NoServerTest(unittest.TestCase):
    def test_cli_without_server(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            for f in ("paper.tex", "reviews.md"):
                shutil.copy(EX / f, tmp / f)
            (tmp / "review-desk.json").write_text(json.dumps(
                {"paper": "paper.tex", "reviews": "reviews.md", "port": free_port()}))
            env = {**os.environ, "PYTHONPATH": str(ROOT)}
            run = lambda *x: subprocess.run([sys.executable, "-m", "review_desk", *x], cwd=tmp, env=env,
                                            capture_output=True, text=True, timeout=60)
            r = run("wait", "--no-block")
            self.assertEqual((r.returncode, json.loads(r.stdout)), (0, []))
            self.assertIn("using the state file directly", r.stderr)
            r = run("comment", "R1.1", "--response", "draft")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run("export")
            self.assertIn("**Response.** draft", r.stdout)
            r = run("build", "--strict")
            self.assertEqual(r.returncode, 1)              # R2.3's anchor is stale
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
