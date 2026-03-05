from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[1]
def test_phase_f_comm_markers() -> None:
    text=(REPO_ROOT/'contract'/'PHASE_F_P0_SAFETY_COMM_CONTRACT_V1.md').read_text(encoding='utf-8')
    assert 'phase_f_p0_safety_comm_contract=ok' in text
    assert 'phase_f_circuit_breaker_comm_path=ok' in text
    assert 'phase_f_hard_stop_comm_path=ok' in text
    assert 'phase_f_manual_reauth_marker_scan=ok' in text
