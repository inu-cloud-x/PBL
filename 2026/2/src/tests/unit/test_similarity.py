import pytest
from pathlib import Path
from t2c_prov.audit.compare import audit_artifacts
import os

# Create temporary directory for test artifacts
TEST_DATA_DIR = Path("data/tests/similarity")
TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)

def create_box_script(size):
    return f"""import cadquery as cq
result = cq.Workplane("XY").box({size}, {size}, {size})
"""

def create_cylinder_script(r, h):
    return f"""import cadquery as cq
result = cq.Workplane("XY").circle({r}).extrude({h})
"""

@pytest.fixture(scope="module")
def setup_artifacts():
    import cadquery as cq
    
    # 1. Base Box (10x10x10)
    script_a = create_box_script(10)
    step_a = TEST_DATA_DIR / "box_10.step"
    res_a = cq.Workplane("XY").box(10, 10, 10)
    res_a.val().exportStep(str(step_a))
    
    # 2. Identical Box with different variable names
    script_b = """import cadquery as cq
my_box = cq.Workplane("XY").box(10, 10, 10)
result = my_box
"""
    step_b = TEST_DATA_DIR / "box_10_copy.step"
    res_a.val().exportStep(str(step_b)) # Same geometry
    
    # 3. Slightly different Box (11x11x11) - SIMILAR
    script_c = create_box_script(11)
    step_c = TEST_DATA_DIR / "box_11.step"
    res_c = cq.Workplane("XY").box(11, 11, 11)
    res_c.val().exportStep(str(step_c))
    
    # 4. Completely different - Cylinder
    script_d = create_cylinder_script(5, 20)
    step_d = TEST_DATA_DIR / "cyl_5_20.step"
    res_d = cq.Workplane("XY").circle(5).extrude(20)
    res_d.val().exportStep(str(step_d))
    
    return {
        "a": (script_a, step_a),
        "b": (script_b, step_b),
        "c": (script_c, step_c),
        "d": (script_d, step_d)
    }

def test_identical_artifacts(setup_artifacts):
    """Test Case 1: Identical geometry, different script naming -> DUPLICATE"""
    a = setup_artifacts["a"]
    b = setup_artifacts["b"]
    
    results = audit_artifacts(a[0], b[0], a[1], b[1])
    print(f"\nIdentical Match Results: {results}")
    
    assert results["status"] == "DUPLICATE"
    assert results["l1_script_sim"] > 0.9 # Normalized name should match
    assert results["fused_similarity"] > 0.95

def test_similar_artifacts(setup_artifacts):
    """Test Case 2: Minor parameter change (10mm -> 11mm) -> SIMILAR"""
    a = setup_artifacts["a"]
    c = setup_artifacts["c"]
    
    results = audit_artifacts(a[0], c[0], a[1], c[1])
    print(f"\nSimilar Match Results: {results}")
    
    assert results["status"] == "SIMILAR"
    assert 0.60 <= results["fused_similarity"] < 0.95

def test_different_artifacts(setup_artifacts):
    """Test Case 3: Different topology (Box vs Cylinder) -> DIFFERENT"""
    a = setup_artifacts["a"]
    d = setup_artifacts["d"]
    
    results = audit_artifacts(a[0], d[0], a[1], d[1])
    print(f"\nDifferent Match Results: {results}")
    
    assert results["status"] == "DIFFERENT"
    assert results["fused_similarity"] < 0.60
