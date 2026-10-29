import tempfile
import unittest
from pathlib import Path

from review_desk.build import build, locate

EX = Path(__file__).resolve().parent.parent / "examples"


class LocateTest(unittest.TestCase):
    def test_exact_and_whitespace(self):
        src = "alpha beta\n   gamma delta"
        self.assertEqual(locate(src, "beta")[2], "exact")
        s, e, how = locate(src, "beta gamma")
        self.assertEqual(how, "whitespace")
        self.assertEqual(src[s:e], "beta\n   gamma")
        self.assertIsNone(locate(src, "epsilon"))

    def test_occurrence(self):
        self.assertEqual(locate("ab ab ab", "ab", 2)[0], 3)


class BuildTest(unittest.TestCase):
    def test_example_marks(self):
        out = build(EX / "synthetic/paper.tex", EX / "synthetic/reviews.md")
        by = {c["id"]: c for c in out["comments"]}
        html = "".join(b["html"] for b in out["blocks"])
        # inline mark around prose that contains math
        self.assertIn('<mark class="rd-mark" data-cid="R1.1">keeps the energy error', html)
        # anchor inside a display equation -> whole block marked
        eq = [b for b in out["blocks"] if "R1.2" in b["cids"]]
        self.assertEqual(len(eq), 1)
        self.assertEqual(eq[0]["kind"], "math")
        # stale anchor -> reported, not fatal
        self.assertEqual(by["R2.3"]["anchor_status"], "unmatched")
        self.assertEqual([r["comment"] for r in out["report"]], ["R2.3"])
        self.assertEqual(by["R2.1"]["anchor_status"], "fuzzy")
        self.assertEqual(html.count("<mark"), html.count("</mark>"))
        self.assertEqual(out["figures"], ["energy_error.svg"])

    def test_overlapping_and_math_crossing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "p.tex").write_text("\\begin{document}\nOne two $x+y$ three four five.\n\\end{document}\n")
            (d / "r.md").write_text("Reviewer 1\nComment 1: a\n@anchor: two $x+y$ three\n"
                                    "Comment 2: b\n@anchor: $x+y$ three four\n"
                                    "Comment 3: c\n@anchor: two $x\n")
            out = build(d / "p.tex", d / "r.md")
            blk = out["blocks"][0]
            self.assertEqual(blk["html"].count("<mark"), 1)          # R1.1 inline
            self.assertEqual(set(blk["cids"]), {"R1.2", "R1.3"})      # overlap / cuts math -> block
            self.assertEqual(blk["html"].count("<mark"), blk["html"].count("</mark>"))

    def test_markdown_build(self):
        out = build(EX / "markdown/paper.md", EX / "markdown/reviews.json")
        self.assertEqual(out["report"], [])
        self.assertEqual({c["anchor_status"] for c in out["comments"]}, {"ok"})


if __name__ == "__main__":
    unittest.main()
