import pytest
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_native_operations_beyond_previous_quotas(tmp_path):
    host=EditorService();source=tmp_path/'unrestricted.ms14'
    try:
        host.create('Unrestricted native checks',str(source))
        host.batch([{'operation':'place','arguments':{'name':name,'ref':ref,'x':x,'y':y,**({'parameters':[{'index':1,'value':value}]} if value is not None else {})}}
                    for name,ref,x,y,value in [('DC_POWER','V1',108,108,12),('RESISTOR_VIRTUAL','R1',306,108,1000),('RESISTOR_VIRTUAL','R2',504,108,1000),('GROUND','0',108,306,None)]])
        host.batch([{'operation':'wire','arguments':{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}}}
                    for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]])
        batch=host.batch([{'operation':'setParameter','arguments':{'ref':'R2','index':1,'value':1000+n}} for n in range(150)])
        assert len(batch['results'])==150
        result=host.run_analysis('tran',step=2,stop=102)
        assert result['vectors'][0]['last']>=102
        host.edit('sheetSize',{'width':12000,'height':12000})
        host.configure_wiring(autowire_on_move=False,connect_touching=False)
        host.edit('move',{'ref':'R2','dx':100001,'dy':0})
        host.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R3','x':600,'y':400})
        rotated=host.edit('transform',{'ref':'R3','angle':37.5})
        import math
        delta=math.degrees(math.atan2(rotated['after'][1],rotated['after'][0])-math.atan2(rotated['before'][1],rotated['before'][0]))
        assert abs((delta+180)%360-180)==pytest.approx(37.5,abs=.001)
        saved=host.save_source();assert saved['verification']['passed'] and not saved['page_check']['passed']
        image=host.export_image(str(tmp_path/'high-dpi.png'),dpi=960,region={'left':100400,'top':0,'right':100600,'bottom':400})
        assert image['width']>0
    finally:host.close()
