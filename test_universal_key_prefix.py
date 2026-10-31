"""The Python half of the XOR-prefixed keys (LINK_LAYER_PLAN.md §8 step 1): the
XOR/WIP fold mirrors the ML fold, and destruct_key rejects a tag it does not
know.  Run with  python -m pytest contrib/Isabelle_RPC/test_universal_key_prefix.py
"""
import pytest

from Isabelle_RPC_Host.universal_key import destruct_key, xor_theory_prefix


def _key(tag: int, prefix: bytes = bytes(16), digest: bytes = bytes(range(15))) -> bytes:
    return prefix + bytes([tag]) + digest


def test_xor_prefix_fold_matches_the_ml_fold():
    # Two WIP-free hashes XOR byte by byte; one WIP hash (LSB of byte 0) makes
    # the result WIP, whatever the XOR parity (two WIP hashes cancel in the XOR
    # but the OR keeps the bit).
    a = bytes([0x02] + [0xAA] * 15)
    b = bytes([0x04] + [0x55] * 15)
    assert xor_theory_prefix([a, b]) == bytes([0x06] + [0xFF] * 15)
    w1 = bytes([0x03] + [0] * 15)
    w2 = bytes([0x05] + [0] * 15)
    assert xor_theory_prefix([w1, w2])[0] == 0x07      # 0x03 ^ 0x05 = 0x06, OR'd with 1
    assert xor_theory_prefix([]) == bytes(16)


@pytest.mark.parametrize("tag", [9, 0x0A])
def test_an_unknown_tag_is_rejected(tag):
    # 9 is unused: no entity kind has it
    with pytest.raises(ValueError):
        destruct_key(_key(tag))
