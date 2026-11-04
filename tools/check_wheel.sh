#!/usr/bin/env bash
# Build the wheel, install it in a fresh environment, and run the student notebook OFFLINE in an empty folder.
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
"$WORK/env/bin/pip" install -q "$WHEEL" nbclient nbformat ipykernel
rm -rf "$WORK/run" && mkdir -p "$WORK/run" && cp "$ROOT/Virtual_River_Gauges_Student.ipynb" "$WORK/run/"
cd "$WORK/run"
VG_OFFLINE=1 "$WORK/env/bin/python" - <<'EOF'
import nbformat, nbclient, sys, virtualgauge as vg, pandas, numpy, geopandas, ipywidgets
print("python", sys.version.split()[0], "| pandas", pandas.__version__, "| numpy", numpy.__version__,
      "| geopandas", geopandas.__version__, "| ipywidgets", ipywidgets.__version__)
assert "site-packages" in vg.__file__, vg.__file__
nb = nbformat.read("Virtual_River_Gauges_Student.ipynb", 4)
for c in nb.cells:
    if c.cell_type == "code":
        c.outputs = []
nbclient.NotebookClient(nb, timeout=600, kernel_name="python3").execute()
errors = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
for e in errors:
    print("ERROR", e.ename, e.evalue)
print("cells:", len(nb.cells), "| errors:", len(errors))
sys.exit(1 if errors else 0)
EOF
echo "OK — student notebook runs offline from the installed wheel"
