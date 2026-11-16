#!/usr/bin/env bash
# Build the wheel, install it (with the flood extras) in a fresh environment, and run both student notebooks
# OFFLINE in an empty folder.
# Proves the bundled data are used and nothing depends on this project folder.
# Usage: tools/check_wheel.sh [work folder]   (PYTHON=python3.12 tools/check_wheel.sh to choose the interpreter)
#        EXTRA_PINS="pandas==2.2.2 numpy==1.26.4 ..." to imitate an older environment such as Colab.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${1:-$(mktemp -d)}"
PY="${PYTHON:-python3}"
rm -rf "$ROOT/dist"
"$PY" -m pip wheel "$ROOT" --no-deps -w "$ROOT/dist" -q
WHEEL="$(ls "$ROOT"/dist/virtualgauge-*.whl)"
echo "wheel: $WHEEL ($(du -h "$WHEEL" | cut -f1))"
"$PY" -m venv "$WORK/env"
if [ -n "${EXTRA_PINS:-}" ]; then "$WORK/env/bin/pip" install -q $EXTRA_PINS; fi
"$WORK/env/bin/pip" install -q "$WHEEL[flood]" nbclient nbformat ipykernel
rm -rf "$WORK/run" && mkdir -p "$WORK/run"
cp "$ROOT/Virtual_River_Gauges_Student.ipynb" "$ROOT/SWOT_Flood_Depth_Student.ipynb" "$WORK/run/"
cd "$WORK/run"
VG_OFFLINE=1 "$WORK/env/bin/python" - <<'EOF'
import nbformat, nbclient, sys, virtualgauge as vg, pandas, numpy, geopandas, ipywidgets
print("python", sys.version.split()[0], "| pandas", pandas.__version__, "| numpy", numpy.__version__,
      "| geopandas", geopandas.__version__, "| ipywidgets", ipywidgets.__version__)
assert "site-packages" in vg.__file__, vg.__file__
failed = 0
for name in ["Virtual_River_Gauges_Student.ipynb", "SWOT_Flood_Depth_Student.ipynb"]:
    nb = nbformat.read(name, 4)
    for c in nb.cells:
        if c.cell_type == "code":
            c.outputs = []
    nbclient.NotebookClient(nb, timeout=600, kernel_name="python3").execute()
    errors = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
    for e in errors:
        print("ERROR", e.ename, e.evalue)
    print(name, "| cells:", len(nb.cells), "| errors:", len(errors))
    failed += len(errors)
sys.exit(1 if failed else 0)
EOF
echo "OK — both student notebooks run offline from the installed wheel"
