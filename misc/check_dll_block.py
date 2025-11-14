# check_dll_block.py
import os
import sys
import traceback

dll_targets = [
    "scipy.sparse",
    "scipy.sparse._csparsetools",
    "scipy.sparse._lil",
    "scipy.sparse._cyutility",
    "sklearn.metrics.pairwise",
]

log_file = "dll_diagnostic_log.txt"

def log(msg):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)

log("=== DLL Block Diagnostic ===")
log(f"Python version: {sys.version}")
log(f"Platform: {sys.platform}")
log(f"Working directory: {os.getcwd()}")
log("")

for module in dll_targets:
    try:
        __import__(module)
        log(f"[OK] Imported: {module}")
    except Exception as e:
        log(f"[ERROR] Failed to import: {module}")
        log(traceback.format_exc())
        log("-" * 40)

log("=== Diagnostic Complete ===")