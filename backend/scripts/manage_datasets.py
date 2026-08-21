"""CLI tool to manage and optimize traffic and cultural datasets for AIC26."""

import json
import argparse
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

DATASETS = {
    "traffic": DATA_DIR / "traffic_signs_vietnam.json",
    "cultural": DATA_DIR / "cultural_entities.json",
    "actions": DATA_DIR / "action_mappings.json",
    "vehicles": DATA_DIR / "vehicles_and_transport.json",
}

def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def optimize_dataset(name: str):
    path = DATASETS.get(name)
    if not path or not path.exists():
        print(f"[ERROR] Dataset {name} not found at {path}")
        return

    data = load_json(path)
    if not data:
        return

    print(f"Optimizing '{name}' dataset...")
    original_len = len(data)

    if isinstance(data, list):
        # Deduplicate list of dicts (like action_mappings or traffic_signs)
        # Convert to a stable string representation for uniqueness
        unique_items = []
        seen = set()
        
        # Determine sorting key
        sort_key = None
        if name == "traffic":
            sort_key = lambda x: x.get("code", "")
        elif name == "actions":
            sort_key = lambda x: x.get("pattern", "")
            
        for item in data:
            key = json.dumps(item, sort_keys=True)
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
                
        if sort_key:
            unique_items.sort(key=sort_key)
            
        data = unique_items
        new_len = len(data)
        
    elif isinstance(data, dict):
        # Dict (like cultural_entities)
        new_dict = {}
        for k in sorted(data.keys()):
            new_dict[k] = data[k]
        data = new_dict
        new_len = len(data)

    save_json(path, data)
    print(f"[SUCCESS] Optimized {name}. Duplicates removed: {original_len - new_len}. Total items: {new_len}.")


def add_cultural_entity(key: str, pattern: str, canonical_en: str, keyword: str):
    path = DATASETS["cultural"]
    data = load_json(path) or {}
    
    if key not in data:
        data[key] = {
            "patterns": [],
            "canonical_en": canonical_en,
            "keywords": []
        }
        
    if pattern not in data[key]["patterns"]:
        data[key]["patterns"].append(pattern)
        
    if keyword and keyword not in data[key]["keywords"]:
        data[key]["keywords"].append(keyword)
        
    save_json(path, data)
    print(f"[SUCCESS] Added entity '{key}' to cultural dataset.")


def main():
    parser = argparse.ArgumentParser(description="Traffic & Cultural Dataset Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Optimize command
    opt_parser = subparsers.add_parser("optimize", help="Deduplicate, format and sort a dataset")
    opt_parser.add_argument("dataset", choices=list(DATASETS.keys()) + ["all"], help="Dataset to optimize")
    
    # Add command for cultural entities (e.g. traffic slang)
    add_parser = subparsers.add_parser("add_slang", help="Add a new Vietnamese slang/entity")
    add_parser.add_argument("--key", required=True, help="Unique ID (e.g. 'canh_sat_co_dong')")
    add_parser.add_argument("--pattern", required=True, help="Regex pattern (e.g. '\\\\bcảnh sát cơ động\\\\b')")
    add_parser.add_argument("--en", required=True, help="English canonical meaning")
    add_parser.add_argument("--keyword", default="", help="Optional keyword to add")

    args = parser.parse_args()
    
    if args.command == "optimize":
        if args.dataset == "all":
            for ds in DATASETS.keys():
                optimize_dataset(ds)
        else:
            optimize_dataset(args.dataset)
            
    elif args.command == "add_slang":
        add_cultural_entity(args.key, args.pattern, args.en, args.keyword)


if __name__ == "__main__":
    main()
