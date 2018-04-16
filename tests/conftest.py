import inspect
from pathlib import Path
import pytest
import sys


# Set up the testing environment to have hermes in its path. Hacky. TODO
current_dir = Path(inspect.stack()[0].filename).parent
project_dir = current_dir / '..'
if not (project_dir / 'Pipfile').exists():
    raise Exception('conftest.py could not configure PYTHONPATH')  # uhoh :(
sys.path.append(str(project_dir))
print(sys.path)


from fixtures.timeaccount import *  # noqa: E402


@pytest.fixture(autouse=True)
def add_doctest_fixtures(doctest_namespace, complex_account):
    doctest_namespace['account'] = complex_account
