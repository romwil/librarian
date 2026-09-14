from librarian.kinds import kind_from_newznab, search_category_for_kind


def test_newznab_category_values():
    assert kind_from_newznab(7030) == "comic"
    assert kind_from_newznab("7010") == "magazine"
    assert kind_from_newznab(7020) == "book"
    assert kind_from_newznab(3030) == "audiobook"
    assert kind_from_newznab(3010) == "music"
    assert kind_from_newznab(2000) is None
    assert kind_from_newznab(5000) is None
    assert kind_from_newznab(6000) is None
    assert kind_from_newznab("nope") is None


def test_search_category_for_kind():
    assert search_category_for_kind("comic") == "7030"
    assert search_category_for_kind("magazine") == "7010"
    assert search_category_for_kind("book") == "7000"
    assert search_category_for_kind("tv") is None
