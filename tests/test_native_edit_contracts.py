from pathlib import Path

import pytest
from PIL import Image, ImageChops

from multisim_native_mcp.service import EditorService, NativeEditError

pytestmark=pytest.mark.native


def test_anchor_value_labels_frames_analysis_and_rollback(tmp_path):
    h=EditorService()
    try:
        h.create('Native edit contracts')
        for name,ref,x,y,value in [('DC_POWER','V1',180,180,12),('RESISTOR_VIRTUAL','R1',360,180,1000),('RESISTOR_VIRTUAL','R2',540,180,1000),('GROUND','0',180,360,None)]:
            args={'name':name,'ref':ref,'x':x,'y':y,'anchor':'pin','pin':'1'}
            if value is not None:args['parameters']=[{'index':1,'value':value}]
            placed=h.edit('place',args)
            assert placed['placement']['anchor']=='pin'
            assert placed['placement']['actual']=={'x':x,'y':y}
            assert next(p for p in placed['component']['pins'] if p['name']=='1')['x']==x
        for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]:
            h.edit('wire',{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}})
        for ref in ['R1','R2']:h.edit('transform',{'ref':ref,'angle':90})
        h.edit('setParameter',{'ref':'R1','index':1,'expression':'2.2k'})
        value=next(l for l in h.call('componentLabels',{'ref':'R1'})['labels'] if l['kind']=='value')
        assert value['text']=='2.2kΩ'
        c=next(c for c in h.call('circuitState')['components'] if c['ref']=='R1')
        assert all(l['center']['x']>0 and l['center']['y']>0 for l in c['labels'])
        h.edit('setParameter',{'ref':'R1','index':1,'expression':'1k'})
        label_state=lambda:[(c['ref'],[(l['kind'],l['text'],l['center']) for l in c['labels']]) for c in h.call('circuitState')['components']]
        before=label_state()
        for _ in range(2):
            result=h.run_analysis('op')
            assert not result['native_result']['failed']
            assert result['native_result']['error_count']==0 and result['native_result']['errors']==[]
            assert next(v for v in result['vectors'] if v['name']=='I(V1)')['last']==pytest.approx(-.006,abs=1e-10)
            assert label_state()==before
        for frame,name in [(True,'framed-before'),(False,'clean'),(True,'framed-after')]:
            h.export_image(str(tmp_path/(name+'.png')),show_frame=frame,show_grid=False)
            assert label_state()==before
        with Image.open(tmp_path/'framed-before.png') as a,Image.open(tmp_path/'framed-after.png') as b,Image.open(tmp_path/'clean.png') as clean:
            assert ImageChops.difference(a,b).getbbox() is None
            assert ImageChops.difference(a,clean).getbbox() is not None
            assert clean.convert('RGB').getpixel((0,0))==(255,255,255)
        h.edit('moveLabel',{'ref':'R1','kind':'value','x':450,'y':270})
        label=next(l for l in h.call('componentLabels',{'ref':'R1'})['labels'] if l['kind']=='value')
        assert label['center']==pytest.approx({'x':450,'y':270},abs=1)
        output=tmp_path/'labels.ms14';h.save_copy(str(output));h.close();h.open_copy(str(output))
        saved=next(l for l in h.call('componentLabels',{'ref':'R1'})['labels'] if l['kind']=='value')
        assert saved['center']==pytest.approx(label['center'],abs=1)
        h.edit('move',{'ref':'R2','dx':9,'dy':0})
        snapshot=h.call('components')['components']
        with pytest.raises(NativeEditError) as error:h.edit('move',{'ref':'MISSING','dx':9,'dy':0})
        assert not error.value.details['handles_invalidated']
        assert h.call('components')['components']==snapshot
        ops=[{'operation':'move','arguments':{'ref':ref,'dx':9,'dy':0}} for ref in ['R2','MISSING']]
        for atomic,delta in [(True,0),(False,9)]:
            with pytest.raises(NativeEditError) as error:h.batch(ops,atomic=atomic)
            details=error.value.details
            assert details['handles_invalidated'] and details['rollback_scope']==('batch' if atomic else 'failed_operation')
            old=next(c for c in snapshot if c['ref']=='R2')
            new=next(c for c in details['state']['components'] if c['ref']=='R2')
            assert new['transform'][4]==pytest.approx(old['transform'][4]+delta)
    finally:h.close()
