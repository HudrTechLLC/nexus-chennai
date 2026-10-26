"""01_files.sql registers every file stage_files.py places, in the internal store (D-022a)."""

import re
from pathlib import Path

from zetaris.register import statements
from zetaris.stage_files import DEST, LAYOUT

ROOT = Path(__file__).resolve().parents[2]


def test_every_table_points_into_the_staged_layout():
    stmts = statements((ROOT / "zetaris" / "01_files.sql").read_text(encoding="utf-8"))
    tables = [s for s in stmts if s.startswith("CREATE LIGHTNING FILESTORE TABLE")]
    assert len(tables) == 12
    folders = {folder for _, folder in LAYOUT}
    for s in tables:
        path = re.search(r'path "file://([^"]+)"', s).group(1)
        assert path.startswith(DEST + "/") and path[len(DEST) + 1:].split("/")[0] in folders, path
        assert "awsSecretAccessKey" not in s
    dbs = [s for s in stmts if s.startswith("CREATE LIGHTNING DATABASE")]
    assert all(re.fullmatch(r'[^"]*"[A-Za-z0-9 ,.]+"', d) for d in dbs)  # DESCRIBE BY charset
