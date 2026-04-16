#!/bin/bash
# ============================================================================
# GPS Spoofer - Instalacni skript
# ============================================================================
# Vytvori virtualni prostredi (venv) a nainstaluje potrebne zavislosti.
# Pouzitim venv se vyhneme PEP 668 "externally-managed-environment" chybe
# na modernich Homebrew Pythonech (3.12+).
# Spusteni:  chmod +x install.sh && ./install.sh
# ============================================================================

set -eo pipefail

# Barvy
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; }
step()    { echo -e "\n${CYAN}${BOLD}>> $1${NC}"; }

echo -e "${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         GPS Spoofer - Instalace       ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

# ---- 1. Kontrola macOS ----
step "Kontrola operacniho systemu"

if [[ "$(uname)" != "Darwin" ]]; then
    error "Tento skript funguje pouze na macOS."
    exit 1
fi

MACOS_VERSION=$(sw_vers -productVersion)
info "macOS verze: $MACOS_VERSION"

MAJOR_VERSION=$(echo "$MACOS_VERSION" | cut -d. -f1)
if [[ "$MAJOR_VERSION" -lt 12 ]]; then
    warn "Doporucena verze macOS je 12 (Monterey) nebo novejsi."
fi

ARCH=$(uname -m)
if [[ "$ARCH" == "arm64" ]]; then
    success "Apple Silicon ($ARCH) detekovan"
else
    success "Intel ($ARCH) detekovan"
fi

# ---- 2. Kontrola Python 3 ----
step "Kontrola Python 3"

PYTHON3=""
for p in /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -x "$p" ]]; then
        PYTHON3="$p"
        break
    fi
done

if [[ -z "$PYTHON3" ]]; then
    error "Python 3 nebyl nalezen!"
    echo ""
    echo -e "  Nainstalujte Python 3:"
    echo -e "  ${CYAN}1.${NC} Stazenim z ${BOLD}https://www.python.org/downloads/${NC}"
    echo -e "  ${CYAN}2.${NC} Pres Homebrew: ${BOLD}brew install python3${NC}"
    exit 1
fi

PY_VERSION=$("$PYTHON3" --version 2>&1)
success "Python nalezen: $PYTHON3 ($PY_VERSION)"

# ---- 3. Kontrola/instalace Homebrew (volitelne) ----
step "Kontrola Homebrew"

if command -v brew &>/dev/null; then
    BREW_VERSION=$(brew --version | head -1)
    success "Homebrew nalezen: $BREW_VERSION"
else
    info "Homebrew neni nainstalovany (neni nutne pokud mas Python)."
fi

# ---- 4. Vytvoreni venv ----
step "Vytvoreni virtualniho prostredi"

if [[ -d "$VENV_DIR" ]]; then
    info "Venv uz existuje v $VENV_DIR"
    info "Pouzijem existujici..."
else
    info "Vytvarim venv v $VENV_DIR ..."
    "$PYTHON3" -m venv "$VENV_DIR"
    success "Venv vytvoren"
fi

VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"

if [[ ! -x "$VENV_PYTHON" ]]; then
    error "Venv python neni funkcni: $VENV_PYTHON"
    exit 1
fi

VENV_PY_VERSION=$("$VENV_PYTHON" --version 2>&1)
success "Venv Python: $VENV_PY_VERSION"

# ---- 5. Instalace balicku do venv ----
step "Instalace Python balicku (PyQt6, pymobiledevice3)"

info "Upgrade pip..."
"$VENV_PIP" install --upgrade pip 2>&1 | tail -1 || true

# PyQt6
if "$VENV_PIP" show PyQt6 &>/dev/null; then
    QT_VERSION=$("$VENV_PIP" show PyQt6 2>/dev/null | grep "^Version:" | awk '{print $2}')
    success "PyQt6 uz je nainstalovany (verze $QT_VERSION)"
else
    info "Instaluji PyQt6 (GUI knihovna)..."
    "$VENV_PIP" install PyQt6
fi

if ! "$VENV_PIP" show PyQt6 &>/dev/null; then
    error "Instalace PyQt6 selhala!"
    exit 1
fi
success "PyQt6 pripraven"

# pymobiledevice3
if "$VENV_PIP" show pymobiledevice3 &>/dev/null; then
    CURRENT_VERSION=$("$VENV_PIP" show pymobiledevice3 2>/dev/null | grep "^Version:" | awk '{print $2}')
    success "pymobiledevice3 uz je nainstalovany (verze $CURRENT_VERSION)"
    info "Aktualizuji na nejnovejsi verzi..."
    "$VENV_PIP" install --upgrade pymobiledevice3 2>&1 | tail -1 || true
else
    info "Instaluji pymobiledevice3..."
    "$VENV_PIP" install pymobiledevice3
fi

if ! "$VENV_PIP" show pymobiledevice3 &>/dev/null; then
    error "Instalace pymobiledevice3 selhala!"
    exit 1
fi
INSTALLED_VERSION=$("$VENV_PIP" show pymobiledevice3 2>/dev/null | grep "^Version:" | awk '{print $2}')
success "pymobiledevice3 verze $INSTALLED_VERSION nainstalovany"

# ---- 6. Vytvoreni launcher skriptu ----
step "Vytvoreni launcher skriptu"

LAUNCHER="$SCRIPT_DIR/run.sh"
cat > "$LAUNCHER" <<EOF
#!/bin/bash
# Auto-generated launcher for GPS Spoofer
SCRIPT_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
exec "\$SCRIPT_DIR/venv/bin/python3" "\$SCRIPT_DIR/app.py" "\$@"
EOF
chmod +x "$LAUNCHER"
success "Launcher vytvoren: $LAUNCHER"

# ---- 7. Zaverecne info ----
step "Instalace dokoncena!"

echo ""
echo -e "${GREEN}${BOLD}  Vse je pripraveno!${NC}"
echo ""
echo -e "  ${BOLD}Spusteni aplikace:${NC}"
echo -e "  ${CYAN}./run.sh${NC}"
echo ""
echo -e "  ${BOLD}Pred spustenim:${NC}"
echo -e "  1. Pripojte iPhone pres USB kabel"
echo -e "  2. Na iPhonu povolte Developer Mode (Nastaveni > Soukromi a zabezpeceni)"
echo -e "  3. Duverte pocitaci na iPhonu kdyz se zobrazi dialog"
echo ""
echo -e "  ${YELLOW}Poznamka:${NC} Aplikace vyzaduje sudo pro tunneld daemon."
echo -e "  Otevre Terminal.app kde zadate heslo (jednou)."
echo ""
