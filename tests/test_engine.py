import inspect
import pytest

import claims_platform.engine as engine_module
from claims_platform import (
    ClaimRecord,
    DurableClaimsPlatformEngine,
    PolicyCoverageClause,
    SealedEvaluationIsolationError,
    ToolScopeViolationError,
)


def _build_engine(auto_approve_limit: float = 5000.0) -> DurableClaimsPlatformEngine:
    engine = DurableClaimsPlatformEngine(auto_approve_limit=auto_approve_limit)
    engine.register_clause(
        PolicyCoverageClause(
            clause_id="CLS-TRV-01",
            incident_type="flight_delay",
            max_coverage_amount=2000.0,
            deductible=50.0,
        )
    )
    engine.register_clause(
        PolicyCoverageClause(
            clause_id="CLS-MED-02",
            incident_type="medical_evacuation",
            max_coverage_amount=25000.0,
            deductible=250.0,
        )
    )
    return engine


def test_payout_limit_enforcement_auto_approve_and_interrupt() -> None:
    engine = _build_engine(auto_approve_limit=5000.0)

    low_claim = ClaimRecord(
        claim_id="CLM-101",
        policy_id="POL-TRV-900",
        claimant_id="USR-1",
        incident_type="flight_delay",
        requested_amount=400.0,
    )
    low_proposal, low_receipt = engine.evaluate_claim(low_claim, idempotency_key="k-low")
    assert low_proposal.status == "AUTO_APPROVED"
    assert low_proposal.requires_human_signoff is False
    assert low_receipt is not None
    assert low_receipt.executed is True
    assert low_receipt.approved_amount == 350.0

    high_claim = ClaimRecord(
        claim_id="CLM-102",
        policy_id="POL-TRV-900",
        claimant_id="USR-2",
        incident_type="medical_evacuation",
        requested_amount=12500.0,
    )
    high_proposal, high_receipt = engine.evaluate_claim(high_claim, idempotency_key="k-high")
    assert high_proposal.status == "PENDING_HUMAN_SIGN_OFF"
    assert high_proposal.requires_human_signoff is True
    assert high_receipt is None


def test_idempotent_payout_execution_on_resume() -> None:
    engine = _build_engine(auto_approve_limit=5000.0)
    claim = ClaimRecord(
        claim_id="CLM-201",
        policy_id="POL-TRV-900",
        claimant_id="USR-3",
        incident_type="medical_evacuation",
        requested_amount=8250.0,
    )
    proposal, receipt = engine.evaluate_claim(claim)
    assert proposal.status == "PENDING_HUMAN_SIGN_OFF"
    assert receipt is None
    assert engine.payout_execution_count == 0

    first_receipt = engine.resume_with_signoff(
        claim_id="CLM-201",
        approved=True,
        handler_id="HANDLER-9",
        idempotency_key="idem-signoff-201",
    )
    second_receipt = engine.resume_with_signoff(
        claim_id="CLM-201",
        approved=True,
        handler_id="HANDLER-9",
        idempotency_key="idem-signoff-201",
    )
    assert first_receipt.executed is True
    assert first_receipt.approved_amount == 8000.0
    assert second_receipt.receipt_id == first_receipt.receipt_id
    assert engine.payout_execution_count == 1


def test_sealed_evaluation_isolation() -> None:
    engine = _build_engine()
    with pytest.raises(SealedEvaluationIsolationError):
        engine.assert_not_sealed_eval_path("evaluation/eval_cases.json")

    engine_source = inspect.getsource(engine_module)
    assert "eval_cases.json" not in engine_source


def test_separate_tool_scopes_for_claim_agent_and_handler_copilot() -> None:
    engine = _build_engine()

    assert engine.authorize_tool("claim_agent", "read_claim") is True
    assert engine.authorize_tool("claim_agent", "draft_decision_proposal") is True
    with pytest.raises(ToolScopeViolationError):
        engine.authorize_tool("claim_agent", "prepare_signoff_brief")
    with pytest.raises(ToolScopeViolationError):
        engine.authorize_tool("claim_agent", "execute_payout")

    assert engine.authorize_tool("handler_copilot", "summarize_claim") is True
    assert engine.authorize_tool("handler_copilot", "prepare_signoff_brief") is True
    with pytest.raises(ToolScopeViolationError):
        engine.authorize_tool("handler_copilot", "draft_decision_proposal")
    with pytest.raises(ToolScopeViolationError):
        engine.authorize_tool("handler_copilot", "execute_payout")
