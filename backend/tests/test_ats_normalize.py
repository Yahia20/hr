from app.ats.normalize import matching_line, prepare_text, readable_line


def test_already_logical_arabic_is_not_reversed():
    line = "الخبرة المهنية: مدير حجوزات"
    assert readable_line(line) == line


def test_visual_word_order_is_repaired_by_phrase_evidence():
    assert readable_line("المهنية الخبرة") == "الخبرة المهنية"


def test_presentation_forms_and_reversed_letters_become_readable():
    # Visual-order glyphs for "الخبرة المهنية"; generated text, not a real CV.
    extracted = "ﺔﻴﻨﻬﻤﻟﺍ ﺓﺮﺒﺨﻟﺍ"
    assert readable_line(extracted) == "الخبرة المهنية"


def test_mixed_scripts_spaced_latin_and_columns_keep_structure():
    mixed = readable_line("A m a d e u s :ﺕﺍﺭﺎﻬﻤﻟﺍ")
    assert mixed.startswith("المهارات")
    assert mixed.endswith("Amadeus")
    assert readable_line("Education   التعليم") == "Education   التعليم"
    assert readable_line("المهارات: A m a d e u s / N D C") == "المهارات: Amadeus / NDC"


def test_dual_outputs_and_line_map():
    prepared = prepare_text("Original\nأحمد\n")
    assert prepared.readable_text.splitlines() == ["Original", "أحمد"]
    assert prepared.matching_lines == ["original", "احمد"]
    assert prepared.line_map == [0, 1]
    assert matching_line("أإآ ة ى ـ مُدير ١٢٣") == "ااا ه ي مدير 123"

