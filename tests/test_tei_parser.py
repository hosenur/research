import unittest

from app.schemas.paper import CitationNode, TextNode
from app.services.tei_parser import parse_tei

TEI = """\
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt><title type="main">Tiny Paper</title></titleStmt>
      <sourceDesc>
        <biblStruct>
          <analytic>
            <author>
              <persName><forename>Ada</forename><surname>Lovelace</surname></persName>
            </author>
            <author>
              <persName><forename>Google</forename><surname>Brain</surname></persName>
            </author>
            <title type="main">Tiny Paper</title>
          </analytic>
          <idno type="arXiv">arXiv:1810.04805v2[cs.CL]</idno>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
    <profileDesc>
      <abstract><p>A short abstract.</p></abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head n="1">Introduction</head>
        <p>
          Prior work
          <ref type="bibr">Peters et al. (2018a)</ref>
          and
          <ref type="bibr" target="#b1">Radford et al. (2018)</ref>
          used the
          <ref type="bibr">([CLS]</ref>
          token.
        </p>
      </div>
      <div>
        <head>Input-Input Layer5</head>
        <p>The Law will never be perfect.</p>
      </div>
      <div>
        <head>QNLI Question Natural Language Inference is a version of the Stanford Question Answering</head>
        <p>A dataset description.</p>
      </div>
    </body>
    <back>
      <div>
        <listBibl>
          <biblStruct xml:id="b0">
            <monogr>
              <title/>
              <author>
                <persName><forename>Matthew</forename><surname>Peters</surname></persName>
              </author>
              <imprint/>
            </monogr>
            <note type="raw_reference">Matthew Peters. 2018a. Deep contextualized word representations. In NAACL.</note>
          </biblStruct>
          <biblStruct xml:id="b1">
            <analytic>
              <title type="main">2018. Improving language understanding by generative pre-training</title>
              <author>
                <persName><forename>Alec</forename><surname>Radford</surname></persName>
              </author>
            </analytic>
            <monogr><title>Tech report</title><imprint/></monogr>
            <note type="raw_reference">Alec Radford. 2018. Improving language understanding by generative pre-training.</note>
          </biblStruct>
          <biblStruct xml:id="b2">
            <monogr>
              <title type="main">Dario Amodei designed and led the research</title>
            </monogr>
            <note type="raw_reference">Dario Amodei designed and led the research.</note>
          </biblStruct>
          <biblStruct xml:id="b3">
            <monogr>
              <title/>
              <imprint><publisher>Ofir Press and Lior Wolf</publisher>
                <date type="published" when="2016">2016</date>
              </imprint>
              <idno type="arXiv">arXiv:1608.05859</idno>
            </monogr>
            <note type="report_type">Using the output embedding to improve language models. arXiv preprint</note>
            <note type="raw_reference">Ofir Press and Lior Wolf. Using the output embedding to improve language models. arXiv preprint arXiv:1608.05859, 2016.</note>
          </biblStruct>
        </listBibl>
      </div>
    </back>
  </text>
</TEI>
"""


class TEIParserTest(unittest.TestCase):
    def setUp(self) -> None:
        self.paper = parse_tei(TEI.encode())

    def test_header_metadata(self) -> None:
        self.assertEqual(self.paper.title, "Tiny Paper")
        self.assertEqual(self.paper.abstract, "A short abstract.")
        self.assertEqual(
            [(author.given, author.family) for author in self.paper.authors],
            [("Ada", "Lovelace")],
        )
        self.assertEqual(self.paper.identifiers.get("arxiv"), "1810.04805")
        self.assertEqual(self.paper.year, 2018)

    def test_sections_are_cleaned(self) -> None:
        titles = [section.title for section in self.paper.sections]
        self.assertEqual(titles, ["Introduction", "QNLI"])
        self.assertEqual(self.paper.sections[0].number, "1")

    def test_special_tokens_stay_text(self) -> None:
        nodes = self.paper.sections[0].paragraphs[0].nodes
        self.assertFalse(
            any(
                isinstance(node, CitationNode) and "CLS" in node.raw_text
                for node in nodes
            )
        )
        self.assertTrue(
            any(isinstance(node, TextNode) and "[CLS]" in node.text for node in nodes)
        )

    def test_author_year_citations_are_linked(self) -> None:
        citations = [
            node
            for node in self.paper.sections[0].paragraphs[0].nodes
            if isinstance(node, CitationNode)
        ]
        peters = next(node for node in citations if "Peters" in node.raw_text)
        self.assertEqual(peters.reference_ids, ["b0"])
        self.assertEqual(peters.unresolved_fragments, [])

    def test_csl_fallback_and_junk_filter(self) -> None:
        by_id = {reference.id: reference for reference in self.paper.references}
        self.assertNotIn("b2", by_id)
        self.assertEqual(by_id["b0"].status, "parsed")
        self.assertEqual(by_id["b0"].csl.title, "Deep contextualized word representations")
        self.assertEqual(by_id["b0"].csl.issued.date_parts, [[2018]])
        self.assertEqual(by_id["b1"].csl.title, "Improving language understanding by generative pre-training")
        self.assertEqual(by_id["b3"].status, "parsed")
        self.assertEqual(
            [(author.given, author.family) for author in by_id["b3"].csl.author],
            [("Ofir", "Press"), ("Lior", "Wolf")],
        )
        self.assertEqual(
            by_id["b3"].csl.title,
            "Using the output embedding to improve language models",
        )

    def test_rejected_xml(self) -> None:
        from app.services.tei_parser import TEIParseError

        with self.assertRaises(TEIParseError):
            parse_tei(b"<note>not tei</note>")
        with self.assertRaises(TEIParseError):
            parse_tei(b"<!DOCTYPE foo [<!ENTITY x SYSTEM 'x'>]><TEI/>")


if __name__ == "__main__":
    unittest.main()
