from __future__ import annotations

import argparse
import json

from claims_platform.engine import DurableClaimsPlatformEngine
from claims_platform.models import ClaimRecord, PolicyCoverageClause


def run_demo(auto_approve_limit: float = 5000.0) -> None:
    engine = DurableClaimsPlatformEngine(auto_approve_limit=auto_approve_limit)
    engine.register_clause(
        PolicyCoverageClause(
            clause_id="CLS-TRV-01",
            incident_type="flight_delay",
            max_coverage_amount=2000.0,
            deductible=50.0,
            summary="Flight delay reimbursement up to $2,000",
        )
    )
    engine.register_clause(
        PolicyCoverageClause(
            clause_id="CLS-MED-02",
            incident_type="medical_evacuation",
            max_coverage_amount=25000.0,
            deductible=250.0,
            summary="Emergency medical evacuation up to $25,000",
        )
    )

    low_claim = ClaimRecord(
        claim_id="CLM-DEMO-001",
        policy_id="POL-TRV-900",
        claimant_id="USR-101",
        incident_type="flight_delay",
        requested_amount=400.0,
        description="6-hour flight delay overnight accommodation",
    )
    low_proposal, low_receipt = engine.evaluate_claim(low_claim, idempotency_key="demo-low-1")
    print("[LOW CLAIM]", json.dumps(low_proposal.model_dump(mode="json"), indent=2))
    if low_receipt:
        print("[LOW RECEIPT]", json.dumps(low_receipt.model_dump(mode="json"), indent=2))

    high_claim = ClaimRecord(
        claim_id="CLM-DEMO-002",
        policy_id="POL-TRV-900",
        claimant_id="USR-102",
        incident_type="medical_evacuation",
        requested_amount=12500.0,
        description="Air ambulance evacuation",
    )
    high_proposal, high_receipt = engine.evaluate_claim(high_claim, idempotency_key="demo-high-1")
    print("[HIGH CLAIM INTERRUPT]", json.dumps(high_proposal.model_dump(mode="json"), indent=2))
    if high_receipt is None:
        resumed_receipt = engine.resume_with_signoff(
            claim_id=high_claim.claim_id,
            approved=True,
            handler_id="HANDLER-42",
            idempotency_key="demo-high-signoff-1",
        )
        print("[HIGH RECEIPT RESUMED]", json.dumps(resumed_receipt.model_dump(mode="json"), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Durable HITL Claims Platform CLI Demo"
    )
    parser.add_argument(
        "--auto-approve-limit",
        type=float,
        default=5000.0,
        help="Deterministic backend payout auto-approval limit (default: 5000.0)",
    )
    args = parser.parse_args()
    run_demo(auto_approve_limit=args.auto_approve_limit)


if __name__ == "__main__":
    main()
