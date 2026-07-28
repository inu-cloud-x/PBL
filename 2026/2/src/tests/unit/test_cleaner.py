from t2c_prov.generation.cleaner import clean_output

def test_clean_output_with_markdown():
    raw = """
Check this out:
```python
import cadquery as cq
result = cq.Workplane("XY").box(10, 10, 10)
```
Hope you like it!
"""
    cleaned = clean_output(raw)
    assert "import cadquery as cq" in cleaned
    assert "result = cq.Workplane(\"XY\").box(10, 10, 10)" in cleaned
    assert "Check this out" not in cleaned

def test_clean_output_missing_imports():
    raw = """
result = cq.Workplane("XY").sphere(5)
"""
    cleaned = clean_output(raw)
    assert "import cadquery as cq" in cleaned
    assert "result =" in cleaned

def test_clean_output_rename_result():
    raw = """
import cadquery as cq
my_box = cq.Workplane("XY").box(1, 2, 3)
"""
    cleaned = clean_output(raw)
    assert "result = my_box" in cleaned
