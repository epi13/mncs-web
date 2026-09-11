#!/usr/bin/env bash
# Full mncs-web validation: source-study every module, then the pytest
# suite. Fails on the first error.
set -euo pipefail
cd "$(dirname "$0")/.."

: "${MNCS_BIN:=/home/epi13/Documents/Projects/mncs-language/target/debug/mncs}"
: "${MNCS_LANG_LIB:=/home/epi13/Documents/Projects/mncs-language/library}"
export MNCS_LIBRARY_PATH="$MNCS_LANG_LIB:$PWD/src"

echo "== source-study all modules =="
for f in src/web/*.mncs; do
  errs=$("$MNCS_BIN" source-study "$f" | python3 -c \
    "import json,sys; d=json.load(sys.stdin); print(len([x for x in d.get('diagnostics',[]) if x.get('severity')=='error']))")
  echo "$f: $errs errors"
  if [ "$errs" != "0" ]; then echo "FAIL $f"; exit 1; fi
done

echo "== pytest suite (${MNCS_BACKENDS:-fast backends}) =="
python3 -m pytest tests/ -q
