import unittest

from app.services.citation_utils import (
    detect_citation_style,
    extract_cite_keys,
    extract_year_label,
    is_figure_or_prompt_section,
    is_special_token_citation,
    is_spurious_bibliography_entry,
    looks_like_name_list,
    normalize_section_title,
    parse_author_year_mentions,
    parse_name_list,
    recover_title_from_raw,
    strip_bibliography_prefix,
    strip_year_prefix,
)


class CitationUtilsTest(unittest.TestCase):
    def test_special_tokens_are_not_citations(self) -> None:
        self.assertTrue(is_special_token_citation("[CLS]"))
        self.assertTrue(is_special_token_citation("([SEP]"))
        self.assertTrue(is_special_token_citation("[MASK]"))
        self.assertFalse(is_special_token_citation("(Peters et al., 2018a)"))

    def test_author_year_mentions(self) -> None:
        mentions = parse_author_year_mentions(
            "(Dai and Le, 2015; Peters et al., 2018a; Radford et al., 2018)"
        )
        keys = {(item.author, item.year, item.letter) for item in mentions}
        self.assertIn(("Dai", 2015, None), keys)
        self.assertIn(("Peters", 2018, "a"), keys)
        self.assertIn(("Radford", 2018, None), keys)

    def test_parenthetical_author_year(self) -> None:
        mentions = parse_author_year_mentions("Peters et al. (2018a)")
        self.assertEqual(mentions[0].year, 2018)
        self.assertEqual(mentions[0].letter, "a")

    def test_title_from_raw_reference(self) -> None:
        self.assertEqual(
            recover_title_from_raw(
                "Matthew Peters. 2018a. Deep contextualized word representations. In NAACL."
            ),
            "Deep contextualized word representations",
        )
        self.assertEqual(
            recover_title_from_raw(
                "Ofir Press and Lior Wolf. Using the output embedding to improve language models. arXiv preprint arXiv:1608.05859, 2016."
            ),
            "Using the output embedding to improve language models",
        )
        self.assertEqual(
            recover_title_from_raw(
                "Roy Schwartz, Jesse Dodge, Noah A. Smith, and Oren Etzioni. Green AI. CoRR, abs/1907.10597, 2019."
            ),
            "Green AI",
        )

    def test_year_prefix_stripped_from_title(self) -> None:
        title, year, letter = strip_year_prefix(
            "2018a. Deep contextualized word representations"
        )
        self.assertEqual(title, "Deep contextualized word representations")
        self.assertEqual(year, 2018)
        self.assertEqual(letter, "a")

    def test_extract_year_label_prefers_disambiguator(self) -> None:
        year, letter = extract_year_label(
            "Matthew Peters. 2018a. Deep contextualized word representations."
        )
        self.assertEqual((year, letter), (2018, "a"))

    def test_name_list_from_publisher_field(self) -> None:
        self.assertTrue(looks_like_name_list("Ofir Press and Lior Wolf"))
        names = parse_name_list("Ofir Press and Lior Wolf")
        self.assertEqual(
            [(name.given, name.family) for name in names],
            [("Ofir", "Press"), ("Lior", "Wolf")],
        )

    def test_spurious_acknowledgements_and_examples(self) -> None:
        self.assertTrue(
            is_spurious_bibliography_entry(
                "Poor English input: I eated the purple berries. Good English output: I ate them.",
                None,
                has_year=False,
                has_identifier=False,
            )
        )
        self.assertTrue(
            is_spurious_bibliography_entry(
                "Dario Amodei designed and led the research.",
                None,
                has_year=False,
                has_identifier=False,
            )
        )
        self.assertFalse(
            is_spurious_bibliography_entry(
                "Ashish Vaswani et al. Attention is all you need. In NeurIPS, 2017.",
                "Attention is all you need",
                has_year=True,
                has_identifier=False,
            )
        )

    def test_cite_keys_ignore_numeric_brackets(self) -> None:
        self.assertEqual(extract_cite_keys("[MCCD13, PSM14]"), ["MCCD13", "PSM14"])
        self.assertEqual(extract_cite_keys("[13, 7]"), [])

    def test_section_title_cleanup(self) -> None:
        self.assertTrue(is_figure_or_prompt_section("Input-Input Layer5"))
        self.assertTrue(is_figure_or_prompt_section("Context → Article:"))
        self.assertTrue(is_figure_or_prompt_section("Setting CL A1 A2 RI RW"))
        self.assertFalse(is_figure_or_prompt_section("Introduction"))
        self.assertEqual(
            normalize_section_title(
                "QNLI Question Natural Language Inference is a version of the Stanford Question Answering"
            ),
            "QNLI",
        )

    def test_reference_prefix_and_style_detection(self) -> None:
        self.assertTrue(
            strip_bibliography_prefix("References [ADG + 16] Learning to learn").startswith(
                "[ADG + 16]"
            )
        )
        self.assertEqual(detect_citation_style(["[13]", "[7]", "[35, 2]"]), "numeric")
        self.assertEqual(
            detect_citation_style(["(Peters et al., 2018a)", "Radford et al. (2018)"]),
            "author-year",
        )
        self.assertEqual(detect_citation_style(["[MCCD13]", "[RNSS18]"]), "harvard-key")


if __name__ == "__main__":
    unittest.main()
