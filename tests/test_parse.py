import unittest
from pathlib import Path

from review_desk import latex, markdown, reviews

EX = Path(__file__).resolve().parent.parent / "examples"


class LatexTest(unittest.TestCase):
    def test_comments_keep_offsets(self):
        src = "a % note\nb 50\\% c % x\n"
        clean = latex.strip_comments(src)
        self.assertEqual(len(clean), len(src))
        self.assertNotIn("note", clean)
        self.assertIn("50\\%", clean)

    def test_structure(self):
        p = latex.parse((EX / "synthetic/paper.tex").read_text())
        kinds = [b.kind for b in p.blocks]
        self.assertIn("math", kinds)
        self.assertIn("figure", kinds)
        self.assertIn("list", kinds)
        self.assertTrue(p.title.startswith("A Damping-Aware"))
        heads = [latex.render(p, b, p.clean[slice(*b.meta["inner"])] if b.meta.get("inner") else "")
                 for b in p.blocks if b.kind == "heading"]
        self.assertTrue(any("Abstract" in h for h in heads))
        self.assertTrue(any(">1</span> Introduction" in h for h in heads))
        self.assertEqual(p.labels["eq:strang"], ("eq", "2"))
        self.assertEqual(p.labels["fig:energy"], ("fig", "1"))
        self.assertIn("dt", p.macros)

    def test_inline(self):
        p = latex.parse(r"\begin{document}x\end{document}")
        p.labels["e1"] = ("eq", "3")
        h = latex.inline(p, r"see \emph{this} and Eq.~\eqref{e1}, cite~\cite{a,b}; $x<y$ \% done--ok")
        self.assertIn("<em>this</em>", h)
        self.assertIn("(3)", h)
        self.assertIn("[a, b]", h)
        self.assertIn('<span class="rd-m">x&lt;y</span>', h)
        self.assertIn("% done–ok", h)

    def test_unknown_macro_degrades(self):
        p = latex.parse(r"\begin{document}\foo{bar} \baz and \begin{theorem}T\end{theorem}\end{document}")
        html = "".join(latex.render(p, b, p.clean[slice(*b.meta["inner"])]) for b in p.blocks)
        self.assertIn("bar", html)
        self.assertIn("T", html)
        self.assertNotIn("theorem", html)


class MarkdownTest(unittest.TestCase):
    def test_structure(self):
        p = markdown.parse((EX / "markdown/paper.md").read_text())
        self.assertEqual(p.title, "Estimating a Diffusion Constant from Short Trajectories")
        kinds = [b.kind for b in p.blocks]
        self.assertEqual(kinds.count("math"), 1)
        self.assertIn("list", kinds)
        self.assertIn("figure", kinds)
        math = [b for b in p.blocks if b.kind == "math"][0]
        self.assertEqual(math.meta["numbers"], ["1"])

    def test_inline(self):
        h = markdown.inline("**b** *i* `c<d` $a_1$ [t](http://x)")
        self.assertIn("<strong>b</strong>", h)
        self.assertIn("<em>i</em>", h)
        self.assertIn("<code>c&lt;d</code>", h)
        self.assertIn('<span class="rd-m">a_1</span>', h)
        self.assertNotIn("http://x", h)


class ReviewsTest(unittest.TestCase):
    def test_markdown_reviews(self):
        cs = reviews.load(EX / "synthetic/reviews.md")
        self.assertEqual([c["id"] for c in cs][:3], ["R1.1", "R1.2", "R1.3"])
        self.assertEqual(len(cs), 7)
        self.assertEqual({c["reviewer"] for c in cs}, {"1", "2"})
        r13 = cs[2]
        self.assertTrue(r13["guessed"])           # anchor guessed from a quoted phrase
        self.assertEqual(r13["anchors"], ["at equal cost"])
        self.assertNotIn("\n", cs[0]["text"])      # hard wraps undone

    def test_numbered_fallback_and_chinese(self):
        cs = reviews.parse_text("审稿人 1\n1. 第一条意见\n@anchor: foo\n2) second\n\nReferee 2:\nComment 1 - x\n")
        self.assertEqual([c["id"] for c in cs], ["R1.1", "R1.2", "R2.1"])
        self.assertEqual(cs[0]["anchors"], ["foo"])

    def test_json_reviews(self):
        cs = reviews.load(EX / "markdown/reviews.json")
        self.assertEqual([c["id"] for c in cs], ["R1.1", "R1.2", "R2.1"])
        self.assertEqual(cs[1]["anchors"], ["\\hat D = \\frac"])

    def test_flat_list_and_duplicates(self):
        cs = reviews.parse_data([{"reviewer": "A", "id": 1, "text": "x"}, {"reviewer": "A", "id": 1, "text": "y"}])
        self.assertEqual(cs[0]["id"], "RA.1")


if __name__ == "__main__":
    unittest.main()
