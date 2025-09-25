/*
 * Copyright (c) 2025 PoCEffectiveness
 * All rights reserved.
 */

from logger import log
from typing import Optional

def select_nearest_reproduced_version_from_lists(
    pending_versions_sorted: list,
    reproduced_versions_sorted: list,
    all_versions: list
) -> Optional[str]:
    
    

    if not pending_versions_sorted:
        log("Selector", "No pending versions available.", "warning")
        return None, None
    if not reproduced_versions_sorted:
        log("Selector", "No reproduced versions available.", "warning")
        return None, None

    reproduced_indices = [all_versions.index(v) for v in reproduced_versions_sorted]
    pending_indices = [all_versions.index(v) for v in pending_versions_sorted]
    
    
    nearest_version = None
    min_distance = float("inf")

    for ver, idx in zip(pending_versions_sorted, pending_indices):
        distance, closest_rep_idx = min(
            ((abs(idx - rep_idx), rep_idx) for rep_idx in reproduced_indices),
            key=lambda x: x[0]
        )
        if distance < min_distance:
            min_distance = distance
            nearest_version = ver
            nearest_reproduce_index = closest_rep_idx
            nearest_reproduce_version = all_versions[nearest_reproduce_index]

    log("Selector", f"Nearest need adapatation version selected: {nearest_version}", "info")
    log("Selector", f"Closest reproduced version: {nearest_reproduce_version} at index {nearest_reproduce_index}", "info")
    return nearest_version, nearest_reproduce_version
