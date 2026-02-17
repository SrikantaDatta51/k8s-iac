#!/usr/bin/env python3
"""BMaaS Monitoring Dashboard Suite — Main Generator.

Generates all Grafana dashboard JSON files by invoking individual build modules.
Usage: python3 generate_dashboards.py [--all | --dashboard 00 01 02 ...]
"""
import json, os, sys

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboards")

BUILDERS = {
    "00": ("build_00_executive", "build_00", "00-executive-fleet-overview.json"),
    "01": ("build_01_gpu_health", "build_01", "01-gpu-health-diagnostics.json"),
    "02": ("build_02_infrastructure", "build_02", "02-infrastructure-hardware-health.json"),
    "03": ("build_03_network", "build_03", "03-network-fabric-monitoring.json"),
    "04": ("build_04_workload", "build_04", "04-workload-job-performance.json"),
    "05": ("build_05_burnin", "build_05", "05-burnin-certification.json"),
    "06": ("build_06_sla", "build_06", "06-sla-compliance-alerting.json"),
}

def generate(dashboard_ids=None):
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    ids = dashboard_ids or sorted(BUILDERS.keys())
    results = []

    for did in ids:
        if did not in BUILDERS:
            print(f"  ⚠️  Unknown dashboard ID: {did}")
            continue

        module_name, func_name, filename = BUILDERS[did]
        outpath = os.path.join(DASHBOARD_DIR, filename)

        try:
            mod = __import__(module_name)
            build_fn = getattr(mod, func_name)
            dashboard = build_fn()
            with open(outpath, "w") as f:
                json.dump(dashboard, f, indent=4)

            panel_count = len(dashboard["panels"])
            uid = dashboard.get("uid", "?")
            results.append((did, filename, panel_count, uid, "✅"))
            print(f"  ✅ {filename}: {panel_count} panels (uid={uid})")
        except Exception as e:
            results.append((did, filename, 0, "?", f"❌ {e}"))
            print(f"  ❌ {filename}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Generated {sum(1 for r in results if '✅' in r[4])} / {len(ids)} dashboards")
    print(f"Output directory: {DASHBOARD_DIR}")

    # Verify unique UIDs
    uids = [r[3] for r in results if '✅' in r[4]]
    if len(uids) != len(set(uids)):
        print("⚠️  WARNING: Duplicate UIDs detected!")
    else:
        print(f"✅ All {len(uids)} UIDs are unique")

    return results


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Usage: python3 generate_dashboards.py [--all | --dashboard 00 01 02 ...]")
        print("  --all           Generate all dashboards (default)")
        print("  --dashboard IDs Generate specific dashboards by ID (00-06)")
        sys.exit(0)

    if "--dashboard" in sys.argv:
        idx = sys.argv.index("--dashboard")
        ids = sys.argv[idx+1:]
    else:
        ids = None  # generate all available

    print(f"BMaaS Monitoring Dashboard Suite — Generator")
    print(f"{'='*60}")
    generate(ids)
