from __future__ import annotations

import stat
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath

from tools.build_university import validate_and_compile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "example-university-archive"
SLUG = "example-university"
MEMBERS = [
    f"{SLUG}/university.json",
    f"{SLUG}/calendars.json",
    f"{SLUG}/README.md",
    f"{SLUG}/departments/EX.json",
]


def build_example_archive(destination: Path) -> None:
    """Package the text-only fixture using the documented deterministic contract."""
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in MEMBERS:
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, (FIXTURE / name).read_bytes())


class ExampleArchiveFixtureTests(unittest.TestCase):
    def test_fixture_has_safe_import_layout_and_valid_source_data(self) -> None:
        fixture_files = [
            path.relative_to(FIXTURE).as_posix()
            for path in FIXTURE.rglob("*")
            if path.is_file()
        ]
        self.assertCountEqual(fixture_files, MEMBERS)

        with tempfile.TemporaryDirectory() as temporary:
            archive_path = Path(temporary) / f"{SLUG}.zip"
            build_example_archive(archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(archive.namelist(), MEMBERS)
                for member in archive.infolist():
                    path = PurePosixPath(member.filename)
                    self.assertEqual(path.parts[0], SLUG)
                    self.assertNotIn("..", path.parts)
                    self.assertFalse(path.is_absolute())
                    self.assertFalse(stat.S_ISLNK(member.external_attr >> 16))
                    self.assertEqual(member.date_time, (1980, 1, 1, 0, 0, 0))

                archive.extractall(temporary)
                catalog = validate_and_compile(Path(temporary) / SLUG)

        self.assertEqual(catalog["university"]["slug"], SLUG)
        self.assertEqual(len(catalog["departments"]), 1)
        self.assertEqual(len(catalog["courses"]), 1)


if __name__ == "__main__":
    unittest.main()
