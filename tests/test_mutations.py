from pwgen.mutation_pipeline import apply_mutations, MUTATIONS, PROFILES


def test_always_yields_original():
    results = list(apply_mutations("hello", [], 10))
    assert "hello" in results


def test_capitalize():
    results = list(apply_mutations("hello", ["capitalize"], 10))
    assert "Hello" in results


def test_reverse():
    results = list(apply_mutations("hello", ["reverse"], 10))
    assert "olleh" in results


def test_leet_swap():
    results = list(apply_mutations("hello", ["leet_swap"], 10))
    assert "h3110" in results  # l→1, e→3, o→0


def test_max_expansion():
    enabled = list(MUTATIONS.keys())
    results = list(apply_mutations("test", enabled, 3))
    # original + 3 mutations max
    assert len(results) <= 4


def test_no_duplicates_from_identity():
    # If a mutation produces the same string, it should not be yielded
    results = list(apply_mutations("TEST", ["upper"], 10))
    # "TEST".upper() == "TEST" — should not appear twice
    assert results.count("TEST") == 1


def test_standard_profile_keys():
    for name in PROFILES["standard"]:
        assert name in MUTATIONS


def test_aggressive_profile_keys():
    for name in PROFILES["aggressive"]:
        assert name in MUTATIONS
