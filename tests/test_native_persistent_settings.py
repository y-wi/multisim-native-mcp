import shutil
from pathlib import Path

import pytest

from multisim_native_mcp.bridge import sha256
from multisim_native_mcp.paths import RESOURCE_DIR
from multisim_native_mcp.service import EditorService

pytestmark=pytest.mark.native


def test_document_settings_save_source_reopen_partial_update_and_reset(tmp_path):
    source=tmp_path/'电路.ms14'
    shutil.copy2(RESOURCE_DIR/'assets'/'blank14.3.ms14',source)
    host=EditorService()
    try:
        host.open_copy(str(source));initial_hash=sha256(source)
        initial=host.configure_interactive(persist=True)
        assert initial['automatic']=={'time_step':True,'max_time_step':True}
        before=host.call('simulationSettingsText')
        configured=host.configure_interactive(time_step=.002,max_time_step=.001,real_time=False,persist=True)
        assert configured['configuration']=={'time_step':.002,'max_time_step':.001,'real_time':False}
        assert sha256(source)==initial_hash and not configured['saved_to_file']
        host.configure_interactive(reset=True,persist=True)
        # All numeric analysis definitions and unrelated solver fields survive a round trip.
        assert host.call('simulationSettingsText').rstrip()==before.rstrip()
        host.configure_interactive(time_step=.01,max_time_step=.01)
        saved=host.configure_interactive(time_step=.002,max_time_step=.001,real_time=False,
                                         persist=True,save_to_source=True)
        assert saved['saved_to_file'] and saved['save']['verification']['simulation_settings_preserved']
        assert sha256(source)!=initial_hash and sha256(Path(saved['save']['backup']))==initial_hash
        assert not host.configure_interactive()['configured']
        host.close();host.open_copy(str(source))
        reopened=host.configure_interactive(persist=True)
        assert reopened['configuration']=={'time_step':.002,'max_time_step':.001,'real_time':False}
        assert not host.configure_interactive()['configured']
        partial=host.configure_interactive(time_step=.0005,persist=True)
        assert partial['configuration']=={'time_step':.0005,'max_time_step':.001,'real_time':False}
        reset=host.configure_interactive(reset=True,persist=True,save_to_source=True)
        assert reset['automatic']=={'time_step':True,'max_time_step':True}
        host.close();host.open_copy(str(source))
        assert host.call('simulationSettingsText').rstrip()==before.rstrip()
    finally:host.close()
