"""Default OFF authorization checked before *any* host/daemon/kernel I/O."""
import platform
import time
from contextlib import contextmanager
from contextvars import ContextVar
from trusted_checker_runtime.profiles import require
from .contracts import PhysicalApproval


class Activation:
    def __init__(self,auth,*,enabled=False,offline=False,clock=time.time,monotonic=time.monotonic):
        require(type(enabled) is bool and type(offline) is bool,'physical_activation_flag_invalid')
        self.auth,self.enabled,self.offline,self.clock,self.monotonic=auth,enabled,offline,clock,monotonic
        self.approval=None
        self._batches={}
        self._recovery_read=ContextVar('physical_recovery_read',default=False)
    def approve(self,signed):
        approval=self.auth.verify(signed,'approval',PhysicalApproval)
        require(approval.created_at<=self.clock()<approval.expires_at,'physical_approval_expired')
        self.approval=approval
        return approval
    @property
    def origin(self):return 'offline_simulation' if self.offline else 'physical_linux'
    def check(self,permission,*,recovery=False):
        require(self.enabled,'physical_backend_disabled')
        require(self.offline or platform.system()=='Linux','physical_linux_only')
        a=self.approval
        require(type(a) is PhysicalApproval and a.dedicated_vm is True,'physical_approval_missing')
        require(a.permission=='install_and_collect' if permission=='mutate' else
                a.permission in ('readonly','install_and_collect'),'physical_permission_missing')
        if not (recovery or (permission=='read' and self._recovery_read.get())):
            require(a.created_at<=self.clock()<a.expires_at,'physical_approval_expired')
        return a

    @contextmanager
    def recovery_reads(self,enabled):
        token=self._recovery_read.set(enabled)
        try:yield
        finally:self._recovery_read.reset(token)

    def _issue_batch(self,identifier,payload,absolute):
        """Trusted installer only, after durable dispatch; not a request API."""
        from .installer import IssuedBatch
        require(identifier not in self._batches,'physical_batch_already_issued')
        batch=IssuedBatch(identifier,payload,absolute)
        self._batches[identifier]=batch;return batch

    def consume_batch(self,batch,budget):
        from .installer import IssuedBatch
        require(type(batch) is IssuedBatch and self._batches.get(batch.identifier) is batch and
                batch.absolute==budget.absolute,'physical_batch_not_issued')
        del self._batches[batch.identifier]
        return batch.payload


class Deadline:
    def __init__(self,absolute,clock=time.time,monotonic=time.monotonic):
        from trusted_checker_runtime.contracts import stamp
        stamp(absolute);self.absolute,self.clock,self.monotonic=absolute,clock,monotonic
        self.last=clock();require(self.last<absolute,'physical_deadline_expired')
        self.end=monotonic()+absolute-self.last;self.timings={}
    def remaining(self,cap=3.0):
        now=self.clock();require(now>=self.last,'physical_clock_rollback');self.last=now
        left=min(self.absolute-now,self.end-self.monotonic(),cap)
        require(left>0,'physical_deadline_expired');return left
    def record(self,stage,started):
        self.observe(stage,started)
        self.remaining()
    def observe(self,stage,started):
        elapsed=max(0,self.monotonic()-started)
        value=self.timings.setdefault(stage,{'count':0,'total_seconds':0.0,'max_seconds':0.0})
        value['count']+=1;value['total_seconds']+=elapsed;value['max_seconds']=max(value['max_seconds'],elapsed)
