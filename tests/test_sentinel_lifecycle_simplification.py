import pytest
import os


def test_sentinel_lifecycle_simplification():
    """RED phase test: Verify sentinel.py lifecycle simplification patterns.
    
    This test SHOULD FAIL with CURRENT code because:
    - process_manager IS imported
    - OpenVikingManager IS used
    - global manager variable IS present
    - shutil.which("openviking-server") IS checked
    
    After simplification (GREEN phase), this test SHOULD PASS.
    """
    # Path to sentinel.py - at project root, not src/
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))
    sentinel_path = os.path.join(project_root, "sentinel.py")
    
    assert os.path.exists(sentinel_path), f"File {sentinel_path} not found"
    
    with open(sentinel_path, "r", encoding="utf-8") as f:
        sentinel_code = f.read()
    
    # Assertions for what should NOT exist after simplification
    # These WILL FAIL with the current code (RED phase)
    assert "import process_manager" not in sentinel_code, \
        "Should not import process_manager (server subprocess management)"
    assert "from process_manager" not in sentinel_code, \
        "Should not import from process_manager"
    assert "OpenVikingManager" not in sentinel_code, \
        "Should not use OpenVikingManager - use embedded SyncOpenViking via OpenVikingClient instead"
    assert "global manager" not in sentinel_code, \
        "Should not have global manager variable for server lifecycle"
    assert 'shutil.which("openviking-server")' not in sentinel_code, \
        "Should not check for external openviking-server binary"
    assert 'has_standalone_server' not in sentinel_code, \
        "Should not have standalone server detection logic"
    assert "health_check()" not in sentinel_code, \
        "Should not have server health check logic"
    assert "manager.start()" not in sentinel_code, \
        "Should not call manager.start() - no subprocess to start"
    assert "manager.stop()" not in sentinel_code, \
        "Should not call manager.stop() - no subprocess to stop"
    
    # Assertion for what SHOULD exist (already true - will pass even now)
    assert "OpenVikingClient(data_path=" in sentinel_code, \
        "Should use OpenVikingClient with data_path parameter for embedded SyncOpenViking"
