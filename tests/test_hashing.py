from app.utils.hashing import normalize_url, item_unique_key, title_similarity


def test_normalize_url_removes_utm_and_fragment():
    url = "https://Example.com/a/?utm_source=x&b=2#frag"
    assert normalize_url(url) == "https://example.com/a?b=2"


def test_item_unique_key_uses_normalized_url():
    k1 = item_unique_key("m", "https://example.com/a?utm_source=x", "T")
    k2 = item_unique_key("m", "https://example.com/a", "T2")
    assert k1 == k2


def test_title_similarity():
    assert title_similarity("React 面试题整理", "React 面试题合集") > 0.5
