import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(default="", max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr
    display_name: str


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


from datetime import datetime  # noqa: E402


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str


class TaskIn(BaseModel):
    objective: str = Field(min_length=3, max_length=4000)
    project_id: uuid.UUID | None = None
    file_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)


class TaskSummary(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    project_id: uuid.UUID | None
    created_at: datetime


class SubtaskOut(BaseModel):
    id: uuid.UUID
    position: int
    capability: str
    label: str
    description: str
    tool_id: str | None
    status: str
    depends_on: list[str]
    routing: dict | None = None
    output_preview: str | None = None


class TaskDetail(BaseModel):
    id: uuid.UUID
    objective: str
    status: str
    project_id: uuid.UUID | None
    plan: dict | None
    created_at: datetime
    context_count: int
    tools_used: list[str]
    subtasks: list[SubtaskOut]
    error: dict | None = None


from pydantic import SecretStr, field_validator  # noqa: E402
import re  # noqa: E402


class ToolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    provider: str
    summary: str
    capabilities: list[str]
    context_window: int
    supports_images: bool
    supports_files: bool
    supports_tools: bool
    cost_class: str
    speed_class: str
    requires_key: bool
    status: str = ""  # ready | needs_key | planned, computed per user


class ConnectIn(BaseModel):
    provider: str = Field(pattern=r"^[a-z0-9\-]{2,60}$")
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def _clean(cls, v: SecretStr) -> SecretStr:
        k = v.get_secret_value().strip()
        if not 8 <= len(k) <= 512 or not re.fullmatch(r"[^\s\x00-\x1f]+", k):
            raise ValueError("API keys are 8 to 512 characters with no spaces")
        return SecretStr(k)


class ConnectionOut(BaseModel):
    provider: str
    key_hint: str
    connected_at: datetime
