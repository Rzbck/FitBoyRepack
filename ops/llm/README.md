# Reusable local LLM service

This directory describes a **VPS-wide** LLM service. It is deliberately independent from FitBoyRepack: any local script or application can call the same OpenAI-compatible endpoint.

## Layout

- `llama-server.service`: generic `systemd` unit for `llama.cpp`'s `llama-server`.
- `llm.env.example`: runtime/model settings. The model can be replaced without changing consuming projects.
- Default API: `http://127.0.0.1:8080/v1` (localhost only).

## VPS setup

1. Install/build `llama-server` at `/usr/local/bin/llama-server`.
2. Create a dedicated account and directories:

   ```bash
   sudo useradd --system --home /var/lib/llm --shell /usr/sbin/nologin llm || true
   sudo install -d -o llm -g llm /var/lib/llm/models /etc/llm
   ```

3. Put a GGUF model in `/var/lib/llm/models/` and copy `llm.env.example` to `/etc/llm/llm.env`. Change `MODEL_PATH` for whichever general-purpose model you choose.
4. Copy `llama-server.service` to `/etc/systemd/system/llama-server.service`.
5. Start it:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now llama-server
   curl http://127.0.0.1:8080/v1/models
   ```

The unit defaults to one parallel generation, low process priority, a 150% CPU quota, `MemoryHigh=5G`, and `MemoryMax=6G`. Those are conservative starter limits, not model requirements; tune them after checking the VPS CPU/RAM.

## Use from any project

Any OpenAI-compatible client can use the service. This repository includes `tools/llm_client.py` as one small example:

```bash
export LLM_BASE_URL=http://127.0.0.1:8080/v1
export LLM_MODEL=local-model
python tools/llm_client.py 'Résume ce texte en français.'
```

FitBoyRepack's metadata worker is only a client of this service. Stopping/deleting the project does not affect the LLM server, and changing the model does not require rewriting the project.
