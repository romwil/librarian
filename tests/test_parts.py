"""Value tests for Usenet multipart markers and part_set assembly."""

from librarian.parts import (
    build_part_set,
    infer_part_fields,
    missing_parts,
    parse_part_marker,
    part_set_incomplete,
    strip_part_markers,
)


def test_parse_part_marker_styles():
    assert parse_part_marker("Stephen King - The Stand 01of32") == {
        "part": 1,
        "total": 32,
        "style": "of",
        "raw": "01of32",
    }
    assert parse_part_marker("Raymond E. Feist - Magician Part 3/5") == {
        "part": 3,
        "total": 5,
        "style": "part",
        "raw": "Part 3/5",
    }
    assert parse_part_marker("Album CD2") == {
        "part": 2,
        "total": None,
        "style": "cd",
        "raw": "CD2",
    }


def test_prefer_named_over_yenc_bracket():
    marker = parse_part_marker('(NMRT [13/16] - "Raymond E. Feist - Magician Part 3/5.mp3" yEnc')
    assert marker == {"part": 3, "total": 5, "style": "part", "raw": "Part 3/5"}


def test_strip_bare_slash_indexes():
    assert "13" not in strip_part_markers("Magician Part 3/5 13/16.mp3 yEnc")
    assert "Magician" in strip_part_markers("Magician Part 3/5 13/16.mp3 yEnc")


def test_missing_parts_vs_total():
    assert missing_parts([1, 3], 5) == [2, 4, 5]
    assert missing_parts([0, 2], 4, origin=0) == [1, 3]


def test_infer_and_build_part_set():
    fields = infer_part_fields(
        titles=["Raymond E. Feist - Magician Part 3/5"],
        filenames=["Magician Part 3.m4b"],
    )
    assert fields["part_total"] == 5
    assert fields["part_style"] == "part"
    assert "Magician" in fields["part_base"]

    work = {
        "title": "Magician",
        "part_total": 5,
        "part_style": "part",
        "part_base": "Raymond E Feist Magician",
    }
    files = [
        {"filename": "Magician Part 3.m4b", "part": 3},
        {"filename": "Magician Part 5.m4b", "part": 5},
    ]
    part_set = build_part_set(work, files)
    assert part_set == {
        "total": 5,
        "owned": [3, 5],
        "style": "part",
        "base": "Raymond E Feist Magician",
        "origin": 1,
    }
    assert part_set_incomplete(part_set) is True
    assert part_set_incomplete({**part_set, "owned": [1, 2, 3, 4, 5]}) is False
