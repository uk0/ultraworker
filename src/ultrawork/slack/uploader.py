"""Slack file upload functionality."""

import os
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


class SlackUploader:
    """Upload files to Slack channels and threads."""

    def __init__(self, token: str | None = None):
        """Initialize the uploader.

        Args:
            token: Slack Bot token. If not provided, uses SLACK_BOT_TOKEN env var.
        """
        self.token = token or os.environ.get("SLACK_BOT_TOKEN")
        if not self.token:
            raise ValueError(
                "Slack token is required. "
                "Provide token argument or set SLACK_BOT_TOKEN environment variable."
            )
        self.client = WebClient(token=self.token)

    def upload_file(
        self,
        file_path: str | Path,
        channel_id: str,
        thread_ts: str | None = None,
        title: str | None = None,
        initial_comment: str | None = None,
    ) -> dict:
        """Upload a file to a Slack channel or thread.

        Args:
            file_path: Path to the file to upload
            channel_id: Slack channel ID
            thread_ts: Optional thread timestamp for uploading to a thread
            title: Optional file title (defaults to filename)
            initial_comment: Optional comment to post with the file

        Returns:
            Slack API response dict with file info

        Raises:
            FileNotFoundError: If file doesn't exist
            SlackApiError: If upload fails
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_title = title or path.name

        try:
            # Use files_upload_v2 for better reliability
            response = self.client.files_upload_v2(
                channel=channel_id,
                file=str(path),
                title=file_title,
                initial_comment=initial_comment,
                thread_ts=thread_ts,
            )
            return {
                "ok": response["ok"],
                "file_id": response.get("file", {}).get("id"),
                "file_url": response.get("file", {}).get("permalink"),
                "filename": file_title,
            }
        except SlackApiError as e:
            return {
                "ok": False,
                "error": str(e),
                "error_code": e.response.get("error", "unknown"),
            }

    def upload_content(
        self,
        content: str,
        channel_id: str,
        filename: str,
        thread_ts: str | None = None,
        title: str | None = None,
        initial_comment: str | None = None,
        filetype: str | None = None,
    ) -> dict:
        """Upload text content as a file to Slack.

        Args:
            content: Text content to upload
            channel_id: Slack channel ID
            filename: Name for the file
            thread_ts: Optional thread timestamp
            title: Optional file title
            initial_comment: Optional comment to post with the file
            filetype: Optional file type (e.g., 'python', 'json', 'markdown')

        Returns:
            Slack API response dict with file info
        """
        file_title = title or filename

        try:
            response = self.client.files_upload_v2(
                channel=channel_id,
                content=content,
                filename=filename,
                title=file_title,
                initial_comment=initial_comment,
                thread_ts=thread_ts,
                filetype=filetype,
            )
            return {
                "ok": response["ok"],
                "file_id": response.get("file", {}).get("id"),
                "file_url": response.get("file", {}).get("permalink"),
                "filename": filename,
            }
        except SlackApiError as e:
            return {
                "ok": False,
                "error": str(e),
                "error_code": e.response.get("error", "unknown"),
            }

    def upload_multiple(
        self,
        file_paths: list[Path] | list[str],
        channel_id: str,
        thread_ts: str | None = None,
        initial_comment: str | None = None,
    ) -> list[dict]:
        """Upload multiple files to a Slack channel or thread.

        Args:
            file_paths: List of file paths to upload
            channel_id: Slack channel ID
            thread_ts: Optional thread timestamp
            initial_comment: Optional comment (only for first file)

        Returns:
            List of upload results
        """
        results = []
        for i, file_path in enumerate(file_paths):
            comment = initial_comment if i == 0 else None
            result = self.upload_file(
                file_path=file_path,
                channel_id=channel_id,
                thread_ts=thread_ts,
                initial_comment=comment,
            )
            results.append(result)
        return results


def upload_to_slack(
    file_path: str | Path,
    channel_id: str,
    thread_ts: str | None = None,
    title: str | None = None,
    comment: str | None = None,
    token: str | None = None,
) -> dict:
    """Convenience function for quick file upload.

    Args:
        file_path: Path to the file to upload
        channel_id: Slack channel ID
        thread_ts: Optional thread timestamp
        title: Optional file title
        comment: Optional comment to post with the file
        token: Optional Slack Bot token

    Returns:
        Upload result dict
    """
    uploader = SlackUploader(token=token)
    return uploader.upload_file(
        file_path=file_path,
        channel_id=channel_id,
        thread_ts=thread_ts,
        title=title,
        initial_comment=comment,
    )
