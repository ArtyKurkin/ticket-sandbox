# Saved native capture — 2026-10-21

User-supplied archive `tc-native-capture-20261021T082517Z.tar.gz`, SHA-256
`b641f7f27eeac55c72651ab6f76effff034135d01cc35226d19c49a35283e0b5` (8080 bytes).
The archive and all 108 original files under [native/](native) are preserved
byte-for-byte. The embedded SHA256SUMS has 107 entries, covering every other
original file. There are 34 saved zero `.exit` records, 34 empty `.err` files,
34 JSON documents (33 topology sources and one host nft ruleset).

Reported versions: Linux 6.8.0-147-generic, nftables 1.0.9, iproute2/bridge 6.1.0.
These are captured text observations, not authenticated binary/host provenance.
The scope labels are host and four named lab namespaces. They are NOT trusted
NamespaceKey/FD/inode/NSID bindings. Tar metadata or the archive name must not
be used to reconstruct per-command capture intervals.

Generated offline review artifacts, distinct from originals:

- [provenance.json](provenance.json): byte counts/hashes and explicit missing proof.
- [source_mapping.json](source_mapping.json): paths, hashes, stdout/stderr/exit refs.
  Exact execution argv and namespace wrapper are **unrecorded**. Nominal future
  source-plan argv is labeled separately and is not proof of what ran.
- [observed_matrix.json](observed_matrix.json): all native fields/types/values,
  array cardinalities, field presence/absence, document counts and old-schema
  decode outcomes. Corpus observations never dynamically widen production schemas.
- [FIELD_MATRIX.md](FIELD_MATRIX.md): 200 field paths against the provisional
  registry and separately reviewed diagnostic revision 2.

The dedicated static profile `iproute2-6.1.0-native-topology-v2-diagnostic-2`
supports these bounded shapes for diagnostic decoding only. No route defaults,
`ifname`→`dev` aliases, string→integer master coercion or volatility erasure is
performed. Integer NSIDs and reciprocal veth indices are candidates, not proof
of peer namespace identity. Management-interface FDB self entries stay visible.

The corpus is NOT a canonical positive installation. It contains `tc-br0`,
`tc_ct_lab`/`tc_strict_lab`, old named namespaces, IPv6 on test links and provider
routes. It has no measurement before/after, packet artifacts or trusted writer
control. There are no peer bridge/VLAN/FDB documents (12 missing documents under
a nine-sources-per-scope diagnostic coverage plan), no namespace FD witnesses,
actual argv/timing/transport completion, complete tc/XDP/flowtable/offload/sysctl,
permissions/capabilities or inherited-FD inventory.

All new results remain offline, unauthenticated and unproven. Physical permits,
ownership, management policy verification and isolation verification are false.
Raw captures are internal fixtures, not a bounded operator export. Do not filter,
rename, reconstruct missing data or fit the expected policy to this corpus.
