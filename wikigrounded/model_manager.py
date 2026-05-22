from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AvailableModel:
    id: str
    display_name: str


@dataclass
class ModelRoles:
    answer: str = "claude-sonnet-4-6"
    judge: str = "claude-sonnet-4-6"
    debug: str = "claude-sonnet-4-6"


class ModelProvider(Protocol):
    def list_models(self) -> list[AvailableModel]:
        ...


class StaticModelProvider:
    def __init__(self, models: list[dict[str, str]]) -> None:
        self.models = [
            AvailableModel(
                id=item["id"],
                display_name=item.get("display_name", item["id"]),
            )
            for item in models
        ]

    def list_models(self) -> list[AvailableModel]:
        return list(self.models)


class ModelManager:
    def __init__(
        self,
        provider: ModelProvider,
        roles: ModelRoles | None = None,
    ) -> None:
        self.provider = provider
        self.roles = roles or ModelRoles()
        self._cache: list[AvailableModel] | None = None

    def available_models(self, refresh: bool = False) -> list[AvailableModel]:
        if self._cache is None or refresh:
            self._cache = self.provider.list_models()
        return list(self._cache)

    def set_role(self, role: str, model_id: str) -> None:
        if role not in {"answer", "judge", "debug", "all"}:
            raise ValueError(f"Unknown model role: {role}")
        if model_id not in {model.id for model in self.available_models()}:
            raise ValueError(f"Unknown model id: {model_id}")
        if role == "all":
            self.roles.answer = model_id
            self.roles.judge = model_id
            self.roles.debug = model_id
            return
        setattr(self.roles, role, model_id)
