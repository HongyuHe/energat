from energat.common import read_cputime_sec, target_exists


def test_common():
    assert target_exists(1)
    assert read_cputime_sec(1) > 0
