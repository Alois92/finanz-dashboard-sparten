"""Reproduzierbarer Teststarter ausschließlich für die Windows-Sandbox."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
_mkdir = os.mkdir
_mkdtemp = tempfile.mkdtemp


def temp_mkdir(path, mode=0o777, *, dir_fd=None):
    if mode == 0o700 and Path(path).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        mode = 0o777
    return _mkdir(path, mode, dir_fd=dir_fd)


def test_mkdtemp(suffix=None, prefix=None, dir=None):
    if dir is not None and Path(dir) == Path('C:/Users/lblet/dev'):
        dir = tempfile.gettempdir()
    return _mkdtemp(suffix=suffix, prefix=prefix, dir=dir)


if __name__ == '__main__':
    os.mkdir = temp_mkdir
    tempfile.mkdtemp = test_mkdtemp
    with tempfile.TemporaryDirectory(prefix='finanz-n4-suite-') as tmp:
        os.environ['FINANZ_DB'] = str(Path(tmp) / 'wegwerf.db')
        os.environ['FINANZ_BACKUP_ZIEL2'] = ''
        print('FINANZ_DB:', os.environ['FINANZ_DB'], flush=True)
        suite = unittest.TestSuite(unittest.defaultTestLoader.discover('tests', pattern=pattern)
                                   for pattern in (sys.argv[1:] or ['test*.py']))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
