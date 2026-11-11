import pytest


@pytest.fixture(autouse=True)
def native_test_workspace(request,tmp_path,monkeypatch):
    if request.node.get_closest_marker('native'):
        monkeypatch.chdir(tmp_path)
