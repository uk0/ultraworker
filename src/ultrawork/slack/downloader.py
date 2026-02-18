"""Slack file download and processing for Claude compatibility.

Downloads files and images from Slack threads and converts them into
formats that Claude can process (text, images, base64).

Supports:
- Images (PNG, JPG, GIF, WEBP) -> passed as image files for vision
- PDF files -> read via Claude's native PDF support
- CSV/TSV files -> read as text content
- Text files (TXT, MD, JSON, YAML, etc.) -> read as text content
- ZIP archives -> extracted and each file processed individually
- Other files -> metadata-only summary
"""

import logging
import mimetypes
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import requests
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)

# File categories for Claude compatibility
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
PDF_EXTENSIONS = {".pdf"}
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".tsv",
    ".json",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".sh",
    ".bash",
    ".zsh",
    ".sql",
    ".r",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".env",
    ".log",
    ".css",
    ".scss",
    ".less",
    ".svg",
}
ARCHIVE_EXTENSIONS = {".zip"}

# Max file size for download (50MB)
MAX_FILE_SIZE = 50 * 1024 * 1024
# Max text content length to include inline (100KB)
MAX_TEXT_INLINE = 100 * 1024


class SlackFileInfo:
    """Metadata about a Slack file."""

    def __init__(
        self,
        file_id: str,
        name: str,
        mimetype: str,
        size: int,
        url_private: str,
        filetype: str = "",
        title: str = "",
        permalink: str = "",
        user: str = "",
        timestamp: float = 0,
    ):
        self.file_id = file_id
        self.name = name
        self.mimetype = mimetype
        self.size = size
        self.url_private = url_private
        self.filetype = filetype
        self.title = title or name
        self.permalink = permalink
        self.user = user
        self.timestamp = timestamp

    @property
    def extension(self) -> str:
        """Get file extension (lowercase, with dot)."""
        return Path(self.name).suffix.lower()

    @property
    def category(self) -> str:
        """Categorize file for processing strategy."""
        ext = self.extension
        if ext in IMAGE_EXTENSIONS:
            return "image"
        if ext in PDF_EXTENSIONS:
            return "pdf"
        if ext in TEXT_EXTENSIONS:
            return "text"
        if ext in ARCHIVE_EXTENSIONS:
            return "archive"
        # Check mimetype as fallback
        if self.mimetype.startswith("image/"):
            return "image"
        if self.mimetype == "application/pdf":
            return "pdf"
        if self.mimetype.startswith("text/"):
            return "text"
        return "binary"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "name": self.name,
            "title": self.title,
            "mimetype": self.mimetype,
            "size": self.size,
            "filetype": self.filetype,
            "category": self.category,
            "permalink": self.permalink,
        }


class ProcessedFile:
    """A file that has been downloaded and processed for Claude."""

    def __init__(
        self,
        file_info: SlackFileInfo,
        local_path: Path | None = None,
        text_content: str | None = None,
        base64_content: str | None = None,
        error: str | None = None,
        children: list["ProcessedFile"] | None = None,
    ):
        self.file_info = file_info
        self.local_path = local_path
        self.text_content = text_content
        self.base64_content = base64_content
        self.error = error
        self.children = children or []

    @property
    def is_success(self) -> bool:
        return self.error is None

    @property
    def category(self) -> str:
        return self.file_info.category

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "file_info": self.file_info.to_dict(),
            "success": self.is_success,
            "category": self.category,
        }
        if self.local_path:
            result["local_path"] = str(self.local_path)
        if self.text_content:
            result["text_content_length"] = len(self.text_content)
        if self.error:
            result["error"] = self.error
        if self.children:
            result["children"] = [c.to_dict() for c in self.children]
        return result


