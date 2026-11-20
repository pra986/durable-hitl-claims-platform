from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field


class PolicyCoverageClause(BaseModel):
    clause_id: str
    incident_type: str
    max_coverage_amount: float = Field(gt=0)
    deductible: float = Field(default=0.0, ge=0)
    excluded: bool = False
    summary: str = ""


class ClaimRecord(BaseModel):
    claim_id: str
    policy_id: str
    claimant_id: str
    incident_type: str
    requested_amount: float = Field(gt=0)
    currency: str = "USD"
    description: str = ""
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ClaimDecisionProposal(BaseModel):
    proposal_id: str
    claim_id: str
    clause_id: str
    proposed_payout: float = Field(ge=0)
    recommended_action: Literal["APPROVE", "DENY", "ESCALATE"]
    rationale: str
    requires_human_signoff: bool = False
    status: Literal[
        "PROPOSED",
        "AUTO_APPROVED",
        "PENDING_HUMAN_SIGN_OFF",
        "APPROVED",
        "REJECTED",
    ] = "PROPOSED"


class PayoutApprovalReceipt(BaseModel):
    receipt_id: str
    claim_id: str
    proposal_id: str
    idempotency_key: str
    approved_amount: float = Field(ge=0)
    currency: str = "USD"
    approval_mode: Literal["AUTO_APPROVED", "HUMAN_SIGNED_OFF", "REJECTED"]
    approved_by: str
    executed: bool
    executed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
