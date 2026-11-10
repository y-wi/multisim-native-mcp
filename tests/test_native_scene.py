from pathlib import Path
import pytest
from PIL import Image
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_native_scene_parameters_labels_and_high_resolution_export(tmp_path):
    h=EditorService()
    try:
        h.create('Scene API divider')
        page=h.call('sheets')[0]
        assert (page['width'],page['height'])==(960,720)
        assert page['bounds']['right']==960 and page['units_per_inch']==96
        search=h.call('librarySearch',{'query':'Resistor1_1.0k','limit':2})
        assert search['results'][0]['Family_Name']=='3D_VIRTUAL'
        filtered=h.call('librarySearch',{'query':'RESISTOR_VIRTUAL','family':'RESISTOR','group':'Basic','limit':10})
        assert all(r['Family_Name']=='RESISTOR' and r['Group_Name']=='Basic' for r in filtered['results'])
        specs=[('DC_POWER','V1',108,108,12),('RESISTOR_VIRTUAL','R1',306,108,1000),('RESISTOR_VIRTUAL','R2',504,108,1000),('GROUND','0',108,306,None)]
        placed=h.batch([{'operation':'place','arguments':{'name':name,'ref':ref,'x':x,'y':y,**({'parameters':[{'index':1,'value':value}]} if value is not None else {})}} for name,ref,x,y,value in specs],include_state=True)
        assert len(placed['state']['components'])==4
        resistor=next(c for c in placed['state']['components'] if c['ref']=='R1')
        assert next(p for p in resistor['parameters'] if p['index']==1)['name']=='resistance'
        h.batch([{'operation':'wire','arguments':{'source':{'ref':a,'pin':ap},'target':{'ref':b,'pin':bp}}} for a,ap,b,bp in [('V1','1','R1','1'),('R1','2','R2','1'),('R2','2','V1','2'),('V1','2','0','1')]])
        checked=h.netlist();assert checked['handles_invalidated'] and len(checked['state']['components'])==4
        assert not h.netlist()['handles_invalidated']
        ids={c['ref']:c['id'] for c in h.call('components')['components']}
        h.edit('setParameter',{'ref':'R2','index':1,'expression':'1k'})
        assert not h.netlist()['handles_invalidated']
        h.edit('transform',{'ref':'R1','angle':90})
        pins=h.call('components')['components']
        label=h.edit('moveLabel',{'ref':'R1','x':450,'y':80})['labels'][0]
        assert label['center']==pytest.approx({'x':450,'y':80},abs=1)
        assert h.call('components')['components']==pins
        assert {c['ref']:c['id'] for c in pins}==ids
        assert not h.netlist()['handles_invalidated']
        analysis=h.run_analysis()
        current=next(v for v in analysis['vectors'] if v['name']=='I(V1)')
        assert current['last']==pytest.approx(-.006,abs=1e-10) and current['unit']=='A'
        assert 'I(V1) [A]' in Path(analysis['csv_path']).read_text(encoding='utf-8-sig')
        state=h.call('circuitState')
        image=h.export_image(str(tmp_path/'high-resolution.png'),dpi=192,region={'left':80,'top':60,'right':640,'bottom':400})
        assert (image['width'],image['height'])==(1120,680)
        assert h.call('circuitState')==state
        with Image.open(image['path']) as rendered:
            assert rendered.info['dpi'][0]==pytest.approx(192,abs=.1)
            assert any(b>r+40 and b>g+40 for r,g,b in rendered.convert('RGB').get_flattened_data())
        h.save_copy(str(tmp_path/'scene.ms14'))
        h.close();h.open_copy(str(tmp_path/'scene.ms14'))
        assert h.call('componentLabels',{'ref':'R1'})['labels'][0]['center']==pytest.approx(label['center'],abs=1)
    finally:h.close()


def test_off_page_routing_and_fitted_export(tmp_path):
    h=EditorService()
    try:
        h.create('Off-page geometry')
        first=h.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R1','x':3000,'y':4000})
        assert first['warnings'][0]['code']=='outside_page'
        h.edit('place',{'name':'RESISTOR_VIRTUAL','ref':'R2','x':3300,'y':4200})
        for operation in ['wire','connectEndpoint']:
            link=h.edit(operation,{'source':{'ref':'R1','pin':'1' if operation=='wire' else '2'},'target':{'ref':'R2','pin':'1' if operation=='wire' else '2'}})
            for end,index in [('source',0),('target',-1)]:assert link['points'][index]=={k:link[end][k] for k in ('x','y')}
        with pytest.raises(ValueError,match='outside the page'):h.export_image(str(tmp_path/'blank.png'))
        assert not (tmp_path/'blank.png').exists()
        before=h.call('circuitState')
        image=h.export_image(str(tmp_path/'fitted.png'),dpi=192,fit_content=True)
        assert image['width']<1200 and image['height']<1000
        assert h.call('circuitState')==before
        with Image.open(image['path']) as rendered:assert any(b>r+40 for r,g,b in rendered.convert('RGB').get_flattened_data())
        output=tmp_path/'cropped-image-original-sheet.ms14'
        h.save_copy(str(output));h.close();h.open_copy(str(output))
        reopened=h.call('circuitState')
        assert reopened['page']['width']==960 and reopened['page']['height']==720
        assert reopened['content_bounds']['right']>reopened['page']['width']
        assert reopened['content_bounds']['bottom']>reopened['page']['height']
        h.edit('addText',{'text':'Native sheet extent','x':3456,'y':3996})
        content=h.call('circuitState')['content_bounds']
        width,height=content['right']+36,content['bottom']+36
        h.batch([{'operation':'sheetSize','arguments':{'width':width,'height':height}}])
        output=tmp_path/'fitted-sheet.ms14'
        h.save_copy(str(output));h.close();h.open_copy(str(output))
        reopened=h.call('circuitState');page=reopened['page'];content=reopened['content_bounds']
        assert (page['width'],page['height'])==(width,height)
        assert content['left']>=0 and content['top']>=0
        assert content['right']<=width-36 and content['bottom']<=height-36
        for wire in reopened['wires']:
            for end,index in [('source',0),('target',-1)]:
                assert wire['points'][index]=={k:wire[end][k] for k in ('x','y')}
        image=h.export_image(str(tmp_path/'saved-whole-sheet.png'))
        assert image['off_page_components']==[]
        assert (image['width'],image['height'])==(width,height)
    finally:h.close()
