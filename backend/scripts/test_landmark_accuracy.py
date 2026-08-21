import sys
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from app.services.kis_engine import kis_engine
from app.services.encyclopedic_store import encyclopedic_store
from app.algorithms.concept_decomposition import decompose_query_concepts

def diagnose() -> None:
    lines = []
    kis_engine.initialize()
    encyclopedic_store.load_all()

    query = "motorcyclists near Ben Thanh Market"
    
    # 1. Check entity match
    matched = encyclopedic_store.match_entities_in_query(query)
    enriched_q, visual_cues = encyclopedic_store.ground_and_expand_query(query)

    lines.append("=== QUERY DIAGNOSTIC ===")
    lines.append(f"Query:        {query}")
    lines.append(f"Matched LMs:  {[m['matched_phrase'] for m in matched]}")
    lines.append(f"Visual Cues:  {visual_cues}")
    lines.append(f"Enriched Q:   {enriched_q}")

    # 2. Compare Search with/without landmark visual prompt enrichment
    res_raw, _ = kis_engine.search_with_metrics(query, top_k=5)
    lines.append("\n--- Standard Search (Raw) ---")
    for r in res_raw:
        lines.append(f"  {r['video_id']}_{r['frame_id']} | r_score={r['r_score']} | time={r['timestamp']}s")

    # 3. Search with Landmark Visual Cues Augmented
    if matched:
        lm_data = matched[0]["data"]
        canon_en = lm_data.get("canonical_en", "")
        cues_str = " ".join(lm_data.get("keywords", [])[:5])
        augmented_query = f"{query}, {canon_en}, {cues_str}"
        res_aug, _ = kis_engine.search_with_metrics(augmented_query, top_k=5)
        lines.append(f"\n--- Augmented Landmark Search: '{augmented_query}' ---")
        for r in res_aug:
            lines.append(f"  {r['video_id']}_{r['frame_id']} | r_score={r['r_score']} | time={r['timestamp']}s")

    out_text = "\n".join(lines)
    print(out_text)
    Path("landmark_diag.txt").write_text(out_text, encoding="utf-8")

if __name__ == "__main__":
    diagnose()
