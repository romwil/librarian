"""Golden fixtures for comic scene normalization."""

from __future__ import annotations

import pytest

from librarian.comic_normalize import normalize_comic_name

FIXTURES = [
    # input, series, volume_year, issue, year
    ("Saga.2012.001.Digital-Empire", "Saga", 2012, "1", 2012),
    ("Saga.#54.(2022).c2c-Minutemen", "Saga", None, "54", 2022),
    ("Moon.Knight.1980.001.Digital", "Moon Knight", 1980, "1", 1980),
    ("Moon.Knight.2014.001.(2014)", "Moon Knight", 2014, "1", 2014),
    ("Batman.#18.1.(2024).no-ads", "Batman", None, "18.1", 2024),
    ("Amazing.Spider-Man.Annual.2023.001", "Amazing Spider Man", None, "Annual 1", 2023),
    ("X-Men.v1.094.(1975)", "X Men", None, "94", 1975),
    ("Watchmen.#01.(1986).Megan", "Watchmen", None, "1", 1986),
    ("Sandman.Overture.#1.(2013).CVR.B", "Sandman Overture", None, "1", 2013),
    ("Paper.Girls.001.(2015).Digital-Empire", "Paper Girls", None, "1", 2015),
    ("Monstress.#18.(2021).HD-WebRip", "Monstress", None, "18", 2021),
    ("The.Walking.Dead.#193.(2019)", "The Walking Dead", None, "193", 2019),
    ("Daredevil.1964.001.Digital-Glorith", "Daredevil", 1964, "1", 1964),
    ("Ultimate.Spider-Man.2024.001", "Ultimate Spider Man", 2024, "1", 2024),
    ("Something.is.Killing.the.Children.#18.(2022)", "Something is Killing the Children", None, "18", 2022),
]


@pytest.mark.parametrize("raw,series,volume_year,issue,year", FIXTURES)
def test_comic_normalize_fixtures(raw, series, volume_year, issue, year):
    tokens = normalize_comic_name(raw)
    assert tokens.series == series
    assert tokens.volume_year == volume_year
    assert tokens.issue == issue
    assert tokens.year == year


def test_tpb_subtitle_tokens():
    tokens = normalize_comic_name("Descender.Vol.01.Tin.Stars.(2015).TPB")
    assert tokens.series == "Descender"
    assert tokens.subtitle == "Tin Stars"
    assert tokens.year == 2015
    assert tokens.format == "tpb"
    assert tokens.issue == ""


def test_variant_captured_not_in_series():
    tokens = normalize_comic_name("Sandman.Overture.#1.(2013).CVR.B")
    assert "Cvr" not in tokens.series and "CVR" not in tokens.series
    assert tokens.variant
