import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
import pytest
from core.accounting_engine import AccountingEngine
from core.smart_dialog_engine import SmartDialogEngine

@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix='.db')
    yield path
    os.close(fd)
    try:
        os.unlink(path)
    except PermissionError:
        pass

@pytest.fixture
def engine(db_path):
    return AccountingEngine(db_path)

@pytest.fixture
def dialog_engine(engine):
    return SmartDialogEngine(engine)
