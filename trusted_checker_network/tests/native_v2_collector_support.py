"""Explicit deterministic capture fixtures. Never execute the recorded argv."""
from dataclasses import dataclass, replace

from trusted_checker_network import native_v2_contracts as c
from trusted_checker_network import native_v2_capture_contracts as a
from trusted_checker_network import native_v2_collector as r
from .native_v2_support import uid, hd

WALL = 1792530000000000
MONO = 1000000


def stamp(offset=0): return a.CaptureTime2(WALL + offset, MONO + offset)


def scripts2(plan, raw_documents):
    result = []
    for index, (request, raw) in enumerate(zip(plan.requests, raw_documents)):
        events = []; offset = 1000 + index * 10000
        for pos in range(0, len(raw), a.CHUNK_BYTES):
            events.append(r.MockReadEvent2('stdout', stamp(offset + len(events)*10), plan.reader,
                                          raw[pos:pos+a.CHUNK_BYTES]))
        for kind in ('stdout_eof', 'stderr_eof', 'exit', 'complete'):
            events.append(r.MockReadEvent2(kind, stamp(offset + len(events)*10), plan.reader,
                                          exit_status=0 if kind == 'exit' else None))
        result.append(r.MockReadScript2(request, plan.binaries.binary(a.operation2(request.source).binary),
                                       request.argv, plan.reader, stamp(offset), tuple(events)))
    return tuple(result)


@dataclass
class CollectorFixture2:
    plan: a.CapturePlan2
    raw_documents: tuple
    scripts: tuple

    @classmethod
    def create(cls, documents=None, namespaces=None, installation=None, binary_digests=None):
        """documents: explicit role/source/profile/raw/capture UUID, not parsed data."""
        keys = namespaces or tuple((role, c.NamespaceKey2(uid(1), 100+i, uid(2), 1))
                                   for i, role in enumerate(('host', 'runner', 'target')))
        refs = tuple(a.NamespaceReference2(role, key, uid(100+i), hd('namespace-'+role), 200+i, 10000+i,
                        tuple((j, other.netns_inode) for j, (_, other) in enumerate(keys) if other != key),
                        tuple(hd('peer-'+str(min(i,j))+'-'+str(max(i,j))) for j, (_, other) in enumerate(keys) if other != key))
                     for i, (role, key) in enumerate(keys))
        peers = tuple(a.ReaderPeerReference2(keys[0][1], 6+i, i, keys[i][1], 2, 0, hd('peer-0-'+str(i)))
                      for i in range(1,len(keys)))
        install = installation or c.InstallKey2(hd('synthetic-approval'), uid(3), hd('binding'), uid(4), uid(5), 1)
        reader = a.ReaderIdentity2(keys[0][1].reader_session_uuid, *(hd(x) for x in (
            'reader', 'installer', 'writer', 'validator', 'approval', 'permissions', 'config')),
            install.writer_epoch_uuid, refs, peers)
        digests = binary_digests or {}
        binaries = a.BinaryManifest2(tuple(a.BinaryReference2(path, digests.get(path, hd(path)),
                       'explicit-synthetic-build', hd('source-'+path), hd('protection-'+path))
                       for path in sorted({o.binary for o in a.OPERATIONS})), hd('binary-review'))
        documents = documents or tuple((role, op.source, hd('decoder-profile'), b'[]', uid(1000+i*10+j))
            for i, (role, _) in enumerate(keys) for j, op in enumerate(a.OPERATIONS))
        requests = tuple(a.CaptureRequest2(capture, next(n for n in refs if n.role == role), source, profile)
                         for role, source, profile, _, capture in documents)
        plan = a.CapturePlan2(uid(2000), install, reader, binaries, requests)
        raw = tuple(item[3] for item in documents)
        return cls(plan, raw, scripts2(plan, raw))

    def collector(self, scripts=None, enabled=True):
        transport = r.DeterministicMockTransport2(self.scripts if scripts is None else scripts)
        runner = r.ReadOnlyCommandRunner2(transport)
        collector = r.FencedReadOnlyCollector2(self.plan, self.plan.digest, self.plan.binaries.digest,
                                              runner, uid(3000), stamp(), enabled=enabled)
        return collector, transport

    def run(self, scripts=None):
        collector, transport = self.collector(scripts)
        return collector.capture(), collector, transport

    def changed_script(self, **changes):
        return (replace(self.scripts[0], **changes), *self.scripts[1:])

    def changed_event(self, index=0, **changes):
        events = list(self.scripts[0].events); events[index] = replace(events[index], **changes)
        return self.changed_script(events=tuple(events))
