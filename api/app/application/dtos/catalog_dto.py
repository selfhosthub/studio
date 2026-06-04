# api/app/application/dtos/catalog_dto.py

"""Unified marketplace catalog-entry DTO (the merged-read contract).

Every catalog package type (workflow / prompt / comfyui / provider) serializes
its merged marketplace read into a single :class:`CatalogEntry` shape, so the
install path keys off it uniformly instead of each type re-diverging.

This module defines the *shape and the derived-bucket predicates only*. It wires
no reads and touches no database - the ``visibility`` / ``operational_status``
columns do not exist until the schema migration, and the RLS-aware merge that
produces these entries is built per type in later phases. Providers are included
in the shape (forward-compatible) but no provider rows flow through it yet.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.domain.common.value_objects import OperationalStatus, Visibility
from app.domain.provider.models import PackageType


class CatalogOrigin(str, Enum):
    """Authored-vs-reference origin of a catalog entry (read-time, not stored).

    Collapses the three real provenances to two: a remote marketplace fetch and
    a super-admin upload of a marketplace JSON file are both
    ``catalog-reference`` (they differ only in transport, which is obsolete);
    super-admin authoring/uploading a custom package is ``managed``. ``managed``
    signals that the super-org actively maintains the package.

    ``Visibility`` governs only the ``managed`` set; ``CatalogTier`` governs only
    ``catalog-reference`` entries.
    """

    CATALOG_REFERENCE = "catalog-reference"
    MANAGED = "managed"


class CatalogTier(str, Enum):
    """Entitlement tier of a catalog-reference entry (deferred axis).

    Naming aligned now so it does not drift: ``basic`` <-> the Community bucket,
    ``advanced`` <-> the Plus bucket. The tier->subscription lookup is future
    work; this only names the values the bucket predicates read.
    """

    BASIC = "basic"
    ADVANCED = "advanced"


class MarketplaceBucket(str, Enum):
    """The three UI buckets - derived predicates over origin/tier/visibility,
    never a stored field."""

    COMMUNITY = "community"
    PLUS = "plus"
    MANAGED = "managed"


class CatalogEntry(BaseModel):
    """One unified marketplace listing entry, regardless of package type.

    ``visibility`` is meaningful only for ``origin=managed``; ``tier`` only for
    ``origin=catalog-reference``. ``operational_status`` is wired for providers
    only (reserved/unwired for the copy-install types).
    """

    id: str = Field(..., description="Stable identifier (slug or local package id)")
    type: PackageType = Field(..., description="Catalog package type")
    origin: CatalogOrigin = Field(..., description="catalog-reference | managed")
    install_ref: str = Field(
        ...,
        description="Catalog ref (catalog-reference) or local package id (managed)",
    )

    visibility: Optional[Visibility] = Field(
        default=None, description="Meaningful only when origin=managed"
    )
    tier: Optional[CatalogTier] = Field(
        default=None, description="Meaningful only when origin=catalog-reference"
    )
    operational_status: Optional[OperationalStatus] = Field(
        default=None, description="Wired for providers only; reserved elsewhere"
    )

    # Display metadata
    name: str
    description: Optional[str] = None
    version: Optional[str] = None
    category: Optional[str] = None

    # Provider-shape forward-compat (no provider rows flow through until Phase 8)
    provider_id: Optional[str] = Field(
        default=None, description="Provider UUID, for linking; provider entries only"
    )

    @property
    def is_community(self) -> bool:
        return (
            self.origin is CatalogOrigin.CATALOG_REFERENCE
            and self.tier is CatalogTier.BASIC
        )

    @property
    def is_plus(self) -> bool:
        return (
            self.origin is CatalogOrigin.CATALOG_REFERENCE
            and self.tier is CatalogTier.ADVANCED
        )

    @property
    def is_managed(self) -> bool:
        return self.origin is CatalogOrigin.MANAGED and self.visibility in (
            Visibility.PUBLIC,
            Visibility.STAGING,
        )

    @property
    def bucket(self) -> Optional[MarketplaceBucket]:
        """The single UI bucket this entry falls in, or ``None`` if it is not
        listable (e.g. a managed ``private`` entry, or a catalog-reference with
        no recognised tier)."""
        if self.is_community:
            return MarketplaceBucket.COMMUNITY
        if self.is_plus:
            return MarketplaceBucket.PLUS
        if self.is_managed:
            return MarketplaceBucket.MANAGED
        return None
