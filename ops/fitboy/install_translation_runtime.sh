#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer as root (sudo)." >&2
    exit 1
fi

REPO="/opt/FitBoyRepack"
RUNTIME="/opt/fitboy-translation"
STATE="/var/lib/fitboy/translation"
TMP_PARENT="/var/lib/fitboy/tmp"
MODEL_ID="Helsinki-NLP/opus-mt-tc-big-en-fr"
RUNTIME_REQ="$REPO/ops/fitboy/translation-runtime-requirements.txt"

for required in python3 git systemctl; do
    command -v "$required" >/dev/null 2>&1 || {
        echo "Missing required command: $required" >&2
        exit 2
    }
done

id fitboy >/dev/null 2>&1 || {
    echo "Missing fitboy system user." >&2
    exit 3
}

test -f "$RUNTIME_REQ" || {
    echo "Missing runtime requirements: $RUNTIME_REQ" >&2
    exit 4
}

install -d -m 0750 -o root -g fitboy "$RUNTIME"
install -d -m 0750 -o fitboy -g fitboy "$STATE"
install -d -m 0750 -o fitboy -g fitboy "$TMP_PARENT"

WORK="$(sudo -u fitboy -H mktemp -d "$TMP_PARENT/translation-install.XXXXXX")"
cleanup() {
    set +e
    rm -rf --one-file-system "$WORK"
}
trap cleanup EXIT INT TERM

echo "[translation-install] temporary workspace=$WORK"
echo "[translation-install] building minimal persistent runtime"

NEW_VENV="$RUNTIME/.venv.new.$$"
rm -rf "$NEW_VENV"
python3 -m venv "$NEW_VENV"
"$NEW_VENV/bin/python" -m pip install --quiet --disable-pip-version-check --no-cache-dir -r "$RUNTIME_REQ"

echo "[translation-install] creating disposable conversion environment"
sudo -u fitboy -H python3 -m venv "$WORK/convert-venv"

sudo -u fitboy -H     env PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1     "$WORK/convert-venv/bin/python" -m pip install     --quiet --no-cache-dir     "torch==2.10.0+cpu"     --index-url https://download.pytorch.org/whl/cpu

sudo -u fitboy -H     env PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1     "$WORK/convert-venv/bin/python" -m pip install     --quiet --no-cache-dir     -r "$RUNTIME_REQ"

export HOME="$WORK/home"
export HF_HOME="$WORK/hf"
export XDG_CACHE_HOME="$WORK/cache"
export TMPDIR="$WORK/tmp"
export TOKENIZERS_PARALLELISM=false
mkdir -p "$HOME" "$HF_HOME" "$XDG_CACHE_HOME" "$TMPDIR"
chown -R fitboy:fitboy "$WORK"

echo "[translation-install] downloading and converting $MODEL_ID to INT8"
sudo -u fitboy -H     env HOME="$HOME" HF_HOME="$HF_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" TMPDIR="$TMPDIR"     TOKENIZERS_PARALLELISM=false     "$WORK/convert-venv/bin/ct2-transformers-converter"     --model "$MODEL_ID"     --output_dir "$WORK/model-int8"     --quantization int8

echo "[translation-install] saving tokenizer-only runtime assets"
sudo -u fitboy -H     env HOME="$HOME" HF_HOME="$HF_HOME" XDG_CACHE_HOME="$XDG_CACHE_HOME" TMPDIR="$TMPDIR"     TOKENIZERS_PARALLELISM=false     "$WORK/convert-venv/bin/python" - "$MODEL_ID" "$WORK/tokenizer" <<'PY'
import sys
from transformers import AutoTokenizer

model_id, output = sys.argv[1], sys.argv[2]
tokenizer = AutoTokenizer.from_pretrained(model_id)
tokenizer.save_pretrained(output)
print("tokenizer_saved=" + output)
PY

echo "[translation-install] validating persistent runtime before swap"
"$NEW_VENV/bin/python" - "$WORK/model-int8" "$WORK/tokenizer" <<'PY'
import sys
import ctranslate2
from transformers import AutoTokenizer

model, tokenizer_path = sys.argv[1], sys.argv[2]
supported = ctranslate2.get_supported_compute_types("cpu")
if "int8" not in supported:
    raise SystemExit("CTranslate2 CPU INT8 is not supported on this host")

translator = ctranslate2.Translator(
    model,
    device="cpu",
    compute_type="int8",
    inter_threads=1,
    intra_threads=1,
)
tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, local_files_only=True)
ids = tokenizer.encode("This is a translation runtime self-test.", add_special_tokens=True)
tokens = tokenizer.convert_ids_to_tokens(ids)
result = translator.translate_batch([tokens], beam_size=2, max_batch_size=1)[0]
out_ids = tokenizer.convert_tokens_to_ids(result.hypotheses[0])
text = tokenizer.decode(out_ids, skip_special_tokens=True).strip()
if not text:
    raise SystemExit("empty translation runtime self-test")
print("runtime_self_test=" + text)
PY

echo "[translation-install] atomically installing runtime/model/tokenizer"
rm -rf "$RUNTIME/.venv.old" "$STATE/model-int8.old" "$STATE/tokenizer.old"

if [ -d "$RUNTIME/.venv" ]; then
    mv "$RUNTIME/.venv" "$RUNTIME/.venv.old"
fi
mv "$NEW_VENV" "$RUNTIME/.venv"

if [ -d "$STATE/model-int8" ]; then
    mv "$STATE/model-int8" "$STATE/model-int8.old"
fi
if [ -d "$STATE/tokenizer" ]; then
    mv "$STATE/tokenizer" "$STATE/tokenizer.old"
fi

mv "$WORK/model-int8" "$STATE/model-int8"
mv "$WORK/tokenizer" "$STATE/tokenizer"

chown -R root:fitboy "$RUNTIME/.venv" "$STATE/model-int8" "$STATE/tokenizer"
chmod -R o-rwx "$RUNTIME/.venv" "$STATE/model-int8" "$STATE/tokenizer"

rm -rf "$RUNTIME/.venv.old" "$STATE/model-int8.old" "$STATE/tokenizer.old"

echo "[translation-install] installing systemd units"
install -m 0644 "$REPO/ops/fitboy/translation-autodrain.service" /etc/systemd/system/translation-autodrain.service
install -m 0644 "$REPO/ops/fitboy/translation-autodrain.timer" /etc/systemd/system/translation-autodrain.timer
install -m 0644 "$REPO/ops/fitboy/translation-publish.service" /etc/systemd/system/translation-publish.service
install -m 0644 "$REPO/ops/fitboy/translation-publish.timer" /etc/systemd/system/translation-publish.timer

systemctl daemon-reload
systemctl enable --now translation-autodrain.timer translation-publish.timer

echo "[translation-install] final persistent sizes"
du -sh "$RUNTIME/.venv" "$STATE/model-int8" "$STATE/tokenizer" 2>/dev/null || true
echo "[translation-install] timers"
systemctl is-active translation-autodrain.timer
systemctl is-active translation-publish.timer

echo "[translation-install] SUCCESS"
echo "Temporary conversion environment and Hugging Face cache will now be removed."
