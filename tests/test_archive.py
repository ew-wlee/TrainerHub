from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from trainerhub.core.archive import ArchiveError, UnsafeArchive, extract, is_archive, sniff


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


def test_sniff_detects_zip_and_exe(tmp_path: Path) -> None:
    zipped = _zip(tmp_path / "a.zip", {"readme.txt": b"hi"})
    assert sniff(zipped) == "zip"
    assert is_archive(zipped)

    exe = tmp_path / "t.exe"
    exe.write_bytes(b"MZ\x90\x00")
    assert sniff(exe) == "exe"
    assert not is_archive(exe)


def test_extract_writes_files(tmp_path: Path) -> None:
    zipped = _zip(tmp_path / "a.zip", {"folder/trainer.exe": b"MZ", "readme.txt": b"hi"})
    out = tmp_path / "out"
    files = extract(zipped, out)
    assert {path.name for path in files} == {"trainer.exe", "readme.txt"}
    assert (out / "folder" / "trainer.exe").exists()


@pytest.mark.parametrize("member", ["../evil.txt", "/abs/evil.txt", "C:/evil.txt", "a/../../evil.txt"])
def test_zip_slip_is_rejected(tmp_path: Path, member: str) -> None:
    zipped = _zip(tmp_path / "evil.zip", {member: b"x"})
    with pytest.raises(UnsafeArchive):
        extract(zipped, tmp_path / "out")


def test_non_archive_raises(tmp_path: Path) -> None:
    plain = tmp_path / "file.bin"
    plain.write_bytes(b"not an archive")
    with pytest.raises(ArchiveError):
        extract(plain, tmp_path / "out")
