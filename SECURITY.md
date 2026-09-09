# Security Policy

## Supported versions

The `master` branch is supported. Released versions are the tagged
`vX.Y.Z` commits.

## Reporting a vulnerability

Please report vulnerabilities privately:
[GitHub security advisories](https://github.com/kutuso/doctor/security/advisories/new).

Include reproduction steps and, where relevant, the environment overrides
(`KUTU_ROOT`, `KUTU_SYSFS`, ...) in play. The tool runs with user privileges
except `mode set/apply` and `reset`, which require root via sudo — reports
about those paths are especially welcome.

## Scope notes

- The CLI only writes files owned by the kutu OS packages
  (`/etc/kutu/**`, the `user.slice` drop-in) and only applies cgroup state
  through `systemctl` — never raw cgroupfs.
- Environment overrides (`KUTU_SYSTEMCTL`, `KUTU_SYSTEMD_RUN`, ...) are for
  tests and chroot inspection; they intentionally alter what gets executed
  and are not a security boundary.
