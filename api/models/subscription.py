"""
Subscription models - Client packages and quota management
"""

from pydantic import BaseModel, Field, computed_field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID


class PackageTemplate(BaseModel):
    """Pre-defined package configuration"""
    id: UUID
    name: str

    # Entra configuration
    entra_packages: int = 6
    entra_domains_per_package: int = 2
    entra_inboxes_per_domain: int = 52

    # Google configuration
    google_packages: int = 5
    google_domains_per_package: int = 5
    google_inboxes_per_domain: int = 3

    # Calculated totals
    total_domains: int
    total_inboxes: int

    monthly_price: Optional[float] = None
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class SubscriptionBase(BaseModel):
    """Base subscription fields"""
    # Entra configuration
    entra_packages: int = Field(default=6, ge=0, description="Number of Entra orders")
    entra_domains_per_package: int = Field(default=2, ge=1)
    entra_inboxes_per_domain: int = Field(default=52, ge=1)

    # Google configuration
    google_packages: int = Field(default=5, ge=0, description="Number of Google orders")
    google_domains_per_package: int = Field(default=5, ge=1)
    google_inboxes_per_domain: int = Field(default=3, ge=1)

    # Spare capacity target
    spare_ratio: float = Field(default=0.15, ge=0, le=1, description="Target spare capacity ratio")

    notes: Optional[str] = None


class SubscriptionCreate(SubscriptionBase):
    """Create a new subscription"""
    client_id: UUID
    package_template_id: Optional[UUID] = None


class SubscriptionUpdate(BaseModel):
    """Update subscription fields"""
    # Entra configuration
    entra_packages: Optional[int] = Field(default=None, ge=0)
    entra_domains_per_package: Optional[int] = Field(default=None, ge=1)
    entra_inboxes_per_domain: Optional[int] = Field(default=None, ge=1)

    # Google configuration
    google_packages: Optional[int] = Field(default=None, ge=0)
    google_domains_per_package: Optional[int] = Field(default=None, ge=1)
    google_inboxes_per_domain: Optional[int] = Field(default=None, ge=1)

    spare_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    notes: Optional[str] = None
    status: Optional[Literal["active", "paused", "cancelled"]] = None

    # For change tracking
    change_reason: Optional[str] = None
    changed_by: Optional[str] = None


class Subscription(SubscriptionBase):
    """Full subscription model with all fields"""
    id: UUID
    client_id: UUID
    package_template_id: Optional[UUID] = None
    package_template_name: Optional[str] = None  # Joined from package_templates

    status: str = "active"
    started_at: datetime
    cancelled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def entra_domains(self) -> int:
        """Total Entra domains"""
        return self.entra_packages * self.entra_domains_per_package

    @computed_field
    @property
    def entra_inboxes(self) -> int:
        """Total Entra inboxes quota"""
        return self.entra_domains * self.entra_inboxes_per_domain

    @computed_field
    @property
    def google_domains(self) -> int:
        """Total Google domains"""
        return self.google_packages * self.google_domains_per_package

    @computed_field
    @property
    def google_inboxes(self) -> int:
        """Total Google inboxes quota"""
        return self.google_domains * self.google_inboxes_per_domain

    @computed_field
    @property
    def total_domains(self) -> int:
        """Total domains quota"""
        return self.entra_domains + self.google_domains

    @computed_field
    @property
    def total_inboxes(self) -> int:
        """Total inboxes quota"""
        return self.entra_inboxes + self.google_inboxes

    @computed_field
    @property
    def target_spare_inboxes(self) -> int:
        """Target spare inbox count based on ratio"""
        return int(self.total_inboxes * self.spare_ratio)

    class Config:
        from_attributes = True


class SubscriptionWithUsage(Subscription):
    """Subscription with current usage statistics"""
    # Current inventory counts
    current_active_domains: int = 0
    current_active_inboxes: int = 0
    current_warming_inboxes: int = 0
    current_spare_inboxes: int = 0
    current_flagged_inboxes: int = 0

    @computed_field
    @property
    def domains_used_percent(self) -> float:
        """Percentage of domain quota used"""
        if self.total_domains == 0:
            return 0
        return round((self.current_active_domains / self.total_domains) * 100, 1)

    @computed_field
    @property
    def inboxes_used_percent(self) -> float:
        """Percentage of inbox quota used"""
        if self.total_inboxes == 0:
            return 0
        return round((self.current_active_inboxes / self.total_inboxes) * 100, 1)

    @computed_field
    @property
    def domains_remaining(self) -> int:
        """Remaining domains to quota"""
        return max(0, self.total_domains - self.current_active_domains)

    @computed_field
    @property
    def inboxes_remaining(self) -> int:
        """Remaining inboxes to quota"""
        return max(0, self.total_inboxes - self.current_active_inboxes)

    @computed_field
    @property
    def spare_status(self) -> str:
        """Status of spare capacity: 'healthy', 'low', 'critical'"""
        if self.target_spare_inboxes == 0:
            return "healthy"
        ratio = self.current_spare_inboxes / self.target_spare_inboxes
        if ratio >= 0.8:
            return "healthy"
        elif ratio >= 0.5:
            return "low"
        return "critical"


class SubscriptionChange(BaseModel):
    """Record of a subscription change"""
    id: UUID
    subscription_id: UUID
    change_type: str  # 'created', 'upgrade', 'downgrade', 'modify', 'cancelled'

    previous_entra_packages: Optional[int] = None
    previous_google_packages: Optional[int] = None
    new_entra_packages: Optional[int] = None
    new_google_packages: Optional[int] = None

    reason: Optional[str] = None
    changed_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ApplyTemplateRequest(BaseModel):
    """Request to apply a package template to a subscription"""
    package_template_id: UUID
    change_reason: Optional[str] = None
    changed_by: Optional[str] = None
