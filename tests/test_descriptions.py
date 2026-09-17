from librarian.descriptions import looks_like_html, normalize_description, sanitize_description
from librarian.openlibrary import _description


def test_looks_like_html_detects_tags():
    assert looks_like_html("<p>King Tut</p>") is True
    assert looks_like_html("Plain blurb about sand.") is False


def test_sanitize_description_keeps_allowlisted_markup():
    raw = "<h3>Overview</h3><p>A <strong>tomb</strong> and <em>gold</em>.</p><ul><li>One</li></ul>"
    cleaned = sanitize_description(raw)
    assert "<h3>Overview</h3>" in cleaned
    assert "<strong>tomb</strong>" in cleaned
    assert "<em>gold</em>" in cleaned
    assert "<li>One</li>" in cleaned


def test_sanitize_description_strips_scripts_and_attributes():
    raw = '<p onclick="alert(1)">Safe</p><script>alert(1)</script><a href="javascript:alert(1)">x</a>'
    cleaned = sanitize_description(raw)
    assert cleaned == "<p>Safe</p>x"
    assert "script" not in cleaned.lower()
    assert "onclick" not in cleaned
    assert "javascript" not in cleaned.lower()


def test_openlibrary_description_normalizes_html():
    assert _description({"value": "<p>Desert planet.</p><script>x</script>"}) == "<p>Desert planet.</p>"
    assert normalize_description("Just text") == "Just text"
