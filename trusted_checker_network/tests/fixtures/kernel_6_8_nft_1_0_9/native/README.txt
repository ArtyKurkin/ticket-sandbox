TRUSTED CHECKER — REAL KERNEL EVIDENCE (2026-10-20)

SOURCE: raw copy of the chat-uploaded VDS terminal capture: Вставленный Markdown(20261020-115809).md.

Three *.json files are exact unchanged lines extracted from the original terminal capture, WITHOUT reserialization or reconstruction. They are the FINAL cumulative snapshot, not atomic probe before/after evidence.

Machine: Ubuntu 24.04.5, kernel 6.8.0-147-generic, nft 1.0.9. Test bridge tc-br0, ports tc-br-r-host and tc-br-t-host, namespaces tc-br-runner and tc-br-target.

Historical tests conducted in this conversation: HTTP 200; ping blocked; TCP 9090 blocked; reverse TCP attempt blocked. Past BEFORE/AFTER outputs were pasted as human-readable `nft -a list table ...`, NOT JSON captures from a single controlled verifier recipe. Do not substitute reconstructed JSON for missing originals.

Known limitations: lab uses interface-scoped forward filtering with base-chain policy ACCEPT, not full global default-deny; no Docker runtime or canonical nft_counter_probe_v1 run; background traffic noted; no verified physical acceptance, checker remains shadow-only.

Codex: use these files only as native JSON-format compatibility fixtures and observations; keep physical tests and approvals gated. For a future physical probe, produce true before/after raw JSON from same controlled attempt with provenance and topology verification.
