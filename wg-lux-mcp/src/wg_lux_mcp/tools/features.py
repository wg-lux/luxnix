from __future__ import annotations

import os
import re
import tempfile
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

SEMANTIC_ID = r"^[a-z][a-z0-9_]*$"
PROVIDER_ID = r"^[a-z][a-z0-9_-]*$"
MAX_SPECIFICATION_BYTES = 1_000_000
ASSESSMENT_STATES = ("verified", "in_progress", "blocked", "not_assessed")
AssessmentStatus = Literal["verified", "in_progress", "blocked", "not_assessed"]


class FeatureResolutionError(RuntimeError):
    """Base class for closed feature-resolution failures."""


class ProviderNotFoundError(FeatureResolutionError):
    pass


class FeatureNotFoundError(FeatureResolutionError):
    pass


class RequirementNotFoundError(FeatureResolutionError):
    pass


class MalformedFeatureStateError(FeatureResolutionError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Evidence(StrictModel):
    kind: str = Field(min_length=1)
    reference: str = Field(min_length=1)
    result: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)


class SourceDocument(StrictModel):
    path: str = Field(min_length=1)
    disposition: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)


class VerificationCommand(StrictModel):
    command: tuple[str, ...] = Field(min_length=1)
    working_directory: str | None = Field(default=None, min_length=1)


class VerificationDefinition(StrictModel):
    kind: Literal["command", "manual"]
    command: tuple[str, ...] | None = None
    commands: tuple[VerificationCommand, ...] | None = None
    instructions: str | None = Field(default=None, min_length=1)
    timeout_seconds: int = Field(default=300, ge=1, le=86_400)

    @model_validator(mode="after")
    def validate_shape(self) -> VerificationDefinition:
        if self.kind == "command" and (self.command is None) == (self.commands is None):
            raise ValueError("command verification requires exactly one of command or commands")
        if self.kind == "manual" and self.instructions is None:
            raise ValueError("manual verification requires instructions")
        return self


class RequirementDefinition(StrictModel):
    id: str = Field(pattern=SEMANTIC_ID)
    category: str = Field(min_length=1)
    title: str = Field(min_length=1)
    acceptance: tuple[str, ...] = Field(min_length=1)
    required: bool = True
    verification: VerificationDefinition