class SlackFileDownloader:
    """Downloads and processes files from Slack for Claude consumption."""

    def __init__(
        self,
        token: str | None = None,
        cookie: str | None = None,
        download_dir: str | Path | None = None,
    ):
        """Initialize the downloader.

        Args:
            token: Slack token. Falls back to SLACK_TOKEN or SLACK_BOT_TOKEN env var.
            cookie: Slack cookie for xoxc tokens. Falls back to SLACK_COOKIE env var.
            download_dir: Directory to save downloaded files. Defaults to temp dir.
        """
        self.token = token or os.environ.get("SLACK_TOKEN") or os.environ.get("SLACK_BOT_TOKEN")
        if not self.token:
            raise ValueError(
                "Slack token is required. "
                "Provide token argument or set SLACK_TOKEN environment variable."
            )

        self.cookie = cookie or os.environ.get("SLACK_COOKIE")

        # Build auth headers for HTTP requests
        self._auth_headers: dict[str, str] = {"Authorization": f"Bearer {self.token}"}
        if self.token.startswith("xoxc-") and self.cookie:
            self._auth_headers["Cookie"] = f"d={self.cookie}"

        # Initialize Slack SDK client
        sdk_headers: dict[str, str] = {}
        if self.token.startswith("xoxc-") and self.cookie:
            sdk_headers["Cookie"] = f"d={self.cookie}"
        self.client = WebClient(token=self.token, headers=sdk_headers)

        # Download directory
        if download_dir:
            self.download_dir = Path(download_dir)
            self.download_dir.mkdir(parents=True, exist_ok=True)
            self._temp_dir = None
        else:
            self._temp_dir = tempfile.mkdtemp(prefix="slack_files_")
            self.download_dir = Path(self._temp_dir)

    def extract_files_from_messages(self, messages: list[dict[str, Any]]) -> list[SlackFileInfo]:
        """Extract file metadata from a list of Slack messages.

        Args:
            messages: List of Slack message dicts (from conversations.replies, etc.)

        Returns:
            List of SlackFileInfo objects for all files found in messages.
        """
        files: list[SlackFileInfo] = []

        for msg in messages:
            msg_files = msg.get("files", [])
            for f in msg_files:
                # Skip tombstones (deleted files)
                mode = f.get("mode", "")
                if mode == "tombstone":
                    continue

                file_info = SlackFileInfo(
                    file_id=f.get("id", ""),
                    name=f.get("name", "unknown"),
                    mimetype=f.get("mimetype", "application/octet-stream"),
                    size=f.get("size", 0),
                    url_private=f.get("url_private", "") or f.get("url_private_download", ""),
                    filetype=f.get("filetype", ""),
                    title=f.get("title", ""),
                    permalink=f.get("permalink", ""),
                    user=msg.get("user", ""),
                    timestamp=float(msg.get("ts", 0)),
                )
                if file_info.url_private:
                    files.append(file_info)
                else:
                    logger.warning(f"File {file_info.name} has no download URL, skipping")

        return files

    def get_thread_files(self, channel_id: str, thread_ts: str) -> list[SlackFileInfo]:
        """Get all files from a Slack thread.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            List of SlackFileInfo for all files in the thread.
        """
        try:
            result = self.client.conversations_replies(
                channel=channel_id,
                ts=thread_ts,
                limit=200,
            )
            messages = result.get("messages", [])
            return self.extract_files_from_messages(messages)
        except SlackApiError as e:
            logger.error(f"Failed to get thread files: {e}")
            return []

    def download_file(self, file_info: SlackFileInfo) -> ProcessedFile:
        """Download and process a single file.

        Args:
            file_info: File metadata from Slack.

        Returns:
            ProcessedFile with downloaded content.
        """
        # Check file size
        if file_info.size > MAX_FILE_SIZE:
            return ProcessedFile(
                file_info=file_info,
                error=f"File too large ({file_info.size / 1024 / 1024:.1f}MB, max {MAX_FILE_SIZE / 1024 / 1024:.0f}MB)",
            )

        try:
            # Download the file
            local_path = self._download_to_disk(file_info)

            # Process based on category
            category = file_info.category
            if category == "image":
                return self._process_image(file_info, local_path)
            elif category == "pdf":
                return self._process_pdf(file_info, local_path)
            elif category == "text":
                return self._process_text(file_info, local_path)
            elif category == "archive":
                return self._process_archive(file_info, local_path)
            else:
                return self._process_binary(file_info, local_path)

        except Exception as e:
            logger.error(f"Failed to download/process {file_info.name}: {e}")
            return ProcessedFile(file_info=file_info, error=str(e))

    def download_all(self, files: list[SlackFileInfo]) -> list[ProcessedFile]:
        """Download and process multiple files.

        Args:
            files: List of file metadata from Slack.

        Returns:
            List of ProcessedFile objects.
        """
        results = []
        for file_info in files:
            result = self.download_file(file_info)
            results.append(result)
        return results

    def get_thread_files_processed(self, channel_id: str, thread_ts: str) -> list[ProcessedFile]:
        """Get and process all files from a Slack thread.

        Convenience method combining get_thread_files + download_all.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            List of ProcessedFile objects.
        """
        files = self.get_thread_files(channel_id, thread_ts)
        if not files:
            return []
        return self.download_all(files)

    def format_for_claude(self, processed_files: list[ProcessedFile]) -> str:
        """Format processed files into a text summary for Claude context.

        For text files, includes the content inline.
        For images and PDFs, includes the local file path for tool-based reading.
        For archives, includes extracted file contents.

        Args:
            processed_files: List of processed files.

        Returns:
            Formatted string for inclusion in Claude prompts.
        """
        if not processed_files:
            return ""

        parts = [f"## Thread Attachments ({len(processed_files)} files)\n"]

        for i, pf in enumerate(processed_files, 1):
            fi = pf.file_info
            parts.append(f"### File {i}: {fi.title} ({fi.name})")
            parts.append(f"- Type: {fi.mimetype} | Size: {_format_size(fi.size)}")

            if not pf.is_success:
                parts.append(f"- **Error**: {pf.error}")
                parts.append("")
                continue

            if pf.category == "text" and pf.text_content:
                parts.append(f"\n```{fi.filetype or fi.extension.lstrip('.')}")
                # Truncate very long files
                content = pf.text_content
                if len(content) > MAX_TEXT_INLINE:
                    content = content[:MAX_TEXT_INLINE] + "\n... (truncated)"
                parts.append(content)
                parts.append("```\n")

            elif pf.category == "image" and pf.local_path:
                parts.append(f"- **Image file**: `{pf.local_path}`")
                parts.append("- Use the Read tool to view this image file.\n")

            elif pf.category == "pdf" and pf.local_path:
                parts.append(f"- **PDF file**: `{pf.local_path}`")
                parts.append("- Use the Read tool to view this PDF file.\n")

            elif pf.category == "archive" and pf.children:
                parts.append(f"- Archive contents ({len(pf.children)} files):")
                for child in pf.children:
                    if child.is_success and child.text_content:
                        parts.append(f"\n#### {child.file_info.name}")
                        parts.append(
                            f"```{child.file_info.filetype or child.file_info.extension.lstrip('.')}"
                        )
                        content = child.text_content
                        if len(content) > MAX_TEXT_INLINE:
                            content = content[:MAX_TEXT_INLINE] + "\n... (truncated)"
                        parts.append(content)
                        parts.append("```")
                    elif child.is_success and child.local_path:
                        parts.append(
                            f"- {child.file_info.name}: `{child.local_path}` ({child.category})"
                        )
                    else:
                        parts.append(f"- {child.file_info.name}: {child.error or 'binary file'}")
                parts.append("")

            elif pf.local_path:
                parts.append(f"- **Binary file**: `{pf.local_path}`")
                parts.append(f"- This file type ({fi.mimetype}) cannot be read as text.\n")

        return "\n".join(parts)

    def cleanup(self) -> None:
        """Remove downloaded temporary files."""
        if self._temp_dir and Path(self._temp_dir).exists():
            import shutil

            shutil.rmtree(self._temp_dir, ignore_errors=True)

    # --- Private methods ---

    def _download_to_disk(self, file_info: SlackFileInfo) -> Path:
        """Download a file from Slack to local disk.

        Args:
            file_info: File metadata with download URL.

        Returns:
            Path to downloaded file.

        Raises:
            requests.HTTPError: If download fails.
        """
        response = requests.get(
            file_info.url_private,
            headers=self._auth_headers,
            stream=True,
            timeout=60,
        )
        response.raise_for_status()

        # Create a safe filename
        safe_name = _sanitize_filename(file_info.name)
        local_path = self.download_dir / f"{file_info.file_id}_{safe_name}"

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"Downloaded {file_info.name} -> {local_path}")
        return local_path

    def _process_image(self, file_info: SlackFileInfo, local_path: Path) -> ProcessedFile:
        """Process an image file. Claude can read images directly via the Read tool."""
        return ProcessedFile(
            file_info=file_info,
            local_path=local_path,
        )

    def _process_pdf(self, file_info: SlackFileInfo, local_path: Path) -> ProcessedFile:
        """Process a PDF file. Claude can read PDFs directly via the Read tool."""
        return ProcessedFile(
            file_info=file_info,
            local_path=local_path,
        )

    def _process_text(self, file_info: SlackFileInfo, local_path: Path) -> ProcessedFile:
        """Process a text-based file by reading its content."""
        try:
            content = local_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = local_path.read_text(encoding="latin-1")
            except Exception:
                return ProcessedFile(
                    file_info=file_info,
                    local_path=local_path,
                    error="Could not decode text file",
                )

        return ProcessedFile(
            file_info=file_info,
            local_path=local_path,
            text_content=content,
        )

    def _process_archive(self, file_info: SlackFileInfo, local_path: Path) -> ProcessedFile:
        """Process a ZIP archive by extracting and processing each file."""
        children: list[ProcessedFile] = []

        try:
            with zipfile.ZipFile(local_path, "r") as zf:
                # Extract to a subdirectory
                extract_dir = self.download_dir / f"{file_info.file_id}_extracted"
                extract_dir.mkdir(exist_ok=True)
                zf.extractall(extract_dir)

                for member in zf.namelist():
                    member_path = extract_dir / member
                    if member_path.is_file():
                        child_info = SlackFileInfo(
                            file_id=f"{file_info.file_id}_{member}",
                            name=member,
                            mimetype=mimetypes.guess_type(member)[0] or "application/octet-stream",
                            size=member_path.stat().st_size,
                            url_private="",  # Already downloaded
                            filetype=Path(member).suffix.lstrip("."),
                        )
                        # Process extracted file based on its type
                        category = child_info.category
                        if category == "text":
                            child = self._process_text(child_info, member_path)
                        elif category == "image":
                            child = self._process_image(child_info, member_path)
                        elif category == "pdf":
                            child = self._process_pdf(child_info, member_path)
                        else:
                            child = ProcessedFile(
                                file_info=child_info,
                                local_path=member_path,
                            )
                        children.append(child)

        except zipfile.BadZipFile:
            return ProcessedFile(
                file_info=file_info,
                local_path=local_path,
                error="Invalid or corrupted ZIP file",
            )

        return ProcessedFile(
            file_info=file_info,
            local_path=local_path,
            children=children,
        )

    def _process_binary(self, file_info: SlackFileInfo, local_path: Path) -> ProcessedFile:
        """Process a binary file (no text extraction possible)."""
        return ProcessedFile(
            file_info=file_info,
            local_path=local_path,
        )


