"""Registry data models for Slack channels and users."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    """Type of Slack channel."""

    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"
    MPIM = "mpim"  # multi-party IM


class UserRole(str, Enum):
    """Role of a user in the workspace."""

    DEVELOPER = "developer"
    MANAGER = "manager"
    ADMIN = "admin"
    BOT = "bot"
    EXTERNAL = "external"


class ChannelInfo(BaseModel):
    """Information about a Slack channel."""

    channel_id: str
    name: str
    type: ChannelType = ChannelType.PUBLIC
    purpose: str = ""
    topic: str = ""
    is_monitored: bool = False
    default_workflow: Literal["full", "simple"] = "full"
    member_count: int = 0
    created_at: datetime | None = None


class UserInfo(BaseModel):
    """Information about a Slack user."""

    user_id: str
    name: str
    display_name: str = ""
    email: str = ""
    role: UserRole = UserRole.DEVELOPER
    team: str = ""
    is_bot: bool = False
    can_approve: bool = False
    timezone: str = ""
    avatar_url: str = ""


class WorkspaceInfo(BaseModel):
    """Information about the Slack workspace."""

    workspace_id: str
    name: str
    domain: str = ""
    bot_user_id: str = ""


class ChannelRegistry(BaseModel):
    """Registry of all channels."""

    updated_at: datetime = Field(default_factory=datetime.now)
    channels: dict[str, ChannelInfo] = Field(default_factory=dict)

    def add_channel(self, channel: ChannelInfo) -> None:
        """Add or update a channel."""
        self.channels[channel.channel_id] = channel
        self.updated_at = datetime.now()

    def get_channel(self, channel_id: str) -> ChannelInfo | None:
        """Get a channel by ID."""
        return self.channels.get(channel_id)

    def get_monitored_channels(self) -> list[ChannelInfo]:
        """Get all monitored channels."""
        return [c for c in self.channels.values() if c.is_monitored]

    def find_by_name(self, name: str) -> ChannelInfo | None:
        """Find a channel by name."""
        name_clean = name.lstrip("#")
        for channel in self.channels.values():
            if channel.name.lstrip("#") == name_clean:
                return channel
        return None


class UserRegistry(BaseModel):
    """Registry of all users."""

    updated_at: datetime = Field(default_factory=datetime.now)
    users: dict[str, UserInfo] = Field(default_factory=dict)

    def add_user(self, user: UserInfo) -> None:
        """Add or update a user."""
        self.users[user.user_id] = user
        self.updated_at = datetime.now()

    def get_user(self, user_id: str) -> UserInfo | None:
        """Get a user by ID."""
        return self.users.get(user_id)

    def get_approvers(self) -> list[UserInfo]:
        """Get all users with approval permission."""
        return [u for u in self.users.values() if u.can_approve]

    def find_by_name(self, name: str) -> UserInfo | None:
        """Find a user by name or display name."""
        name_lower = name.lower()
        for user in self.users.values():
            if user.name.lower() == name_lower or user.display_name.lower() == name_lower:
                return user
        return None

    def get_by_role(self, role: UserRole) -> list[UserInfo]:
        """Get all users with a specific role."""
        return [u for u in self.users.values() if u.role == role]
