from graphy.services.notes import clean, preview_of, text_of, title_of


def test_formatting_survives_and_active_content_does_not() -> None:
    dirty = ('<div onclick="x()">Hello <b style="color:red">world</b></div>'
             '<script>alert(1)</script><img src=x onerror=y>'
             '<a href="javascript:alert(1)">bad</a><a href="https://ok.example/p">ok</a>')
    out = clean(dirty)
    assert "<b>world</b>" in out and "Hello" in out
    for bad in ("script", "onclick", "onerror", "javascript:", "style", "<img"):
        assert bad not in out
    assert 'href="https://ok.example/p"' in out and 'rel="noopener noreferrer"' in out


def test_only_http_https_and_mailto_links_are_kept() -> None:
    out = clean('<a href="mailto:a@x.example">m</a><a href="data:text/html,x">d</a>'
                '<a href="ftp://x.example">f</a>')
    assert 'href="mailto:a@x.example"' in out
    assert "data:" not in out and "ftp:" not in out


def test_text_keeps_one_block_per_line() -> None:
    body = "<h2>Call with bank</h2><p>They confirmed <b>one</b> owner &amp; two accounts.</p><ul><li>a</li><li>b</li></ul>"
    assert text_of(body).splitlines() == [
        "Call with bank", "They confirmed one owner & two accounts.", "a", "b"]
    assert preview_of(body, 20) == "Call with bank They"


def test_a_title_defaults_to_the_first_line() -> None:
    assert title_of("  ", "<p>First line here</p><p>second</p>") == "First line here"
    assert title_of("My title", "<p>x</p>") == "My title"
    assert title_of("", "") == "Untitled"
    assert len(title_of("", "<p>" + "w" * 500 + "</p>")) == 80