class FeatureSpecification(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str = Field(pattern=SEMANTIC_ID)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    owners: tuple[str, ...] = Field(min_length=1)
    production_critical: bool = True
    source_documents: tuple[SourceDocument, ...] = ()
    invariants: tuple[str, ...] = ()
    definition_of_done: tuple[RequirementDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_ids(self) -> FeatureSpecification:
        ids = tuple(item.id for item in self.definition_of_done)
        if len(ids) != len(set(ids)):
            raise ValueError("requirement IDs must be unique")
        return self


class CurrentWork(StrictModel):
    objective: str = Field(min_length=1)
    scope: tuple[str, ...] = ()
    next: tuple[str, ...] = ()


class ProviderDescriptor(StrictModel):
    kind: Literal["nix", "development"]
    feature_root: Path
    package_store_path: Path | None = None
    drv_path: Path | None = None
    revision: str | None = Field(default=None, min_length=1)
    version: str | None = Field(default=None, min_length=1)
    system_generation: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_nix_provider(self) -> ProviderDescriptor:
        if self.kind == "nix" and self.package_store_path is None:
            raise ValueError("Nix providers require package_store_path")
        if self.kind == "development" and self.package_store_path is not None:
            raise ValueError("development providers cannot claim a package store path")
        return self


class ProviderRegistry(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    providers: dict[str, ProviderDescriptor]

    @field_validator("providers")
    @classmethod
    def validate_provider_ids(
        cls, providers: dict[str, ProviderDescriptor]
    ) -> dict[str, ProviderDescriptor]:
        for provider in providers:
            if re.fullmatch(PROVIDER_ID, provider) is None:
                raise ValueError(f"invalid provider identity: {provider!r}")
        return providers


class FeatureIdentity(StrictModel):
    provider: str = Field(pattern=PROVIDER_ID)
    id: str = Field(pattern=SEMANTIC_ID)


class DeployedSubject(StrictModel):
    provider: str = Field(pattern=PROVIDER_ID)
    feature_id: str = Field(pattern=SEMANTIC_ID)
    nix_store_path: Path | None = None
    drv_path: Path | None = None
    revision: str | None = None
    version: str | None = None
    system_generation: str | None = None


class RequirementAssessmentEvent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    event: Literal["feature.requirement.assessed"] = "feature.requirement.assessed"
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1)
    feature: FeatureIdentity
    requirement_id: str = Field(pattern=SEMANTIC_ID)
    status: AssessmentStatus
    subject: DeployedSubject
    evidence: tuple[Evidence, ...] = ()
    note: str | None = Field(default=None, min_length=1)
    assessed_by: str = Field(min_length=1)
    assessed_at: datetime

    @field_validator("assessed_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("assessed_at must include a timezone")
        return value


class CurrentWorkEvent(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    event: Literal["feature.current_work.updated"] = "feature.current_work.updated"
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1)
    feature: FeatureIdentity
    current_work: CurrentWork
    subject: DeployedSubject
    assessed_by: str = Field(min_length=1)
    assessed_at: datetime


FeatureEvent = Annotated[RequirementAssessmentEvent | CurrentWorkEvent, Field(discriminator="event")]
EVENT_ADAPTER = TypeAdapter(FeatureEvent)


class RequirementProjection(StrictModel):
    status: AssessmentStatus
    note: str | None = None
    assessed_by: str | None = None
    assessed_at: datetime | None = None
    subject: DeployedSubject | None = None


class FeatureProjection(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    feature: FeatureIdentity
    requirements: dict[str, RequirementProjection] = Field(default_factory=dict)
    current_work: CurrentWork | None = None


def _load_mapping(path: Path) -> dict[str, object]:
    if not path.is_file() or path.is_symlink():
        raise MalformedFeatureStateError(f"expected regular file: {path}")
    if path.stat().st_size > MAX_SPECIFICATION_BYTES:
        raise MalformedFeatureStateError(f"feature file exceeds size limit: {path.name}")
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise MalformedFeatureStateError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise MalformedFeatureStateError(f"{path} must contain a string-keyed mapping")
    return cast(dict[str, object], value)


def _atomic_json(path: Path, value: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(value.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_yaml(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(value, handle, sort_keys=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class AssessmentLedger:
    def __init__(self, state_root: Path):
        self.state_root = state_root
        self.events_root = state_root / "events"
        self.projections_root = state_root / "projections"

    def projection_path(self, provider: str, feature_id: str) -> Path:
        return self.projections_root / provider / f"{feature_id}.json"

    def load_projection(self, provider: str, feature_id: str) -> FeatureProjection:
        path = self.projection_path(provider, feature_id)
        if not path.exists():
            return FeatureProjection(feature=FeatureIdentity(provider=provider, id=feature_id))
        try:
            return FeatureProjection.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MalformedFeatureStateError(f"invalid feature projection {path}: {exc}") from exc

    def append(self, event: FeatureEvent) -> Path:
        directory = self.events_root / event.feature.provider / event.feature.id
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = event.assessed_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        path = directory / f"{timestamp}-{event.event_id}.yml"
        payload = yaml.safe_dump(event.model_dump(mode="json"), sort_keys=False)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError as exc:
            if path.read_text(encoding="utf-8") == payload:
                self.rebuild_projection(event.feature.provider, event.feature.id)
                return path
            raise MalformedFeatureStateError(f"conflicting assessment event: {event.event_id}") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self.rebuild_projection(event.feature.provider, event.feature.id)
        return path

    def _events(self, provider: str, feature_id: str) -> list[FeatureEvent]:
        directory = self.events_root / provider / feature_id
        if not directory.exists():
            return []
        events: list[FeatureEvent] = []
        for path in sorted((*directory.glob("*.yml"), *directory.glob("*.yaml"))):
            try:
                events.append(EVENT_ADAPTER.validate_python(_load_mapping(path)))
            except ValueError as exc:
                raise MalformedFeatureStateError(f"invalid assessment event {path}: {exc}") from exc
        return sorted(events, key=lambda item: (item.assessed_at, item.event_id))

    def rebuild_projection(self, provider: str, feature_id: str) -> FeatureProjection:
        requirements: dict[str, RequirementProjection] = {}
        current_work: CurrentWork | None = None
        for event in self._events(provider, feature_id):
            if isinstance(event, RequirementAssessmentEvent):
                requirements[event.requirement_id] = RequirementProjection(
                    status=event.status,
                    note=event.note,
                    assessed_by=event.assessed_by,
                    assessed_at=event.assessed_at,
                    subject=event.subject,
                )
            else:
                current_work = event.current_work
        projection = FeatureProjection(
            feature=FeatureIdentity(provider=provider, id=feature_id),
            requirements=requirements,
            current_work=current_work,
        )
        _atomic_json(self.projection_path(provider, feature_id), projection)
        return projection

    def evidence(
        self, provider: str, feature_id: str, requirement_id: str, offset: int, limit: int
    ) -> tuple[list[dict[str, object]], int]:
        matching = [
            event
            for event in self._events(provider, feature_id)
            if isinstance(event, RequirementAssessmentEvent)
            and event.requirement_id == requirement_id
            and event.evidence
        ]
        rows = [cast(dict[str, object], event.model_dump(mode="json")) for event in matching]
        return rows[offset : offset + limit], len(rows)


class FeatureResolver:
    def __init__(self, registry_path: Path, state_root: Path):
        self.registry_path = registry_path
        self.ledger = AssessmentLedger(state_root)
        try:
            self.registry = ProviderRegistry.model_validate_json(
                registry_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise MalformedFeatureStateError(f"invalid provider registry {registry_path}: {exc}") from exc

    def list_feature_providers(self) -> list[dict[str, object]]:
        return [
            {
                "provider": provider,
                "kind": descriptor.kind,
                "revision": descriptor.revision,
                "version": descriptor.version,
            }
            for provider, descriptor in sorted(self.registry.providers.items())
        ]

    def _provider(self, provider: str) -> ProviderDescriptor:
        try:
            descriptor = self.registry.providers[provider]
        except KeyError as exc:
            raise ProviderNotFoundError(f"unknown deployed feature provider: {provider}") from exc
        if descriptor.kind != "nix":
            raise ProviderNotFoundError(
                f"provider {provider!r} is development-only, not a deployed Nix provider"
            )
        return descriptor

    def _specifications(self, provider: str) -> dict[str, FeatureSpecification]:
        root = self._provider(provider).feature_root
        if not root.is_dir() or root.is_symlink():
            raise MalformedFeatureStateError(f"feature root is unavailable for {provider}: {root}")
        specifications: dict[str, FeatureSpecification] = {}
        for path in sorted((*root.rglob("*.yml"), *root.rglob("*.yaml"))):
            try:
                specification = FeatureSpecification.model_validate(_load_mapping(path))
            except ValueError as exc:
                raise MalformedFeatureStateError(f"malformed feature specification {path}: {exc}") from exc
            if specification.id in specifications:
                raise MalformedFeatureStateError(
                    f"ambiguous feature ID {specification.id!r} for provider {provider}"
                )
            specifications[specification.id] = specification
        return specifications

    def list_features(self, provider: str) -> list[dict[str, object]]:
        return [
            {
                "feature": {"provider": provider, "id": specification.id},
                "name": specification.name,
                "production_critical": specification.production_critical,
            }
            for specification in self._specifications(provider).values()
        ]

    def _specification(self, provider: str, feature_id: str) -> FeatureSpecification:
        try:
            return self._specifications(provider)[feature_id]
        except KeyError as exc:
            raise FeatureNotFoundError(
                f"unknown feature identity: ({provider}, {feature_id})"
            ) from exc

    def get_feature(self, provider: str, feature_id: str) -> dict[str, object]:
        specification = self._specification(provider, feature_id)
        projection = self.ledger.load_projection(provider, feature_id)
        return {
            "feature": {"provider": provider, "id": feature_id},
            "specification": specification.model_dump(mode="json"),
            "current_work": (
                projection.current_work.model_dump(mode="json")
                if projection.current_work is not None
                else None
            ),
        }

    def get_feature_status(self, provider: str, feature_id: str) -> dict[str, object]:
        specification = self._specification(provider, feature_id)
        projection = self.ledger.load_projection(provider, feature_id)
        groups: dict[str, list[str]] = {state: [] for state in ASSESSMENT_STATES}
        for requirement in specification.definition_of_done:
            assessment = projection.requirements.get(requirement.id)
            status = assessment.status if assessment is not None else "not_assessed"
            groups[status].append(requirement.id)
        required_ids = {item.id for item in specification.definition_of_done if item.required}
        if any(item in required_ids for item in groups["blocked"]):
            state = "blocked"
        elif required_ids and required_ids.issubset(groups["verified"]):
            state = "verified"
        elif groups["in_progress"] or groups["verified"]:
            state = "in_progress"
        else:
            state = "not_assessed"
        return {
            "feature": {"provider": provider, "id": feature_id},
            "production_critical": specification.production_critical,
            "state": state,
            "invariants": list(specification.invariants),
            "verified_requirement_ids": groups["verified"],
            "in_progress_requirement_ids": groups["in_progress"],
            "blocked_requirement_ids": groups["blocked"],
            "current_objective": (
                projection.current_work.objective if projection.current_work is not None else None
            ),
            "next_actions": (
                list(projection.current_work.next) if projection.current_work is not None else []
            ),
        }

    def get_requirement(
        self, provider: str, feature_id: str, requirement_id: str
    ) -> dict[str, object]:
        specification = self._specification(provider, feature_id)
        requirement = next(
            (item for item in specification.definition_of_done if item.id == requirement_id), None
        )
        if requirement is None:
            raise RequirementNotFoundError(
                f"unknown requirement identity: ({provider}, {feature_id}, {requirement_id})"
            )
        assessment = self.ledger.load_projection(provider, feature_id).requirements.get(
            requirement_id
        )
        return {
            "feature": {"provider": provider, "id": feature_id},
            "requirement": requirement.model_dump(mode="json"),
            "assessment": assessment.model_dump(mode="json") if assessment else None,
        }

    def get_current_work(self, provider: str, feature_id: str) -> dict[str, object]:
        self._specification(provider, feature_id)
        current_work = self.ledger.load_projection(provider, feature_id).current_work
        return {
            "feature": {"provider": provider, "id": feature_id},
            "current_work": current_work.model_dump(mode="json") if current_work else None,
        }

    def get_feature_evidence(
        self,
        provider: str,
        feature_id: str,
        requirement_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> dict[str, object]:
        if offset < 0 or not 1 <= limit <= 50:
            raise ValueError("offset must be non-negative and limit must be between 1 and 50")
        self.get_requirement(provider, feature_id, requirement_id)
        events, total = self.ledger.evidence(provider, feature_id, requirement_id, offset, limit)
        return {
            "feature": {"provider": provider, "id": feature_id},
            "requirement_id": requirement_id,
            "events": events,
            "page": {
                "offset": offset,
                "limit": limit,
                "returned": len(events),
                "total": total,
                "has_more": offset + len(events) < total,
            },
        }

    def get_deployed_feature_subject(self, provider: str, feature_id: str) -> dict[str, object]:
        self._specification(provider, feature_id)
        descriptor = self._provider(provider)
        return DeployedSubject(
            provider=provider,
            feature_id=feature_id,
            nix_store_path=descriptor.package_store_path,
            drv_path=descriptor.drv_path,
            revision=descriptor.revision,
            version=descriptor.version,
            system_generation=descriptor.system_generation,
        ).model_dump(mode="json")


def deployed_resolver(registry_path: Path, state_root: Path) -> FeatureResolver:
    """Construct only the deterministic deployed resolver; there is no checkout fallback."""
    return FeatureResolver(registry_path, state_root)


def _legacy_timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = datetime.now(UTC)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def migrate_combined_tracker(
    *,
    provider: str,
    source_path: Path,
    specification_root: Path,
    ledger: AssessmentLedger,
    subject: DeployedSubject,
    default_assessor: str = "legacy-feature-migration",
) -> tuple[Path, list[Path]]:
    """Split one legacy combined tracker without dropping assessment evidence."""
    combined = _load_mapping(source_path)
    feature_id = combined.get("id")
    if not isinstance(feature_id, str):
        raise MalformedFeatureStateError(f"combined tracker {source_path} has no feature id")
    combined.pop("tracking", None)
    explicit_work = combined.pop("current_work", None)
    requirements = combined.get("definition_of_done")
    if not isinstance(requirements, list):
        raise MalformedFeatureStateError(f"combined tracker {source_path} has no requirements")
    events: list[FeatureEvent] = []
    for requirement_value in requirements:
        if not isinstance(requirement_value, dict):
            raise MalformedFeatureStateError("legacy requirements must be mappings")
        requirement = cast(dict[str, object], requirement_value)
        assessment_value = requirement.pop("assessment", {})
        if not isinstance(assessment_value, dict):
            raise MalformedFeatureStateError("legacy assessment must be a mapping")
        assessment = cast(dict[str, object], assessment_value)
        status = assessment.get("status", "not_assessed")
        if assessment and status != "not_assessed":
            evidence_value = assessment.get("evidence", [])
            if not isinstance(evidence_value, list):
                raise MalformedFeatureStateError("legacy evidence must be a list")
            evidence = tuple(Evidence.model_validate(item) for item in evidence_value)
            assessed_at = _legacy_timestamp(assessment.get("assessed_at"))
            requirement_id = str(requirement.get("id"))
            event_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"wg-lux:{provider}:{feature_id}:{requirement_id}:{assessed_at.isoformat()}",
            ).hex
            events.append(
                RequirementAssessmentEvent(
                    event_id=event_id,
                    feature=FeatureIdentity(provider=provider, id=feature_id),
                    requirement_id=requirement_id,
                    status=cast(AssessmentStatus, str(status)),
                    subject=subject,
                    evidence=evidence,
                    note=cast(str | None, assessment.get("note")),
                    assessed_by=str(assessment.get("assessed_by") or default_assessor),
                    assessed_at=assessed_at,
                )
            )
    specification = FeatureSpecification.model_validate(combined)
    specification_root.mkdir(parents=True, exist_ok=True)
    specification_path = specification_root / f"{feature_id}.yml"
    _atomic_yaml(
        specification_path,
        cast(dict[str, object], specification.model_dump(mode="json")),
    )
    written = [ledger.append(event) for event in events]
    if explicit_work is not None:
        event = CurrentWorkEvent(
            event_id=uuid.uuid5(
                uuid.NAMESPACE_URL, f"wg-lux:{provider}:{feature_id}:current-work:migration"
            ).hex,
            feature=FeatureIdentity(provider=provider, id=feature_id),
            current_work=CurrentWork.model_validate(explicit_work),
            subject=subject,
            assessed_by=default_assessor,
            assessed_at=datetime(1970, 1, 1, tzinfo=UTC),
        )
        written.append(ledger.append(event))
    return specification_path, written
