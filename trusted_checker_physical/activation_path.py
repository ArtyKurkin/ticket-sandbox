"""Reviewed manual composition path, OFF by default. No CLI/setup or auto-enable."""
from .authorization import Activation
from .docker_readonly import ReadOnlyDocker
from .io import LinuxIO
from .preflight import HostPreflight
from .inventory import NamespaceInventory
from .installer import PhysicalNetworkInstaller,IndependentNftReadback
from .journal import PhysicalJournal
from .collector import BoundedPhysicalCollector


class ReviewedActivationPath:
    def __init__(self,auth,signed_approval,runtime_approval,endpoint,*,enabled=False):
        self.activation=Activation(auth,enabled=enabled)
        self.activation.approve(signed_approval) # Signature/expiry only, not host I/O.
        self.signed_approval,self.runtime_approval=signed_approval,runtime_approval
        self.io=LinuxIO(self.activation);self.read_io=LinuxIO(self.activation)
        self.docker=ReadOnlyDocker(self.activation,endpoint)
        self.preflight=HostPreflight(self.activation,self.read_io,self.docker)
        self.inventory=NamespaceInventory(self.activation,self.read_io,self.docker)
        self.reader=IndependentNftReadback(self.activation,self.read_io)
    def open_installer(self,journal_path):
        self.activation.check('mutate') # Before even creating a journal file.
        journal=PhysicalJournal(journal_path,self.activation.origin)
        installer=PhysicalNetworkInstaller(self.activation,self.io,self.reader,journal,self.preflight,self.inventory,self.runtime_approval)
        installer.register(self.signed_approval)
        return installer
    def collector(self,installer):
        from trusted_checker_runtime.profiles import require
        self.activation.check('mutate')
        require(type(installer) is PhysicalNetworkInstaller and installer.activation is self.activation,
                'physical_foreign_installer')
        return BoundedPhysicalCollector(self.activation,self.inventory,self.reader,installer.journal)
