import threading
import pytest
from multisim_native_mcp.experiments import run_sweep,validate_spec


class FakeHost:
    def __init__(self):self.lock=threading.RLock();self.value=10;self.restored=False
    def call(self,op,args):
        if op=='parameters':return {'parameters':[{'index':1,'value':self.value}]}
        self.value=args['value'];self.restored=self.value==10
    def checkpoint(self):return {'path':'checkpoint','value':self.value}
    def restore(self,c):self.value=c['value'];self.restored=True
    def validate(self,*a):pass
    def run_analysis(self,**a):raise RuntimeError('convergence failure')


def test_failed_trials_restore_original_parameters():
    host=FakeHost()
    r=run_sweep(host,[{'ref':'R1','index':1,'values':[1,2]}],{'analysis':'op'},[{'id':'v','metric':'mean','signal':'V(1)'}])
    assert r['status']=='failed' and len(r['trials'])==2 and r['restored']
    assert host.value==10 and host.restored


def test_cancel_before_first_trial_also_restores():
    host=FakeHost();cancel=threading.Event();cancel.set()
    r=run_sweep(host,[{'ref':'R1','index':1,'values':[1,2]}],{},[{'metric':'mean','signal':'V(1)'}],cancel=cancel)
    assert r['status']=='cancelled' and r['trials']==[] and host.restored


def test_bound_cartesian_product_before_native_changes():
    assert validate_spec([{'ref':r,'index':1,'values':list(range(11))} for r in ['R1','R2']],{},[{'metric':'mean','signal':'V(1)'}],[],None)==121
