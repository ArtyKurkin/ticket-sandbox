# Independently derived H1 invariants / fault points

Written after production review, before reading remediation security tests.

- I01: Every successful/failed dispatch has recoverable ownership of only its attempt, including shared kernel and registry variants.
- I02: Received owned FD accounting precedes semantic validation; foreign/unexpected inherited FD observations remain visible and cannot be silently replaced by the owned-transfer catalog.
- I03: No read/close uses a stale generation, closed descriptor, or unowned replacement. Close failures remain sticky after recovery.
- I04: feed/accept/finish failure is irreversible across input shape, EOF, sequence, and BaseException.
- I05: Cancellation is monotonic/bounded; valid nested/concurrent cancel at dispatch commit cannot deadlock.
- I06: Partial effects before/after prepare/register/reserve/dispatch/poll/reap/close/publication cannot bypass finalization or change an already issued terminal.
- I07: Actual command UID/GID/group execute admission and independently supplied metadata must match expected; no observed field is overwritten to pass.
- I08: Deadline is respected through publication, including delay after the final pre-publication clock check.
- I09: Positive fake result has no model-owned running/unreaped/unclosed child/helper/FD; unknown resources are not called clean.
- I10: Process-tree/native provenance remains unproven; hashes/commitments do not create OS attestation or authority.

Fault matrix: before/after every effectful method; a second fault during retry;
coherent extra FD and inode/hash/generation substitution; same/different registry
with common invocation/kernel; publication before/after assignment; repeated and
reentrant concurrent cancel; ordinary exceptions and BaseException; late wire
messages and clock advancement/rollback/freeze. No native entry invocation.
