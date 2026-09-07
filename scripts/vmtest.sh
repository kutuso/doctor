#!/usr/bin/env bash
# Integration test in QEMU: boots the kutu OS ISO, shares this repo into the
# live VM over 9p, and runs scripts/vm_kernel_check.py against the real
# kernel (zswap/MGLRU/DAMON mutations + live mode application).
# The host is never touched: QEMU runs in a disposable docker container
# (or natively with KUTU_IN_DOCKER=1 when qemu + expect are installed).
set -euo pipefail
cd "$(dirname "$0")/.."

latest_iso() {
  find "$1" -name 'kutu-os-*.iso' -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | cut -d' ' -f2- || true
}

ISO="${KUTU_ISO:-${EXPECT_ISO:-$(latest_iso "../os/out")}}"
[ -n "$ISO" ] || { echo "no kutu ISO found; set KUTU_ISO=... or build one in ../os (make build)"; exit 1; }
ISO=$(readlink -f "$ISO")
ISO_NAME=$(basename "$ISO")

if [ "${KUTU_IN_DOCKER:-0}" != 1 ]; then
  command -v docker >/dev/null 2>&1 || { echo "docker required (or set KUTU_IN_DOCKER=1 with qemu-system-x86 + expect)"; exit 1; }
  KVM_FLAGS=()
  [ -w /dev/kvm ] && KVM_FLAGS=(--device /dev/kvm)
  exec docker run --rm "${KVM_FLAGS[@]+"${KVM_FLAGS[@]}"}" \
    -v "$PWD:/cli" -v "$(dirname "$ISO"):/iso:ro" \
    -w /cli -e KUTU_IN_DOCKER=1 -e EXPECT_ISO="/iso/$ISO_NAME" \
    archlinux:base-devel bash scripts/vmtest.sh
fi

pacman -Sy --noconfirm --needed qemu-system-x86 qemu-system-x86-firmware expect >/dev/null 2>&1

export REPO=/cli
export SMOKE_LOG=/cli/vmtest.log
mkdir -p /cli
: > "$SMOKE_LOG"

KVM_ARGS=""
[ -w /dev/kvm ] && KVM_ARGS="-enable-kvm -cpu host"
export KVM_ARGS

expect <<'EOF'
set timeout 1800
log_file -noappend $env(SMOKE_LOG)
spawn qemu-system-x86_64 -m 2048 -display none -serial mon:stdio -nographic \
  {*}$env(KVM_ARGS) \
  -virtfs local,path=$env(REPO),mount_tag=host0,security_model=none,rw \
  -cdrom $env(EXPECT_ISO) -boot d
expect {
  -re {\]# $} {}
  timeout { puts "TIMEOUT waiting for serial root shell"; exit 1 }
}
send -- {modprobe 9pnet_virtio 9p; mkdir -p /mnt/cli; mount -t 9p -o trans=virtio,version=9p2000.L,msize=104857600 host0 /mnt/cli; echo VMTEST:MOUNT:$?}
send "\r"
expect {\]# $}
send -- {cd /mnt/cli && PYTHONDONTWRITEBYTECODE=1 python3 scripts/vm_kernel_check.py; echo VMCHECK:$?}
send "\r"
expect {\]# $}
send -- {poweroff}
send "\r"
expect {
  eof {}
  timeout { puts "TIMEOUT waiting for poweroff"; exit 1 }
}
EOF

fails=$(grep -c 'VMTEST:FAIL:' "$SMOKE_LOG" || true)
passes=$(grep -c 'VMTEST:PASS:' "$SMOKE_LOG" || true)
if ! grep -q 'VMTEST:MOUNT:0' "$SMOKE_LOG"; then
  echo "vmtest: FAIL (9p mount failed — see $SMOKE_LOG)"; exit 1
fi
if ! grep -q 'VMCHECK:0' "$SMOKE_LOG"; then
  echo "vmtest: FAIL (in-VM check did not pass — see $SMOKE_LOG)"; exit 1
fi
echo "vmtest: PASS ($passes checks, $fails failures; log: $SMOKE_LOG)"
