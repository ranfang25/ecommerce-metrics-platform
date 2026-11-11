import os
import pytest
import duckdb
from src.common import ROOT
from src.make_fixture import generate
from src.pipeline import run
from src.metrics_service import published


@pytest.fixture(scope='session')
def build():
    if os.environ.get('ECOM_TEST_OUTPUT'):
        output=ROOT/os.environ['ECOM_TEST_OUTPUT']
        _,meta=published(output)
        return output,meta
    if not (ROOT/'tests/fixtures/events.parquet').exists(): generate()
    meta=run(ROOT/'config/settings.demo.yml')
    return ROOT/'data/demo_build',meta


@pytest.fixture
def con(build):
    db,_=published(build[0])
    connection=duckdb.connect(str(db),read_only=True)
    yield connection
    connection.close()


@pytest.fixture
def app(build,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('ECOM_OUTPUT',str(build[0]))
    return AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
