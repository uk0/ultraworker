"""Slack registry for channels and users management."""

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ultrawork.models import (
    ChannelInfo,
    ChannelRegistry,
    ChannelType,
    UserInfo,
    UserRegistry,
    UserRole,
    WorkspaceInfo,
)


class SlackRegistry:
    """Manages Slack channel and user registry."""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.registry_dir = self.data_dir / "registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        self.channels_file = self.registry_dir / "channels.yaml"
        self.users_file = self.registry_dir / "users.yaml"
        self.workspace_file = self.registry_dir / "workspace.yaml"

        self._channels: ChannelRegistry | None = None
        self._users: UserRegistry | None = None
        self._workspace: WorkspaceInfo | None = None

    # --- Channel Operations ---

    def get_channels(self) -> ChannelRegistry:
        """Get the channel registry, loading from file if needed."""
        if self._channels is None:
            self._channels = self._load_channels()
        return self._channels

    def _load_channels(self) -> ChannelRegistry:
        """Load channels from YAML file."""
        if not self.channels_file.exists():
            return ChannelRegistry()

        data = yaml.safe_load(self.channels_file.read_text(encoding="utf-8")) or {}
        channels = {}
        for cid, cdata in data.get("channels", {}).items():
            if "type" in cdata:
                cdata["type"] = ChannelType(cdata["type"])
            channels[cid] = ChannelInfo(channel_id=cid, **cdata)

        return ChannelRegistry(
            updated_at=data.get("updated_at", datetime.now()),
            channels=channels,
        )

    def save_channels(self) -> None:
        """Save channels to YAML file."""
        channels = self.get_channels()
        data = {
            "updated_at": channels.updated_at.isoformat(),
            "channels": {
                cid: {
                    "name": c.name,
                    "type": c.type.value,
                    "purpose": c.purpose,
                    "topic": c.topic,
                    "is_monitored": c.is_monitored,
                    "default_workflow": c.default_workflow,
                    "member_count": c.member_count,
                }
                for cid, c in channels.channels.items()
            },
        }
        self.channels_file.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    def sync_channels_from_slack(self, slack_channels: list[dict[str, Any]]) -> int:
        """Sync channels from Slack API response."""
        channels = self.get_channels()
        count = 0

        for ch in slack_channels:
            channel_id = ch.get("id", "")
            if not channel_id:
                continue

            # Determine channel type
            ch_type = ChannelType.PUBLIC
            if ch.get("is_private"):
                ch_type = ChannelType.PRIVATE
            elif ch.get("is_im"):
                ch_type = ChannelType.DM
            elif ch.get("is_mpim"):
                ch_type = ChannelType.MPIM

            # Check if already exists
            existing = channels.get_channel(channel_id)
            is_monitored = existing.is_monitored if existing else False
            default_workflow = existing.default_workflow if existing else "full"

            channels.add_channel(
                ChannelInfo(
                    channel_id=channel_id,
                    name=ch.get("name", ""),
                    type=ch_type,
                    purpose=ch.get("purpose", {}).get("value", ""),
                    topic=ch.get("topic", {}).get("value", ""),
                    is_monitored=is_monitored,
                    default_workflow=default_workflow,
                    member_count=ch.get("num_members", 0),
                )
            )
            count += 1

        self.save_channels()
        return count

    def set_channel_monitored(self, channel_id: str, monitored: bool = True) -> bool:
        """Set whether a channel should be monitored."""
        channels = self.get_channels()
        channel = channels.get_channel(channel_id)
        if not channel:
            return False

        channel.is_monitored = monitored
        channels.add_channel(channel)
        self.save_channels()
        return True

    def get_channel_info(self, channel_id: str) -> ChannelInfo | None:
        """Get channel info by ID."""
        return self.get_channels().get_channel(channel_id)

    def get_channel_by_name(self, name: str) -> ChannelInfo | None:
        """Get channel info by name."""
        return self.get_channels().find_by_name(name)

    # --- User Operations ---

    def get_users(self) -> UserRegistry:
        """Get the user registry, loading from file if needed."""
        if self._users is None:
            self._users = self._load_users()
        return self._users

    def _load_users(self) -> UserRegistry:
        """Load users from YAML file."""
        if not self.users_file.exists():
            return UserRegistry()

        data = yaml.safe_load(self.users_file.read_text(encoding="utf-8")) or {}
        users = {}
        for uid, udata in data.get("users", {}).items():
            if "role" in udata:
                udata["role"] = UserRole(udata["role"])
            users[uid] = UserInfo(user_id=uid, **udata)

        return UserRegistry(
            updated_at=data.get("updated_at", datetime.now()),
            users=users,
        )

    def save_users(self) -> None:
        """Save users to YAML file."""
        users = self.get_users()
        data = {
            "updated_at": users.updated_at.isoformat(),
            "users": {
                uid: {
                    "name": u.name,
                    "display_name": u.display_name,
                    "email": u.email,
                    "role": u.role.value,
                    "team": u.team,
                    "is_bot": u.is_bot,
                    "can_approve": u.can_approve,
                    "timezone": u.timezone,
                }
                for uid, u in users.users.items()
            },
        }
        self.users_file.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    def sync_users_from_slack(self, slack_users: list[dict[str, Any]]) -> int:
        """Sync users from Slack API response."""
        users = self.get_users()
        count = 0

        for user in slack_users:
            user_id = user.get("id", "")
            if not user_id:
                continue

            profile = user.get("profile", {})
            is_bot = user.get("is_bot", False)

            # Check if already exists for preserved fields
            existing = users.get_user(user_id)
            role = existing.role if existing else (UserRole.BOT if is_bot else UserRole.DEVELOPER)
            can_approve = existing.can_approve if existing else False
            team = existing.team if existing else ""

            users.add_user(
                UserInfo(
                    user_id=user_id,
                    name=user.get("name", ""),
                    display_name=profile.get("display_name", ""),
                    email=profile.get("email", ""),
                    role=role,
                    team=team,
                    is_bot=is_bot,
                    can_approve=can_approve,
                    timezone=user.get("tz", ""),
                    avatar_url=profile.get("image_72", ""),
                )
            )
            count += 1

        self.save_users()
        return count

    def set_user_role(self, user_id: str, role: UserRole) -> bool:
        """Set user role."""
        users = self.get_users()
        user = users.get_user(user_id)
        if not user:
            return False

        user.role = role
        users.add_user(user)
        self.save_users()
        return True

    def set_user_can_approve(self, user_id: str, can_approve: bool = True) -> bool:
        """Set whether a user can approve tasks."""
        users = self.get_users()
        user = users.get_user(user_id)
        if not user:
            return False

        user.can_approve = can_approve
        users.add_user(user)
        self.save_users()
        return True

    def get_user_info(self, user_id: str) -> UserInfo | None:
        """Get user info by ID."""
        return self.get_users().get_user(user_id)

    def get_user_by_name(self, name: str) -> UserInfo | None:
        """Get user info by name."""
        return self.get_users().find_by_name(name)

    # --- Workspace Operations ---

    def get_workspace(self) -> WorkspaceInfo | None:
        """Get workspace info."""
        if self._workspace is None and self.workspace_file.exists():
            data = yaml.safe_load(self.workspace_file.read_text(encoding="utf-8")) or {}
            self._workspace = WorkspaceInfo(**data)
        return self._workspace

    def save_workspace(self, workspace: WorkspaceInfo) -> None:
        """Save workspace info."""
        self._workspace = workspace
        self.workspace_file.write_text(
            yaml.dump(workspace.model_dump(), allow_unicode=True), encoding="utf-8"
        )

    # --- Helper Methods ---

    def resolve_user_id(self, user_id_or_name: str) -> str | None:
        """Resolve a user ID or name to a user ID."""
        if user_id_or_name.startswith("U"):
            return user_id_or_name

        user = self.get_user_by_name(user_id_or_name)
        return user.user_id if user else None

    def resolve_channel_id(self, channel_id_or_name: str) -> str | None:
        """Resolve a channel ID or name to a channel ID."""
        if channel_id_or_name.startswith("C"):
            return channel_id_or_name

        channel = self.get_channel_by_name(channel_id_or_name)
        return channel.channel_id if channel else None

    def get_user_display_name(self, user_id: str) -> str:
        """Get display name for a user ID."""
        user = self.get_user_info(user_id)
        if user:
            return user.display_name or user.name
        return user_id

    def get_channel_display_name(self, channel_id: str) -> str:
        """Get display name for a channel ID."""
        channel = self.get_channel_info(channel_id)
        if channel:
            return channel.name
        return channel_id
