#!/bin/bash
# ============================================================================
# GPS Spoofer - Instalacni skript
# ============================================================================
# Tento skript nainstaluje vsechny potrebne zavislosti pro GPS Spoofer.
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
NC='\033[0m' # No Color

# Funkce pro vypis
info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[OK]${NC}    $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; }
step()    { echo -e "\n${CYAN}${BOLD}>> $1${NC}"; }

# Banner
echo -e "${BOLD}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║         GPS Spoofer - Instalace       ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

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
    warn "Starsi verze nemusí byt plne podporovany."
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
    echo -e "  Nainstalujte Python 3 jednim z techto zpusobu:"
    echo -e "  ${CYAN}1.${NC} Stazenim z ${BOLD}https://www.python.org/downloads/${NC}"
    echo -e "  ${CYAN}2.${NC} Pres Homebrew: ${BOLD}brew install python3${NC}"
    echo ""
    exit 1
fi

PY_VERSION=$("$PYTHON3" --version 2>&1)
success "Python nalezen: $PYTHON3 ($PY_VERSION)"

# ---- 3. Kontrola/instalace Homebrew ----
step "Kontrola Homebrew"

if command -v brew &>/dev/null; then
    BREW_VERSION=$(brew --version | head -1)
    success "Homebrew nalezen: $BREW_VERSION"
else
    warn "Homebrew neni nainstalovany."
    info "Instaluji Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Pridej do PATH pro Apple Silicon
    if [[ "$ARCH" == "arm64" ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi

    if command -v brew &>/dev/null; then
        success "Homebrew uspesne nainstalovany"
    else
        error "Instalace Homebrew selhala"
        exit 1
    fi
fi

# ---- 4. Instalace PyQt6 a pymobiledevice3 ----
step "Instalace Python balicku (PyQt6, pymobiledevice3)"

PIP3="${PYTHON3} -m pip"

# PyQt6
if $PIP3 show PyQt6 &>/dev/null; then
    QT_VERSION=$($PIP3 show PyQt6 2>/dev/null | grep "^Version:" | awk '{print $2}')
    success "PyQt6 uz je nainstalovany (verze $QT_VERSION)"
else
    info "Instaluji PyQt6 (GUI knihovna)..."
    $PIP3 install PyQt6 2>&1 | tail -3
fi

if ! $PIP3 show PyQt6 &>/dev/null; then
    error "Instalace PyQt6 selhala!"
    echo ""
    echo -e "  Zkuste manualni instalaci:"
    echo -e "  ${BOLD}$PIP3 install PyQt6${NC}"
    echo ""
    exit 1
fi
success "PyQt6 pripraven"

# pymobiledevice3
if $PIP3 show pymobiledevice3 &>/dev/null; then
    CURRENT_VERSION=$($PIP3 show pymobiledevice3 2>/dev/null | grep "^Version:" | awk '{print $2}')
    success "pymobiledevice3 uz je nainstalovany (verze $CURRENT_VERSION)"
    info "Aktualizuji na nejnovejsi verzi..."
    $PIP3 install --upgrade pymobiledevice3 2>&1 | tail -1
else
    info "Instaluji pymobiledevice3..."
    $PIP3 install pymobiledevice3 2>&1 | tail -3
fi

# Overeni instalace
if $PIP3 show pymobiledevice3 &>/dev/null; then
    INSTALLED_VERSION=$($PIP3 show pymobiledevice3 2>/dev/null | grep "^Version:" | awk '{print $2}')
    success "pymobiledevice3 verze $INSTALLED_VERSION nainstalovany"
else
    error "Instalace pymobiledevice3 selhala!"
    echo ""
    echo -e "  Zkuste manualni instalaci:"
    echo -e "  ${BOLD}$PIP3 install pymobiledevice3${NC}"
    echo ""
    exit 1
fi

# Overeni ze CLI je dostupne
PMD3_PATH=""
for p in /opt/homebrew/bin/pymobiledevice3 /usr/local/bin/pymobiledevice3 "$HOME/.local/bin/pymobiledevice3"; do
    if [[ -x "$p" ]]; then
        PMD3_PATH="$p"
        break
    fi
done

if [[ -n "$PMD3_PATH" ]]; then
    success "pymobiledevice3 CLI: $PMD3_PATH"
else
    warn "pymobiledevice3 CLI neni v PATH."
    warn "Mozna bude potreba pridat ~/.local/bin do PATH:"
    echo -e "  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${NC}"
fi

# ---- 5. Zaverecne info ----
step "Instalace dokoncena!"

echo ""
echo -e "${GREEN}${BOLD}  Vse je pripraveno!${NC}"
echo ""
echo -e "  ${BOLD}Spusteni aplikace:${NC}"
echo -e "  ${CYAN}$PYTHON3 app.py${NC}"
echo ""
echo -e "  ${BOLD}Pred spustenim:${NC}"
echo -e "  1. Pripojte iPhone pres USB kabel"
echo -e "  2. Na iPhonu povolte Developer Mode (Nastaveni > Soukromi a zabezpeceni)"
echo -e "  3. Duverte pocitaci na iPhonu kdyz se zobrazi dialog"
echo ""
echo -e "  ${YELLOW}Poznamka:${NC} Aplikace vyzaduje sudo pro tunneld daemon."
echo -e "  Budete pozadani o heslo pri spusteni."
echo ""
