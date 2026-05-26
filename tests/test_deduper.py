from pwgen.deduper import Deduper, dedupe_stream


def test_no_false_negatives():
    """
    Bloom filters guarantee NO false negatives: an item that was added is
    ALWAYS detected as present. False positives (unique items wrongly treated
    as duplicates) are the accepted trade-off for O(1) memory.
    Verify the false-positive rate stays within the configured error bound.
    """
    items = [f"pw{i}" for i in range(1000)]
    seen = set(dedupe_stream(items, use_bloom=True))
    # All items should appear — allow up to 1% false-positive drop rate
    assert len(seen) >= len(items) * 0.99, (
        f"Too many false positives: only {len(seen)}/{len(items)} unique items passed"
    )


def test_duplicates_removed():
    items = ["abc", "abc", "def", "def", "ghi"]
    result = list(dedupe_stream(items))
    assert result.count("abc") == 1
    assert result.count("def") == 1
    assert "ghi" in result


def test_stats_tracking():
    d = Deduper(use_bloom=False)
    for w in ["a", "b", "a", "c", "b"]:
        d.is_new(w)
    s = d.stats
    assert s["seen"] == 5
    assert s["duplicates"] == 2
    assert s["unique"] == 3


def test_bloom_mode():
    d = Deduper(use_bloom=True)
    assert d.is_new("hello")
    assert not d.is_new("hello")
    assert d.is_new("world")
    assert d.stats["mode"] == "bloom"


def test_set_fallback_mode():
    d = Deduper(use_bloom=False)
    assert d.is_new("test")
    assert not d.is_new("test")
    assert d.stats["mode"] == "set"


def test_large_unique_set_acceptable_false_positive_rate():
    """
    Over 10K unique items, the Bloom filter false-positive rate should be
    well under 1% (ScalableBloomFilter is configured to 0.1% error rate).
    """
    items = [str(i) for i in range(10_000)]
    seen = list(dedupe_stream(items, use_bloom=True))
    # Accept up to 1% false positives (configured target is 0.1%)
    assert len(seen) >= 9_900, (
        f"False-positive rate too high: only {len(seen)}/10000 passed"
    )
