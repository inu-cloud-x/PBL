import ast
import Levenshtein
from pathlib import Path
import build123d as b3d
import numpy as np
from typing import Dict, Any, List
from scipy.spatial.distance import cdist
import networkx as nx
import tokenize
import io

def calculate_l1_similarity(script_a: str, script_b: str) -> float:
    """L1: Script Similarity using AST Normalization and Token-based Jaccard."""
    def get_canonical(code):
        try:
            tree = ast.parse(code)
            from ..hashing.script import NormalizeVariables, StripDocstrings, DataFlowSimplifier
            tree = StripDocstrings().visit(tree)
            tree = DataFlowSimplifier().visit(tree)
            tree = NormalizeVariables().visit(tree)
            return ast.unparse(tree)
        except:
            return code

    canon_a = get_canonical(script_a)
    canon_b = get_canonical(script_b)
    
    # 1. Normalized Levenshtein for code structure
    lev_dist = Levenshtein.distance(canon_a, canon_b)
    max_len = max(len(canon_a), len(canon_b), 1)
    lev_sim = 1.0 - (lev_dist / max_len)
    
    # 2. Token-level Jaccard Similarity (more robust than trigrams)
    def get_tokens(code):
        try:
            tokens = []
            for tok in tokenize.generate_tokens(io.StringIO(code).readline):
                # Ignore whitespace and comments
                if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.COMMENT):
                    tokens.append(tok.string)
            return tokens
        except:
            return code.split()

    tokens_a = get_tokens(canon_a)
    tokens_b = get_tokens(canon_b)
    set_a, set_b = set(tokens_a), set(tokens_b)
    if not set_a and not set_b: return 1.0
    jaccard = len(set_a & set_b) / len(set_a | set_b)
    
    # Weighted average (Jaccard is usually higher for structural equivalence)
    return (lev_sim * 0.3 + jaccard * 0.7)

def calculate_l2_brep_similarity(step_a: Path, step_b: Path) -> float:
    """L2: B-rep Similarity using Face Adjacency Graph and Topology."""
    shape_a = b3d.import_step(str(step_a))
    shape_b = b3d.import_step(str(step_b))
    
    # Simple Topological Comparison (weighted)
    v1, e1, f1 = len(shape_a.vertices()), len(shape_a.edges()), len(shape_a.faces())
    v2, e2, f2 = len(shape_b.vertices()), len(shape_b.edges()), len(shape_b.faces())
    
    topo_score = 1.0 - (
        abs(v1-v2)/(max(v1,v2)+1) + 
        abs(e1-e2)/(max(e1,e2)+1) + 
        abs(f1-f2)/(max(f1,f2)+1)
    ) / 3.0
    
    # Physical Properties Similarity
    vol_sim = 1.0 - abs(shape_a.volume - shape_b.volume) / (max(shape_a.volume, shape_b.volume) + 1e-9)
    area_sim = 1.0 - abs(shape_a.area - shape_b.area) / (max(shape_a.area, shape_b.area) + 1e-9)
    
    return float(np.clip(0.4*topo_score + 0.3*vol_sim + 0.3*area_sim, 0, 1))

def calculate_l3_mesh_similarity(step_a: Path, step_b: Path, n_samples: int = 2048) -> float:
    """L3: Mesh Similarity using Chamfer Distance."""
    shape_a = b3d.import_step(str(step_a))
    shape_b = b3d.import_step(str(step_b))
    
    # Tessellate and Sample Points
    # Fixed parameters for determinism as per 6.3
    mesh_a = shape_a.tessellate(tolerance=0.01, angular_tolerance=0.2)
    mesh_b = shape_b.tessellate(tolerance=0.01, angular_tolerance=0.2)
    
    def get_points(mesh):
        # Extract vertices from build123d mesh structure
        # Use tuple(v) instead of v.to_tuple() to avoid DeprecationWarning
        pts = np.array([tuple(v) for v in mesh[0]])
        if len(pts) > n_samples:
            idx = np.random.choice(len(pts), n_samples, replace=False)
            pts = pts[idx]
        return pts

    pts_a = get_points(mesh_a)
    pts_b = get_points(mesh_b)
    
    # Calculate Chamfer Distance
    dists_a_to_b = cdist(pts_a, pts_b, 'sqeuclidean')
    dists_b_to_a = cdist(pts_b, pts_a, 'sqeuclidean')
    
    chamfer = np.mean(np.min(dists_a_to_b, axis=1)) + np.mean(np.min(dists_b_to_a, axis=1))
    
    return float(1.0 / (1.0 + chamfer))

def calculate_fused_similarity(l1: float, l2: float, l3: float) -> float:
    """L4: Weighted Fusion Similarity."""
    w_script = 0.20
    w_brep = 0.50
    w_mesh = 0.30
    
    return l1 * w_script + l2 * w_brep + l3 * w_mesh

def audit_artifacts(script_a: str, script_b: str, step_a: Path, step_b: Path) -> Dict[str, Any]:
    """Comprehensive 4-layer audit."""
    l1 = calculate_l1_similarity(script_a, script_b)
    l2 = calculate_l2_brep_similarity(step_a, step_b)
    l3 = calculate_l3_mesh_similarity(step_a, step_b)
    fused = calculate_fused_similarity(l1, l2, l3)
    
    status = "DIFFERENT"
    if fused >= 0.85:
        status = "DUPLICATE"
    elif fused >= 0.60:
        status = "SIMILAR"
        
    return {
        "l1_script_sim": l1,
        "l2_brep_sim": l2,
        "l3_mesh_sim": l3,
        "fused_similarity": fused,
        "status": status
    }
