"""Testlauf im Windows-Sandbox-Token mit vererbten Verzeichnisrechten.

Python 3.12 setzt bei mkdir(0700) eine eigene Windows-DACL, die den
Sandbox-Token ausschließt. Nur temporäre Testverzeichnisse erhalten deshalb
die Rechte ihres bereits freigegebenen Elternverzeichnisses.
"""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


def temporaere_rechte():
    if os.name == 'nt':
        original = os.mkdir
        temp_root = pathlib.Path(tempfile.gettempdir()).resolve()

        def mkdir(path, mode=0o777, *, dir_fd=None):
            resolved = pathlib.Path(path).resolve()
            if mode == 0o700 and resolved.is_relative_to(temp_root):
                mode = 0o777
            return original(path, mode, dir_fd=dir_fd)

        os.mkdir = mkdir


def main():
    root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / 'tests'))
    temporaere_rechte()
    # Einige Alttests importieren DB_PATH einmal und wechseln später nur die
    # Umgebungsvariable. Auch diese gemeinsame Testbasis muss je Lauf frisch sein.
    with tempfile.TemporaryDirectory(prefix='finanz-p20-suite-') as tmp:
        with patch.dict(os.environ, {'FINANZ_DB': str(pathlib.Path(tmp) / 'suite.db')}):
            suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern=sys.argv[1] if len(sys.argv) > 1 else 'test*.py')
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
