"""Tests for the MD5 surrogate-key scheme."""
import load_dv


def test_same_value_same_key():
    assert load_dv.md5_key("Razorpay Software Private Limited") == load_dv.md5_key(
        "  RAZORPAY software private limited "
    )


def test_different_values_different_keys():
    assert load_dv.md5_key("CRED") != load_dv.md5_key("Zeta")


def test_composite_key_order_sensitivity():
    # Order is part of the identity: (A, B) must differ from (B, A),
    # and the same tuple must always give the same key.
    assert load_dv.md5_key("A", "B") != load_dv.md5_key("B", "A")
    assert load_dv.md5_key("A", "B") == load_dv.md5_key("A", "B")


def test_key_length():
    assert len(load_dv.md5_key("anything")) == 32