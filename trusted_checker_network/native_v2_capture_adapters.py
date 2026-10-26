"""Pure parsing bridges, gated by the issuing mock collector instance.

No recipe validation, OS provenance upgrade, ownership or authority conversion.
Older descriptors retain their explicit unauthenticated/unrecorded limitations;
the wrapper separately records the new mock artifact/session references.
"""
from dataclasses import dataclass

from . import native_v2_contracts as c
from . import native_v2_capture_contracts as a
from .native_v2_collector import FencedReadOnlyCollector2
from . import native_v2_readback as nft
from . import native_v2_topology as topology
from . import native_v2_topology_schema as provisional
from . import native_v2_native61 as native
from . import native_v2_native61_schema as native_schema


@dataclass(frozen=True, slots=True)
class ParsedCaptureReference2(c._Offline2):
    capture_artifact_digest: str
    capture_validation_digest: str
    decoded_digest: str
    parser_domain: str
    provenance: str = 'mock_capture_reference_only_os_unproven'

    def __post_init__(self):
        c._Offline2.__post_init__(self)
        for value in (self.capture_artifact_digest, self.capture_validation_digest, self.decoded_digest): c._hex(value)
        c._enum(self.parser_domain, ('nft_v2', 'topology_v2_provisional', 'native61_diagnostic'))
        a.require(self.provenance == 'mock_capture_reference_only_os_unproven', 'provenance_invalid')


def _artifact(collector, validation, capture_uuid, source, profile_digest):
    a.require(type(collector) is FencedReadOnlyCollector2, 'boundary_invalid')
    manifest = collector.admit_for_parsing(validation)
    c._uuid(capture_uuid)
    found = tuple(x for x in manifest.artifacts if x.request.capture_uuid == capture_uuid)
    a.require(len(found) == 1, 'missing_source')
    artifact = found[0]
    a.require(artifact.request.source == source and artifact.request.decoder_profile_digest == profile_digest,
              'source_substitution')
    return artifact


def decode_collected_nft2(collector, validation, capture_uuid, profile, context):
    c._typed(profile, nft.NativeFormatProfile2); c._typed(context, nft.ReadbackContext2)
    artifact = _artifact(collector, validation, capture_uuid, 'nft', profile.digest)
    a.require(context.namespace == artifact.request.namespace.key, 'namespace_mismatch')
    manifest = collector.admit_for_parsing(validation)
    a.require(context.installation == manifest.plan.installation and
              profile.nft_binary_digest == artifact.observed_binary.binary_sha256, 'profile_mismatch')
    decoded = nft.decode_native2(artifact.stdout, profile, context)
    return decoded, ParsedCaptureReference2(artifact.digest, validation.digest, decoded.digest, 'nft_v2')


_OLD_SOURCE = (('nft', 'nft'), ('link', 'link'), ('address', 'address'), ('bridge_link', 'bridge_link'),
               ('vlan', 'bridge_vlan'), ('fdb', 'bridge_fdb'), ('route4', 'route4'), ('route6', 'route6'),
               ('rule4', 'rule4'), ('rule6', 'rule6'))


def decode_collected_topology2(collector, validation, profile, expected_capture_plan):
    """Full old-plan coverage is mandatory; parsing never completes topology.

    The old descriptors are independently supplied fixture/capture references.
    Matching them does not turn their offline transport into OS attestation.
    """
    c._typed(profile, provisional.TopologyProfile2)
    c._typed(expected_capture_plan, topology.TopologyCapturePlan2)
    a.require(type(collector) is FencedReadOnlyCollector2, 'boundary_invalid')
    manifest = collector.admit_for_parsing(validation)
    a.require(expected_capture_plan.profile == profile, 'profile_mismatch')
    captures = tuple(x for x in manifest.artifacts if x.request.source != 'nft')
    a.require(len(captures) == len(expected_capture_plan.captures), 'source_coverage_incomplete')
    documents = []; references = []
    for descriptor in expected_capture_plan.captures:
        a.require(descriptor.source in dict(_OLD_SOURCE) and descriptor.source != 'nft', 'source_substitution')
        source = dict(_OLD_SOURCE)[descriptor.source]
        artifact = _artifact(collector, validation, descriptor.capture_uuid, source, profile.digest)
        installation = manifest.plan.installation
        a.require(descriptor.namespace == artifact.request.namespace.key and
                  descriptor.context_uuid == installation.context_uuid and
                  descriptor.approval_digest == installation.approval_digest and
                  descriptor.writer_epoch_uuid == installation.writer_epoch_uuid and
                  descriptor.binary_digest == artifact.observed_binary.binary_sha256 and
                  descriptor.raw_sha256 == artifact.stdout_sha256 and
                  descriptor.raw_byte_count == artifact.stdout_byte_count, 'provenance_mismatch')
        documents.append((artifact.stdout, descriptor)); references.append(artifact)
    decoded = topology.decode_topology_documents2(tuple(documents), profile, expected_capture_plan)
    wrappers = tuple(ParsedCaptureReference2(artifact.digest, validation.digest, value.digest,
                     'topology_v2_provisional') for artifact, value in zip(references, decoded))
    return decoded, wrappers


def decode_collected_native61(collector, validation, capture_uuid, profile, reference,
                              pinned_reference_digest):
    c._typed(profile, native_schema.NativeTopologyProfile61)
    c._typed(reference, native.NativeSourceReference61)
    a.require(reference.digest == pinned_reference_digest, 'pin_mismatch')
    artifact = _artifact(collector, validation, capture_uuid, reference.source, profile.digest)
    a.require(reference.scope_label == artifact.request.namespace.role and
              reference.raw_sha256 == artifact.stdout_sha256 and
              reference.raw_byte_count == artifact.stdout_byte_count, 'provenance_mismatch')
    # Native61 build refs may merely hash version text. They are NOT substituted
    # for the independent BinaryManifest2 binary/source/protection references.
    decoded = native.decode_native_source61(artifact.stdout, profile, reference)
    return decoded, ParsedCaptureReference2(artifact.digest, validation.digest, decoded.digest,
                                          'native61_diagnostic')
