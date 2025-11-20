

import multiprocessing
from version_analyzer import CVEProcessor
from version_selector import select_nearest_reproduced_version_from_lists
from exploit_preparer import ExploitPreparer
from exploit_executor import ExploitExecutor
from exploit_adapter import ExploitAdapter

import os
import json
from logger import log
import shutil

import traceback

def run_adaptation(adapter, base_version, next_version, executor, queue):
    try:
        result = adapter.adapt(base_version, next_version, executor)
        queue.put(("ok", result))
    except Exception as e:
        tb_str = traceback.format_exc()
        queue.put(("error", tb_str))



def run_with_timeout(adapter, base_version, next_version, executor, timeout_sec=300):
    queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=run_adaptation, args=(adapter, base_version, next_version, executor, queue))
    p.start()
    p.join(timeout=timeout_sec)

    if p.is_alive():
        p.terminate()
        p.join()
        print(f"[Adapt] ⏰ Timeout: exceeded {timeout_sec} seconds for {base_version} → {next_version}")
        return None
    else:
        if not queue.empty():
            status, result = queue.get()
            if status == "ok":
                print(f"[Adapt] ✓ Completed: {result}")
                return result
            else:
                print(f"[Adapt] ✗ Error during execution: {result}")
                return False
        else:
            print("[Adapt] ✗ No result returned.")
            return False
        
        
def main_process(cve_id: str, from_version: str = None):
    log("Main", f"=== Starting adaptation process for {cve_id} ===", "bold")

    result_log = []
    result_dir = os.path.join("/PoCAdaptation", "exploit", "result", cve_id)
    os.makedirs(result_dir, exist_ok=True)
    result_file_path = os.path.join(result_dir, "result.json")

    processor = CVEProcessor(cve_id)

    log("Processor", "Fetching all available Maven versions...", "info")
    processor.fetch_all_maven_versions()

    log("Processor", "Identifying versions with successful reproduction...", "info")
    processor.identify_reproduced_versions()

    reproduced_versions = processor.get_reproduced_versions()
    affected_versions = processor.get_affected_versions()
    all_versions = processor.all_maven_versions
    pending_versions = [v for v in affected_versions if v not in reproduced_versions]
    pending_versions_sorted = sorted(pending_versions, key=lambda v: all_versions.index(v))

    log("Processor", f"Pending versions: {pending_versions_sorted}", "info")
    
    preparer = ExploitPreparer(cve_id, processor.get_group_id(), processor.get_artifact_id())

    attempted_versions = set()

    
    if from_version and from_version in all_versions:
        from_index = all_versions.index(from_version)
        
        removed_versions = [v for v in pending_versions_sorted if all_versions.index(v) > from_index]
        reproduced_versions.extend(removed_versions)
        pending_versions_sorted = [v for v in pending_versions_sorted if all_versions.index(v) <= from_index]


    reproduced_versions_sorted = sorted(reproduced_versions, key=lambda v: all_versions.index(v))

    log("Main", f"Total affected versions: {len(affected_versions)}", "success")
    log("Main", f"Already reproduced versions: {len(reproduced_versions_sorted)}", "success")
    log("Main", f"Versions pending adaptation: {len(pending_versions_sorted)}", "warning")
    log("Main", "    -> " + str(pending_versions_sorted), "info")
    log("Main", "    -> " + str(reproduced_versions_sorted), "info")




    executor = ExploitExecutor(cve_id, processor.get_reproduced_behavior(), processor.get_reproduced_detail())
    adapter = ExploitAdapter(cve_id, processor)


    while True:
        next_version, nearst_reproduce_version = select_nearest_reproduced_version_from_lists(
            pending_versions_sorted=pending_versions_sorted,
            reproduced_versions_sorted=reproduced_versions_sorted,
            all_versions=all_versions
        )

        if not next_version:
            log("Main", "No suitable version found for further adaptation. Stopping.", "error")
            break

        log("Adapter", f"Trying next closest version: {next_version}", "info")

        if next_version in attempted_versions:
            log("Adapter", f"{next_version} already attempted. Removing from pending list.", "warning")
            if next_version in pending_versions_sorted:
                pending_versions_sorted.remove(next_version)
            continue

        attempted_versions.add(next_version)
        if next_version in pending_versions_sorted:
            pending_versions_sorted.remove(next_version)

        base_version = nearst_reproduce_version if reproduced_versions_sorted else None
        preparer.prepare_adaptation_version(base_version, next_version, all_versions)

        log("Executor", f"Attempting direct exploit execution on {next_version}...", "info")
        if executor.execute(next_version):
            log("Executor", f"Direct reproduction successful on {next_version}", "success")
            reproduced_versions_sorted.append(next_version)
            reproduced_versions_sorted = sorted(reproduced_versions_sorted, key=lambda v: all_versions.index(v))
            
            result_log.append({
                "version": next_version,
                "method": "direct",
                "status": "success",
                "message": "Direct reproduction succeeded"
            })
            result_path = f"/PoCAdaptation/exploit/pending/{cve_id}/{next_version}"
            valid_path = f"/PoCAdaptation/exploit/valid/{cve_id}/{next_version}"

            if os.path.exists(valid_path):
                shutil.rmtree(valid_path)  
            shutil.copytree(result_path, valid_path)
            log("Adapter", f"Copied successful adaptation to {valid_path}", "info")
                
            continue

        log("Adapter", f"Attempting adaptation from base version {base_version} to {next_version}...", "info")
        if base_version and adapter.adapt(base_version, next_version, executor):
            log("Adapter", f"Adaptation complete. Retesting exploit on {next_version}...", "info")
            log("Executor", f"Adaptation + reproduction successful on {next_version}", "success")
            reproduced_versions_sorted.append(next_version)
            reproduced_versions_sorted = sorted(reproduced_versions_sorted, key=lambda v: all_versions.index(v))
            result_log.append({
                "version": next_version,
                "method": "adaptation",
                "status": "success",
                "message": "Adaptation and reproduction succeeded"
            })
            result_path = f"/PoCAdaptation/exploit/result/{cve_id}/{next_version}"
            valid_path = f"/PoCAdaptation/exploit/valid/{cve_id}/{next_version}"

            if os.path.exists(valid_path):
                shutil.rmtree(valid_path) 
            shutil.copytree(result_path, valid_path)
            log("Adapter", f"Copied successful adaptation to {valid_path}", "info")

        else:
            log("Adapter", f"Adaptation failed for {next_version}", "error")
            result_log.append({
                "version": next_version,
                "method": "adaptation",
                "status": "fail_adaptation",
                "message": "Adaptation failed"
            })
            exit(1)


    with open(result_file_path, "w") as f:
        json.dump(result_log, f, indent=2)

    log("Main", "=== Adaptation process complete ===", "bold")
    log("Main", f"Total reproduced versions: {len(reproduced_versions_sorted)}", "success")
    


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("cve_id", help="CVE ID, e.g., CVE-2021-12345")
    parser.add_argument("from_version", nargs='?', default=None, help="Start Adaptation version, e.g., 1.34.2 (optional)")
    args = parser.parse_args()

    # try:
    #     main_process(args.cve_id, args.from_version)
    # except Exception as e:
    #     log("Main", f"{type(e).__name__}: {e}", "error")

    main_process(args.cve_id, args.from_version)
