"""Tests for Slack file downloader module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from ultrawork.slack.downloader import (
    ProcessedFile,
    SlackFileDownloader,
    SlackFileInfo,
    _format_size,
    _sanitize_filename,
)


class TestSlackFileInfo:
    def test_extension_extraction(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="report.csv", mimetype="text/csv", size=100, url_private="https://x"
        )
        assert info.extension == ".csv"

    def test_extension_uppercase(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="photo.PNG", mimetype="image/png", size=100, url_private="https://x"
        )
        assert info.extension == ".png"

    def test_category_image(self) -> None:
        for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
            info = SlackFileInfo(
                file_id="F1",
                name=f"file{ext}",
                mimetype=f"image/{ext.lstrip('.')}",
                size=100,
                url_private="https://x",
            )
            assert info.category == "image", f"Expected image for {ext}"

    def test_category_pdf(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="doc.pdf",
            mimetype="application/pdf",
            size=100,
            url_private="https://x",
        )
        assert info.category == "pdf"

    def test_category_text(self) -> None:
        for ext in [".csv", ".txt", ".json", ".yaml", ".py", ".md"]:
            info = SlackFileInfo(
                file_id="F1",
                name=f"file{ext}",
                mimetype="text/plain",
                size=100,
                url_private="https://x",
            )
            assert info.category == "text", f"Expected text for {ext}"

    def test_category_archive(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="archive.zip",
            mimetype="application/zip",
            size=100,
            url_private="https://x",
        )
        assert info.category == "archive"

    def test_category_binary_fallback(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="data.bin",
            mimetype="application/octet-stream",
            size=100,
            url_private="https://x",
        )
        assert info.category == "binary"

    def test_category_image_by_mimetype(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="file_no_ext",
            mimetype="image/png",
            size=100,
            url_private="https://x",
        )
        assert info.category == "image"

    def test_category_text_by_mimetype(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="file_no_ext",
            mimetype="text/plain",
            size=100,
            url_private="https://x",
        )
        assert info.category == "text"

    def test_to_dict(self) -> None:
        info = SlackFileInfo(
            file_id="F1",
            name="test.csv",
            mimetype="text/csv",
            size=1024,
            url_private="https://x",
            title="Test CSV",
        )
        d = info.to_dict()
        assert d["file_id"] == "F1"
        assert d["name"] == "test.csv"
        assert d["title"] == "Test CSV"
        assert d["category"] == "text"
        assert d["size"] == 1024

    def test_title_defaults_to_name(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="test.csv", mimetype="text/csv", size=100, url_private="https://x"
        )
        assert info.title == "test.csv"


class TestProcessedFile:
    def test_success_file(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="test.txt", mimetype="text/plain", size=100, url_private="https://x"
        )
        pf = ProcessedFile(file_info=info, text_content="hello")
        assert pf.is_success
        assert pf.category == "text"

    def test_error_file(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="test.txt", mimetype="text/plain", size=100, url_private="https://x"
        )
        pf = ProcessedFile(file_info=info, error="Download failed")
        assert not pf.is_success

    def test_to_dict_with_content(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="test.txt", mimetype="text/plain", size=100, url_private="https://x"
        )
        pf = ProcessedFile(file_info=info, text_content="hello world")
        d = pf.to_dict()
        assert d["success"]
        assert d["text_content_length"] == 11

    def test_to_dict_with_error(self) -> None:
        info = SlackFileInfo(
            file_id="F1", name="test.txt", mimetype="text/plain", size=100, url_private="https://x"
        )
        pf = ProcessedFile(file_info=info, error="Failed")
        d = pf.to_dict()
        assert not d["success"]
        assert d["error"] == "Failed"


class TestExtractFilesFromMessages:
    @patch.object(SlackFileDownloader, "__init__", lambda self, **kw: None)
    def _make_downloader(self) -> SlackFileDownloader:
        d = SlackFileDownloader.__new__(SlackFileDownloader)
        d.token = "xoxc-test"
        d.cookie = None
        d._auth_headers = {}
        d.client = MagicMock()
        d.download_dir = Path(tempfile.mkdtemp())
        d._temp_dir = str(d.download_dir)
        return d

    def test_extracts_files_from_messages(self) -> None:
        d = self._make_downloader()
        messages = [
            {
                "user": "U123",
                "ts": "1234567890.000000",
                "text": "Here is a file",
                "files": [
                    {
                        "id": "F001",
                        "name": "data.csv",
                        "mimetype": "text/csv",
                        "size": 1024,
                        "url_private": "https://files.slack.com/data.csv",
                        "filetype": "csv",
                        "title": "Data CSV",
                        "permalink": "https://slack.com/files/F001",
                    }
                ],
            }
        ]
        files = d.extract_files_from_messages(messages)
        assert len(files) == 1
        assert files[0].file_id == "F001"
        assert files[0].name == "data.csv"
        assert files[0].category == "text"

    def test_skips_tombstone_files(self) -> None:
        d = self._make_downloader()
        messages = [
            {
                "user": "U123",
                "ts": "1234567890.000000",
                "files": [
                    {
                        "id": "F001",
                        "name": "deleted.csv",
                        "mimetype": "text/csv",
                        "size": 0,
                        "mode": "tombstone",
                        "url_private": "",
                    }
                ],
            }
        ]
        files = d.extract_files_from_messages(messages)
        assert len(files) == 0

    def test_skips_files_without_url(self) -> None:
        d = self._make_downloader()
        messages = [
            {
                "user": "U123",
                "ts": "1234567890.000000",
                "files": [
                    {
                        "id": "F001",
                        "name": "nourl.csv",
                        "mimetype": "text/csv",
                        "size": 1024,
                    }
                ],
            }
        ]
        files = d.extract_files_from_messages(messages)
        assert len(files) == 0

    def test_handles_messages_without_files(self) -> None:
        d = self._make_downloader()
        messages = [{"user": "U123", "ts": "1234567890.000000", "text": "No files here"}]
        files = d.extract_files_from_messages(messages)
        assert len(files) == 0

    def test_multiple_files_in_message(self) -> None:
        d = self._make_downloader()
        messages = [
            {
                "user": "U123",
                "ts": "1234567890.000000",
                "files": [
                    {
                        "id": "F001",
                        "name": "photo.png",
                        "mimetype": "image/png",
                        "size": 2048,
                        "url_private": "https://files.slack.com/photo.png",
                    },
                    {
                        "id": "F002",
                        "name": "report.pdf",
                        "mimetype": "application/pdf",
                        "size": 4096,
                        "url_private": "https://files.slack.com/report.pdf",
                    },
                ],
            }
        ]
        files = d.extract_files_from_messages(messages)
        assert len(files) == 2
        assert files[0].category == "image"
        assert files[1].category == "pdf"


class TestFormatForClaude:
    @patch.object(SlackFileDownloader, "__init__", lambda self, **kw: None)
    def _make_downloader(self) -> SlackFileDownloader:
        d = SlackFileDownloader.__new__(SlackFileDownloader)
        d.token = "xoxc-test"
        return d

    def test_empty_files(self) -> None:
        d = self._make_downloader()
        assert d.format_for_claude([]) == ""

    def test_text_file_inline(self) -> None:
        d = self._make_downloader()
        info = SlackFileInfo(
            file_id="F1",
            name="data.csv",
            mimetype="text/csv",
            size=50,
            url_private="https://x",
            filetype="csv",
        )
        pf = ProcessedFile(file_info=info, text_content="col1,col2\na,b")
        result = d.format_for_claude([pf])
        assert "col1,col2" in result
        assert "data.csv" in result

    def test_image_file_path(self) -> None:
        d = self._make_downloader()
        info = SlackFileInfo(
            file_id="F1",
            name="photo.png",
            mimetype="image/png",
            size=2048,
            url_private="https://x",
        )
        pf = ProcessedFile(file_info=info, local_path=Path("/tmp/photo.png"))
        result = d.format_for_claude([pf])
        assert "/tmp/photo.png" in result
        assert "Image file" in result

    def test_pdf_file_path(self) -> None:
        d = self._make_downloader()
        info = SlackFileInfo(
            file_id="F1",
            name="doc.pdf",
            mimetype="application/pdf",
            size=4096,
            url_private="https://x",
        )
        pf = ProcessedFile(file_info=info, local_path=Path("/tmp/doc.pdf"))
        result = d.format_for_claude([pf])
        assert "/tmp/doc.pdf" in result
        assert "PDF file" in result

    def test_error_file(self) -> None:
        d = self._make_downloader()
        info = SlackFileInfo(
            file_id="F1",
            name="big.bin",
            mimetype="application/octet-stream",
            size=999999999,
            url_private="https://x",
        )
        pf = ProcessedFile(file_info=info, error="File too large")
        result = d.format_for_claude([pf])
        assert "File too large" in result


class TestHelpers:
    def test_sanitize_filename_basic(self) -> None:
        assert _sanitize_filename("hello.txt") == "hello.txt"

    def test_sanitize_filename_slashes(self) -> None:
        assert "/" not in _sanitize_filename("path/to/file.txt")

    def test_sanitize_filename_long(self) -> None:
        long_name = "a" * 300 + ".txt"
        result = _sanitize_filename(long_name)
        assert len(result) <= 200

    def test_format_size_bytes(self) -> None:
        assert _format_size(500) == "500B"

    def test_format_size_kb(self) -> None:
        assert _format_size(2048) == "2.0KB"

    def test_format_size_mb(self) -> None:
        assert _format_size(5 * 1024 * 1024) == "5.0MB"


class TestProcessText:
    def test_reads_utf8_file(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("Hello, World!")
            f.flush()
            path = Path(f.name)

        try:
            d = SlackFileDownloader.__new__(SlackFileDownloader)
            info = SlackFileInfo(
                file_id="F1",
                name="test.txt",
                mimetype="text/plain",
                size=13,
                url_private="https://x",
            )
            result = d._process_text(info, path)
            assert result.is_success
            assert result.text_content == "Hello, World!"
        finally:
            path.unlink()

    def test_reads_korean_text(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("한국어 텍스트 테스트")
            f.flush()
            path = Path(f.name)

        try:
            d = SlackFileDownloader.__new__(SlackFileDownloader)
            info = SlackFileInfo(
                file_id="F1",
                name="korean.txt",
                mimetype="text/plain",
                size=30,
                url_private="https://x",
            )
            result = d._process_text(info, path)
            assert result.is_success
            assert "한국어" in (result.text_content or "")
        finally:
            path.unlink()


class TestProcessArchive:
    def test_processes_zip_with_text_files(self) -> None:
        import zipfile as zf

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "test.zip"
            with zf.ZipFile(zip_path, "w") as z:
                z.writestr("readme.txt", "Hello from zip!")
                z.writestr("data.csv", "a,b,c\n1,2,3")

            d = SlackFileDownloader.__new__(SlackFileDownloader)
            d.download_dir = Path(tmpdir)

            info = SlackFileInfo(
                file_id="F1",
                name="test.zip",
                mimetype="application/zip",
                size=zip_path.stat().st_size,
                url_private="https://x",
            )
            result = d._process_archive(info, zip_path)
            assert result.is_success
            assert len(result.children) == 2
            assert any("Hello from zip!" in (c.text_content or "") for c in result.children)

    def test_handles_bad_zip(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as f:
            f.write(b"not a zip file")
            path = Path(f.name)

        try:
            d = SlackFileDownloader.__new__(SlackFileDownloader)
            d.download_dir = path.parent

            info = SlackFileInfo(
                file_id="F1",
                name="bad.zip",
                mimetype="application/zip",
                size=14,
                url_private="https://x",
            )
            result = d._process_archive(info, path)
            assert not result.is_success
            assert "Invalid" in (result.error or "")
        finally:
            path.unlink()
