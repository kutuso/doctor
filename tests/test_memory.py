from __future__ import annotations

from pathlib import Path

from kutu_doctor import memory


def test_meminfo_parses(fake_stack):
    info = memory.meminfo()
    assert info["MemTotal"] == fake_stack["memtotal_kb"]
    assert info["SwapTotal"] == 8388608


def test_detect_mode_boundaries():
    assert memory.detect_mode(4 * 1024 * 1024) == "saver"
    assert memory.detect_mode(6290432) == "saver"
    assert memory.detect_mode(6291456) == "balanced"
    assert memory.detect_mode(16 * 1024 * 1024) == "balanced"
    assert memory.detect_mode(64 * 1024 * 1024) == "performance"


def test_zswap_params(fake_stack):
    z = memory.zswap_params()
    assert z.enabled is True
    assert z.compressor == "zstd"
    assert z.max_pool_percent == 35
    assert z.shrinker is True
    assert z.zpool_param_exists is False


def test_zswap_live_stats_and_ratio(fake_stack):
    stats = memory.zswap_stats(fake_stack["memtotal_kb"])
    assert stats.pool_total_size == 512 * 1024 * 1024
    assert stats.stored_pages == 131072
    assert stats.pool_cap_bytes == fake_stack["memtotal_kb"] * 1024 * 35 // 100
    assert stats.compressed_ratio is not None
    assert 0.9 < stats.compressed_ratio < 1.1


def test_mglru_damon_psi_thp(fake_stack):
    lru = memory.mglru()
    assert lru.enabled == 0x7
    assert lru.min_ttl_ms == 1000
    assert memory.damon_state() == "on"
    psi = memory.psi_memory()
    assert psi is not None and psi.some_avg10 == 0.12
    assert memory.thp_mode() == "madvise"


def test_user_slice_memory_high(fake_stack):
    assert memory.user_slice_memory_high() == 15118201733


def test_missing_files_degrade_to_none(fake_stack, tmp_path, monkeypatch):
    monkeypatch.setenv("KUTU_SYSFS", str(tmp_path / "empty"))
    (tmp_path / "empty").mkdir()
    assert memory.zswap_params().enabled is None
    assert memory.mglru().enabled is None
    assert memory.damon_state() is None


def test_default_roots_are_absolute(monkeypatch):
    monkeypatch.delenv("KUTU_ROOT", raising=False)
    monkeypatch.delenv("KUTU_SYSFS", raising=False)
    monkeypatch.delenv("KUTU_PROC", raising=False)
    from kutu_doctor import paths

    assert paths.root().is_absolute()
    assert paths.etc() == Path("/etc")
    assert paths.sysfs() == Path("/sys")
    assert paths.proc() == Path("/proc")
