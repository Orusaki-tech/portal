#!/usr/bin/env python3
"""
Pre-generation script for the COG Catalog (Track 3).

Pre-queries all STAC sources for admin1 (47 counties) and admin2 (290 sub-counties)
polygons so the ImageryModal returns cached results instantly.

Usage:
    python scripts/pregenerate-cogs.py
    python scripts/pregenerate-cogs.py --sources naip,sentinel-2-l2a
    python scripts/pregenerate-cogs.py --level admin1
    python scripts/pregenerate-cogs.py --dry-run
    python scripts/pregenerate-cogs.py --force
"""

import argparse
import json
import os
import sys
import time
from typing import Any

# Add the project root to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.engine.service_layer.cog_service import (
    SOURCE_CONFIG,
    _geometry_hash,
    _gcs_index_path,
    _query_stac,
    _write_gcs_json,
    _public_url,
    PRODUCTION_BUCKET,
    _gcs_blob_exists,
    compute_geojson_area,
)

STAC_SOURCE_IDS = list(SOURCE_CONFIG.keys())

ADMIN_DATA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "frontend", "public", "data", "kenya"
)


def load_admin_geojson(level: str) -> list[dict[str, Any]]:
    path = os.path.join(ADMIN_DATA_DIR, f"{level}.geojson")
    if not os.path.exists(path):
        print(f"  [SKIP] {path} not found")
        return []
    with open(path) as f:
        data = json.load(f)
    features = data.get("features", [])
    print(f"  Loaded {len(features)} features from {level}")
    return features


def pregenerate_for_level(
    level: str,
    sources: list[str],
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    features = load_admin_geojson(level)
    if not features:
        return {"level": level, "features": 0, "total": 0, "cached": 0, "new": 0, "errors": 0}

    total = 0
    cached = 0
    new_count = 0
    errors = 0

    for i, feat in enumerate(features):
        geometry = feat.get("geometry")
        if not geometry:
            continue

        props = feat.get("properties", {})
        name = props.get(f"adm{level[-1]}_name", f"feature-{i}")

        for source_id in sources:
            buffer_m = 0
            geo_hash = _geometry_hash(geometry, source_id, buffer_m)
            index_path = _gcs_index_path(source_id, geo_hash)

            # Check cache
            if not force and _gcs_blob_exists(PRODUCTION_BUCKET, index_path):
                cached += 1
                total += 1
                continue

            if dry_run:
                print(f"  [DRY] {level}/{name} @ {source_id} -> {index_path}")
                new_count += 1
                total += 1
                continue

            try:
                scene = _query_stac(source_id, geometry, buffer_m)
                if scene:
                    area_km2 = compute_geojson_area(geometry, buffer_m)
                    index_data = {
                        "cog_url": scene["cog_url"],
                        "scene_id": scene["scene_id"],
                        "collection": scene["collection"],
                        "datetime": scene["datetime"],
                        "resolution": scene["resolution"],
                        "area_km2": area_km2,
                        "source_type": "stac",
                        "pre_generated": True,
                    }
                    _write_gcs_json(PRODUCTION_BUCKET, index_path, index_data)
                    new_count += 1
                    print(f"  [OK]  {level}/{name} @ {source_id} -> {scene['scene_id']}")
                else:
                    print(f"  [--]  {level}/{name} @ {source_id} -> no scene found")
                total += 1
            except Exception as e:
                errors += 1
                print(f"  [ERR] {level}/{name} @ {source_id}: {e}")

    return {
        "level": level,
        "features": len(features),
        "total": total,
        "cached": cached,
        "new": new_count,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-generate COG catalog for admin boundaries")
    parser.add_argument(
        "--sources",
        default=",".join(STAC_SOURCE_IDS),
        help=f"Comma-separated source IDs (default: all STAC sources: {','.join(STAC_SOURCE_IDS)})",
    )
    parser.add_argument(
        "--level",
        choices=["admin1", "admin2", "all"],
        default="all",
        help="Admin level to pre-generate (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be done")
    parser.add_argument("--force", action="store_true", help="Re-query even if cached")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    levels = ["admin1", "admin2"] if args.level == "all" else [args.level]

    print(f"COG Pre-generation")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Levels:  {', '.join(levels)}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Force:   {args.force}")
    print()

    start = time.time()
    total_stats = {"total": 0, "cached": 0, "new": 0, "errors": 0}

    for level in levels:
        stats = pregenerate_for_level(level, sources, args.dry_run, args.force)
        total_stats["total"] += stats["total"]
        total_stats["cached"] += stats["cached"]
        total_stats["new"] += stats["new"]
        total_stats["errors"] += stats["errors"]
        print(f"  {level}: {stats['total']} total, {stats['cached']} cached, {stats['new']} new, {stats['errors']} errors")
        print()

    elapsed = time.time() - start
    print(f"Done in {elapsed:.1f}s")
    print(f"  Total operations: {total_stats['total']}")
    print(f"  Cache hits:       {total_stats['cached']}")
    print(f"  New entries:      {total_stats['new']}")
    print(f"  Errors:           {total_stats['errors']}")

    if args.dry_run:
        print()
        print("This was a dry run. Re-run without --dry-run to execute.")


if __name__ == "__main__":
    main()
