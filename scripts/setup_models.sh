#!/usr/bin/env bash
# =============================================================================
# Luminous Model Setup — auto-download and configure local AI models
#
# Tries Ollama first (easiest). Falls back to llama.cpp GGUF download.
# All models are free, open-weight, zero-cost.
#
# Usage:
#   ./scripts/setup_models.sh              # interactive guided setup
#   ./scripts/setup_models.sh --fast       # pull smallest model only
#   ./scripts/setup_models.sh --all        # pull full recommended set
#   ./scripts/setup_models.sh --llama-cpp  # download GGUF + setup llama.cpp
# =============================================================================
set -euo pipefail

FAST=false
ALL_MODELS=false
LLAMA_CPP=false
MODELS_DIR="${MODELS_DIR:-./models}"

for arg in "$@"; do
    case "$arg" in
        --fast)       FAST=true ;;
        --all)        ALL_MODELS=true ;;
        --llama-cpp)  LLAMA_CPP=true ;;
        --help)
            echo "Usage: $0 [--fast | --all | --llama-cpp]"
            exit 0
            ;;
    esac
done

green()  { echo -e "\033[0;32m$*\033[0m"; }
yellow() { echo -e "\033[0;33m$*\033[0m"; }
red()    { echo -e "\033[0;31m$*\033[0m"; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Luminous Model Setup — Trancendos Platform"
echo "═══════════════════════════════════════════════════════"
echo ""

# ── Ollama setup ──────────────────────────────────────────────────────────────

setup_ollama() {
    echo "--- Checking Ollama ---"

    if ! command -v ollama >/dev/null 2>&1; then
        yellow "Ollama not found. Installing..."
        if [[ "$OSTYPE" == "linux-gnu"* ]]; then
            curl -fsSL https://ollama.com/install.sh | sh
        elif [[ "$OSTYPE" == "darwin"* ]]; then
            echo "On macOS: download from https://ollama.com/download/mac"
            echo "Or: brew install ollama"
            exit 1
        else
            red "Unsupported OS. Install Ollama manually: https://ollama.com"
            exit 1
        fi
    fi
    green "✓ Ollama installed: $(ollama --version 2>/dev/null || echo 'unknown version')"

    # Start Ollama if not running
    if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        yellow "Starting Ollama service..."
        ollama serve &>/dev/null &
        sleep 3
    fi
    green "✓ Ollama service running"

    echo ""
    echo "--- Downloading models ---"

    if [ "$FAST" = true ]; then
        MODELS=("llama3.2:1b")
    elif [ "$ALL_MODELS" = true ]; then
        MODELS=(
            "llama3.2:1b"
            "llama3.2:3b"
            "mistral:7b"
            "phi3:mini"
            "nomic-embed-text"
        )
    else
        # Default: small fast model + embedding model
        MODELS=("llama3.2:1b" "nomic-embed-text")
    fi

    for model in "${MODELS[@]}"; do
        echo "Pulling: $model"
        if ollama pull "$model"; then
            green "  ✓ $model ready"
        else
            yellow "  ⚠ Failed to pull $model — skipping"
        fi
    done

    echo ""
    green "Ollama models ready:"
    ollama list 2>/dev/null || true
}

# ── llama.cpp setup ───────────────────────────────────────────────────────────

setup_llama_cpp() {
    echo ""
    echo "--- Setting up llama.cpp ---"

    mkdir -p "$MODELS_DIR"

    # Build llama.cpp if not already done
    LLAMA_DIR="./llama.cpp"
    if [ ! -d "$LLAMA_DIR" ]; then
        yellow "Cloning llama.cpp..."
        git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_DIR"
    fi

    if [ ! -f "$LLAMA_DIR/main" ] && [ ! -f "$LLAMA_DIR/llama-cli" ]; then
        yellow "Building llama.cpp (CPU-only)..."
        cd "$LLAMA_DIR"
        make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
        cd - >/dev/null
        green "✓ llama.cpp built"
    else
        green "✓ llama.cpp already built"
    fi

    # Download a GGUF model if none present
    GGUF_FILES=("$MODELS_DIR"/*.gguf)
    if [ ! -e "${GGUF_FILES[0]}" ]; then
        echo ""
        yellow "No GGUF models found. Downloading Mistral 7B Q4_K_M (~4.4GB)..."
        echo "  Source: HuggingFace (TheBloke/Mistral-7B-Instruct-v0.2-GGUF)"
        echo "  This is free to download and use."
        echo ""

        if command -v wget >/dev/null 2>&1; then
            wget -q --show-progress \
                "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf" \
                -O "$MODELS_DIR/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
        elif command -v curl >/dev/null 2>&1; then
            curl -L --progress-bar \
                "https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf" \
                -o "$MODELS_DIR/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
        else
            red "Neither wget nor curl found. Download manually:"
            echo "  https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF"
        fi
        green "✓ Model downloaded to $MODELS_DIR/"
    else
        green "✓ GGUF model already present: ${GGUF_FILES[0]}"
    fi

    # Create start script for llama.cpp server
    GGUF_MODEL=$(ls "$MODELS_DIR"/*.gguf 2>/dev/null | head -1)
    if [ -n "$GGUF_MODEL" ]; then
        cat > scripts/start_llama_cpp.sh <<EOF
#!/usr/bin/env bash
# Auto-generated: start llama.cpp HTTP server
LLAMA_DIR="\${LLAMA_DIR:-./llama.cpp}"
MODEL="${GGUF_MODEL}"
CONTEXT="\${CONTEXT_LENGTH:-2048}"
THREADS="\${CPU_THREADS:-$(nproc 2>/dev/null || echo 4)}"
SLOTS="\${LLAMA_SLOTS:-4}"

exec "\$LLAMA_DIR/main" \\
  -m "\$MODEL" \\
  --server \\
  -c "\$CONTEXT" \\
  -t "\$THREADS" \\
  -ngl 0 \\
  --slots "\$SLOTS" \\
  --host 0.0.0.0 \\
  --port 8080
EOF
        chmod +x scripts/start_llama_cpp.sh
        green "✓ llama.cpp start script: scripts/start_llama_cpp.sh"
    fi
}

# ── Python dependencies ───────────────────────────────────────────────────────

setup_python_deps() {
    echo ""
    echo "--- Installing Python inference dependencies ---"

    if command -v pip >/dev/null 2>&1; then
        pip install --quiet \
            sentence-transformers \
            lmformatenforcer \
            peft \
            accelerate \
            2>/dev/null || true
        green "✓ Python inference packages installed"
    else
        yellow "pip not found — skipping Python deps"
    fi
}

# ── Run setup ─────────────────────────────────────────────────────────────────

setup_ollama
setup_python_deps

if [ "$LLAMA_CPP" = true ]; then
    setup_llama_cpp
fi

echo ""
echo "═══════════════════════════════════════════════════════"
green "  Luminous model setup complete!"
echo ""
echo "  Start API:    make dev-api  (or: uvicorn api:app --reload)"
echo "  Test Ollama:  ollama run llama3.2:1b"

if [ "$LLAMA_CPP" = true ]; then
    echo "  Start llama.cpp: ./scripts/start_llama_cpp.sh"
fi

echo "═══════════════════════════════════════════════════════"
