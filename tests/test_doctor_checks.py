
def test_zswap_check_accepts_active_zram_swap(fake_stack):
    from kutu_doctor import doctor

    (fake_stack["sys"] / "module/zswap/parameters/enabled").write_text("N\n")
    (fake_stack["proc"] / "swaps").write_text(
        "Filename\tType\tSize\tUsed\tPriority\n/dev/zram0\tpartition\t1024\t0\t100\n"
    )
    zswap = next(c for c in doctor.kernel_checks() if c.name == "zswap")
    assert zswap.ok is True
    assert "zram" in zswap.detail


def test_zswap_check_fails_when_off_without_zram(fake_stack):
    from kutu_doctor import doctor

    (fake_stack["sys"] / "module/zswap/parameters/enabled").write_text("N\n")
    (fake_stack["proc"] / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n")
    zswap = next(c for c in doctor.kernel_checks() if c.name == "zswap")
    assert zswap.ok is False