def _sanitize_filename(name: str) -> str:
    """Make a filename safe for local filesystem."""
    # Replace problematic characters
    safe = name.replace("/", "_").replace("\\", "_").replace("\0", "")
    # Limit length
    if len(safe) > 200:
        ext = Path(safe).suffix
        safe = safe[: 200 - len(ext)] + ext
    return safe


def _format_size(size: int) -> str:
    """Format file size in human-readable form."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / 1024 / 1024:.1f}MB"


def download_thread_files(
    channel_id: str,
    thread_ts: str,
    token: str | None = None,
    cookie: str | None = None,
    download_dir: str | Path | None = None,
) -> tuple[list[ProcessedFile], str]:
    """Convenience function to download all files from a thread.

    Args:
        channel_id: Slack channel ID
        thread_ts: Thread timestamp
        token: Slack token (optional, uses env var)
        cookie: Slack cookie for xoxc tokens (optional, uses env var)
        download_dir: Where to save files (optional, uses temp dir)

    Returns:
        Tuple of (list of ProcessedFile, formatted text for Claude)
    """
    downloader = SlackFileDownloader(
        token=token,
        cookie=cookie,
        download_dir=download_dir,
    )
    processed = downloader.get_thread_files_processed(channel_id, thread_ts)
    formatted = downloader.format_for_claude(processed)
    return processed, formatted
