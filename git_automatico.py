# -*- coding: utf-8 -*-
"""
GitAutomatico - Ferramenta de automacao para GitHub
Compila com PyInstaller para gerar um .exe standalone.
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
from pathlib import Path

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich.live import Live
from rich.align import Align
from rich import box
from rich.prompt import Prompt
import questionary
from questionary import Style

# ============================================================
#  TOKEN - salvo em %LOCALAPPDATA%\GitAuto\token.dat
#  NAO edite aqui. O programa pergunta na primeira execucao.
# ============================================================
GITHUB_TOKEN = ""  # preenchido em runtime por load_token()
API_BASE = "https://api.github.com"

# ============================================================
#  PASTA DE CONFIG
# ============================================================
def get_config_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    d = base / "GitAuto"
    d.mkdir(parents=True, exist_ok=True)
    return d


TOKEN_FILE  = get_config_dir() / "token.dat"
CUSTOM_IGNORE_FILE = get_config_dir() / "custom_gitignore.json"
DEFAULT_IGNORE_FILE = get_config_dir() / "default_gitignore.json"


def load_token() -> str:
    if TOKEN_FILE.exists():
        try:
            return TOKEN_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return ""


def save_token(token: str):
    TOKEN_FILE.write_text(token.strip(), encoding="utf-8")


def load_custom_ignore() -> list:
    if CUSTOM_IGNORE_FILE.exists():
        try:
            data = json.loads(CUSTOM_IGNORE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_custom_ignore(patterns: list):
    CUSTOM_IGNORE_FILE.write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")


def load_default_ignore() -> list:
    """Carrega a lista padrao editada pelo usuario, ou retorna vazio se nao existir."""
    if DEFAULT_IGNORE_FILE.exists():
        try:
            data = json.loads(DEFAULT_IGNORE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


def save_default_ignore(patterns: list):
    """Salva a lista padrao editada pelo usuario."""
    DEFAULT_IGNORE_FILE.write_text(json.dumps(patterns, ensure_ascii=False, indent=2), encoding="utf-8")


console = Console()

# Tema customizado para o questionary
custom_style = Style([
    ("qmark",       "fg:#00d7ff bold"),
    ("question",    "fg:#ffffff bold"),
    ("answer",      "fg:#00ff87 bold"),
    ("pointer",     "fg:#ff5fd7 bold"),
    ("highlighted", "fg:#ff5fd7 bold"),
    ("selected",    "fg:#00ff87 bold"),
    ("instruction", "fg:#808080 italic"),
    ("text",        "fg:#ffffff"),
    ("separator",   "fg:#444444"),
])


# ============================================================
#  UI HELPERS
# ============================================================
def banner():
    console.clear()
    title_art = (
        "  ____ _ _      _         _                        _   _           \n"
        " / ___(_) |_   / \\  _   _| |_ ___  _ __ ___   __ _| |_(_) ___ ___  \n"
        "| |  _| | __| / _ \\| | | | __/ _ \\| '_ ` _ \\ / _` | __| |/ __/ _ \\ \n"
        "| |_| | | |_ / ___ \\ |_| | || (_) | | | | | | (_| | |_| | (_| (_) |\n"
        " \\____|_|\\__/_/   \\_\\__,_|\\__\\___/|_| |_| |_|\\__,_|\\__|_|\\___\\___/ \n"
    )
    body = Text()
    body.append(title_art, style="bold cyan")
    body.append("\n")
    body.append("       GitHub Repository Automation Tool", style="bold white")
    body.append("\n")
    body.append("                    v1.0.0", style="dim")

    console.print(Panel(
        Align.center(body),
        border_style="bright_magenta",
        box=box.DOUBLE,
        padding=(1, 2),
    ))
    console.print()


def info(msg):
    console.print(f"[cyan][>][/cyan] {msg}")


def success(msg):
    console.print(f"[bold green][OK][/bold green] {msg}")


def warn(msg):
    console.print(f"[bold yellow][!][/bold yellow] {msg}")


def err(msg):
    console.print(f"[bold red][X][/bold red] {msg}")


def pause_exit(code=0):
    console.print()
    try:
        input("Pressione ENTER para sair...")
    except (EOFError, KeyboardInterrupt):
        pass
    sys.exit(code)


def play_notification_sound():
    """Toca o som de notificacao padrao do Windows (ou faz um sinal sonoro)."""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        sys.stdout.write("\a")
        sys.stdout.flush()


# ============================================================
#  VALIDACOES
# ============================================================
def check_token():
    """Carrega token do AppData ou pede ao usuario na primeira vez."""
    global GITHUB_TOKEN
    GITHUB_TOKEN = load_token()
    if not GITHUB_TOKEN:
        console.print()
        console.print(Panel(
            "[bold white]Token do GitHub nao encontrado.[/bold white]\n\n"
            "Para gerar um token:\n"
            "  1. Acesse: [link=https://github.com/settings/tokens]https://github.com/settings/tokens[/link]\n"
            "  2. Clique em [bold]Generate new token (classic)[/bold]\n"
            "  3. Marque os escopos: [bold]repo[/bold], [bold]workflow[/bold]\n"
            "  4. Copie e cole abaixo\n\n"
            f"[dim]Sera salvo em: {TOKEN_FILE}[/dim]",
            border_style="yellow", box=box.ROUNDED, title="[yellow]Configuracao inicial[/yellow]",
        ))
        token = questionary.password("Cole seu token do GitHub:", style=custom_style).ask()
        if not token or not token.strip():
            err("Token nao informado. Encerrando.")
            pause_exit(1)
        save_token(token.strip())
        GITHUB_TOKEN = token.strip()
        success(f"Token salvo em {TOKEN_FILE}")
        console.print()


def check_git_installed():
    try:
        r = subprocess.run(
            ["git", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode != 0:
            raise RuntimeError(r.stderr)
        return r.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError) as e:
        err("Git nao encontrado no sistema!")
        warn("Instale o Git em: https://git-scm.com/download/win")
        console.print(f"[dim]Detalhe: {e}[/dim]")
        pause_exit(1)


# ============================================================
#  GITHUB API
# ============================================================
def gh_headers():
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def reset_token():
    """Apaga o token salvo e pede um novo."""
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
    warn("Token removido. Reinicie o programa para configurar novamente.")


def gh_get_user():
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Autenticando no GitHub..."),
        console=console, transient=True,
    ) as p:
        p.add_task("auth", total=None)
        r = requests.get(f"{API_BASE}/user", headers=gh_headers(), timeout=20)
    if r.status_code == 401:
        err("Token invalido ou expirado.")
        pause_exit(1)
    if r.status_code != 200:
        err(f"Falha na autenticacao ({r.status_code}): {r.text[:200]}")
        pause_exit(1)
    return r.json()


def gh_create_repo(name, private, description=""):
    payload = {
        "name": name,
        "private": private,
        "description": description,
        "auto_init": False,
    }
    r = requests.post(
        f"{API_BASE}/user/repos",
        json=payload, headers=gh_headers(), timeout=30,
    )
    if r.status_code == 201:
        return r.json()
    msg = r.json().get("message", r.text[:200]) if r.text else "Erro desconhecido"
    errors = r.json().get("errors", []) if r.text else []
    detail = "; ".join(e.get("message", "") for e in errors)
    err(f"Erro ao criar repositorio: {msg}")
    if detail:
        console.print(f"[dim]{detail}[/dim]")
    return None


def gh_list_repos(affiliation="owner"):
    repos = []
    page = 1
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Carregando seus repositorios..."),
        console=console, transient=True,
    ) as p:
        p.add_task("repos", total=None)
        while True:
            r = requests.get(
                f"{API_BASE}/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated", "affiliation": affiliation},
                headers=gh_headers(), timeout=30,
            )
            if r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
            if len(batch) < 100:
                break
    return repos


def gh_delete_repo(owner, repo_name):
    """Apaga um repositorio no GitHub. Requer permissao 'delete_repo' no token."""
    r = requests.delete(
        f"{API_BASE}/repos/{owner}/{repo_name}",
        headers=gh_headers(), timeout=30,
    )
    if r.status_code == 204:
        return True, ""
    if r.status_code == 403:
        return False, "Sem permissao. O token precisa do escopo 'delete_repo'."
    msg = ""
    try:
        msg = r.json().get("message", r.text[:200])
    except Exception:
        msg = r.text[:200]
    return False, f"Erro {r.status_code}: {msg}"


def gh_toggle_visibility(owner, repo_name, make_private: bool):
    """Altera a visibilidade de um repositorio (publico <-> privado)."""
    payload = {"private": make_private}
    r = requests.patch(
        f"{API_BASE}/repos/{owner}/{repo_name}",
        json=payload, headers=gh_headers(), timeout=30,
    )
    if r.status_code == 200:
        return True, r.json()
    msg = ""
    try:
        msg = r.json().get("message", r.text[:200])
    except Exception:
        msg = r.text[:200]
    return False, f"Erro {r.status_code}: {msg}"


def gh_list_branches(owner, repo_name):
    """Lista todas as branches de um repositorio."""
    branches = []
    page = 1
    while True:
        r = requests.get(
            f"{API_BASE}/repos/{owner}/{repo_name}/branches",
            params={"per_page": 100, "page": page},
            headers=gh_headers(), timeout=30,
        )
        if r.status_code != 200:
            break
        batch = r.json()
        if not batch:
            break
        branches.extend(batch)
        page += 1
        if len(batch) < 100:
            break
    return branches


def gh_create_pull_request(owner, repo_name, title, head, base, body=""):
    """Cria um Pull Request no GitHub."""
    payload = {"title": title, "head": head, "base": base, "body": body}
    r = requests.post(
        f"{API_BASE}/repos/{owner}/{repo_name}/pulls",
        json=payload, headers=gh_headers(), timeout=30,
    )
    if r.status_code == 201:
        return True, r.json()
    msg = ""
    try:
        msg = r.json().get("message", r.text[:200])
        errors = r.json().get("errors", [])
        if errors:
            msg += " | " + "; ".join(e.get("message", "") for e in errors)
    except Exception:
        msg = r.text[:200]
    return False, f"Erro {r.status_code}: {msg}"


# ============================================================
#  GERACAO DE ARQUIVOS DO PROJETO (.gitignore, README, .env)
# ============================================================
GITIGNORE_COMMON = """# ===== Sistema operacional =====
.DS_Store
Thumbs.db
desktop.ini
ehthumbs.db
$RECYCLE.BIN/

# ===== Editores / IDEs =====
.vscode/
.idea/
*.swp
*.swo
*.sublime-*
*.code-workspace
.history/

# ===== Logs =====
*.log
logs/

# ===== Dependencias / build (qualquer stack) =====
# Estas pastas SEMPRE devem ser ignoradas, independente da linguagem.
# Adicionadas no nivel raiz e tambem em qualquer subpasta.
node_modules/
**/node_modules/
.venv/
**/.venv/
venv/
**/venv/
env/
__pycache__/
**/__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
target/
**/target/
build/
**/build/
dist/
**/dist/
out/
**/out/
bin/
**/bin/
obj/
**/obj/
.next/
.nuxt/
.cache/
.gradle/
vendor/
**/vendor/
.parcel-cache/
.turbo/

# ===== Arquivos sensiveis =====
.env
.env.local
.env.*.local
*.pem
*.key
secrets.json

# ===== Temporarios / cache =====
*.tmp
*.bak
"""

GITIGNORE_PYTHON = """
# ===== Python =====
__pycache__/
*.py[cod]
*$py.class
*.so
build/
dist/
*.egg-info/
.eggs/
*.egg
.venv/
venv/
env/
ENV/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
.tox/
.ipynb_checkpoints/
"""

GITIGNORE_NODE = """
# ===== Node.js =====
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
.pnp.*
.yarn/
.next/
.nuxt/
out/
dist/
build/
coverage/
"""

GITIGNORE_JAVA = """
# ===== Java =====
*.class
*.jar
*.war
*.ear
target/
.gradle/
build/
.classpath
.project
.settings/
hs_err_pid*
"""

GITIGNORE_DOTNET = """
# ===== .NET =====
bin/
obj/
*.user
*.suo
*.pdb
.vs/
"""

GITIGNORE_GO = """
# ===== Go =====
*.exe
*.exe~
*.test
*.out
vendor/
"""

GITIGNORE_RUST = """
# ===== Rust =====
target/
**/*.rs.bk
"""


# Pastas conhecidas por serem MUITO grandes (lentas no git add se nao ignoradas)
HUGE_DIRS = [
    "node_modules", ".venv", "venv", "env", "ENV",
    "target", "build", "dist", "out",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "bin", "obj", ".vs",
    ".next", ".nuxt", ".cache",
    "vendor", ".gradle",
]


def detect_huge_dirs(folder):
    """Retorna lista de pastas-problema presentes no nivel raiz."""
    found = []
    try:
        for name in HUGE_DIRS:
            p = os.path.join(folder, name)
            if os.path.isdir(p):
                found.append(name)
    except OSError:
        pass
    return found


def is_pattern_in_gitignore(gitignore_path, pattern):
    """Verifica (de forma tolerante) se um pattern ja esta no .gitignore."""
    if not os.path.exists(gitignore_path):
        return False
    try:
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                clean = line.strip()
                if not clean or clean.startswith("#"):
                    continue
                # normaliza: tira / inicial/final e compara
                normalized = clean.lstrip("/").rstrip("/")
                if normalized == pattern.strip("/"):
                    return True
    except OSError:
        pass
    return False


def detect_project_type(folder):
    """Detecta tipo(s) de projeto baseado em arquivos presentes."""
    types = set()
    try:
        files = set(os.listdir(folder))
    except OSError:
        return types

    if "package.json" in files:
        types.add("node")
    if "requirements.txt" in files or "pyproject.toml" in files or "setup.py" in files or "Pipfile" in files:
        types.add("python")
    if "pom.xml" in files or "build.gradle" in files or "build.gradle.kts" in files:
        types.add("java")
    if "go.mod" in files:
        types.add("go")
    if "Cargo.toml" in files:
        types.add("rust")
    if any(f.endswith((".csproj", ".sln", ".fsproj")) for f in files):
        types.add("dotnet")

    if not types:
        # Fallback: detecta por extensoes
        for f in files:
            lower = f.lower()
            if lower.endswith(".py"):
                types.add("python")
            elif lower.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
                types.add("node")
            elif lower.endswith(".java"):
                types.add("java")
            elif lower.endswith(".cs"):
                types.add("dotnet")
            elif lower.endswith(".go"):
                types.add("go")
            elif lower.endswith(".rs"):
                types.add("rust")
    return types


def generate_gitignore(project_types):
    parts = [GITIGNORE_COMMON]
    if "python" in project_types: parts.append(GITIGNORE_PYTHON)
    if "node"   in project_types: parts.append(GITIGNORE_NODE)
    if "java"   in project_types: parts.append(GITIGNORE_JAVA)
    if "dotnet" in project_types: parts.append(GITIGNORE_DOTNET)
    if "go"     in project_types: parts.append(GITIGNORE_GO)
    if "rust"   in project_types: parts.append(GITIGNORE_RUST)
    return "\n".join(parts).rstrip() + "\n"


def make_env_example_content(env_path):
    """Gera conteudo de .env.example a partir de um .env (zera valores)."""
    out = []
    try:
        with open(env_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\n")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    out.append(line)
                    continue
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    # Remove "export " no inicio se houver
                    if key.lower().startswith("export "):
                        key = key[7:].strip()
                    out.append(f"{key}=")
                else:
                    out.append(line)
    except OSError:
        return "# Exemplo de variaveis de ambiente\n# Copie para .env e preencha os valores\n"

    header = [
        "# Exemplo de variaveis de ambiente",
        "# Copie este arquivo para .env e preencha com seus valores reais",
        "",
    ]
    return "\n".join(header + out).rstrip() + "\n"


def ensure_in_gitignore(gitignore_path, pattern):
    """Garante que pattern esta no .gitignore (cria o arquivo se nao existir)."""
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        existing = [l.strip() for l in content.splitlines()]
        if pattern in existing:
            return
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(f"{pattern}\n")
    else:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(f"{pattern}\n")


def remove_from_gitignore(gitignore_path, pattern):
    """Remove uma entrada exata do .gitignore se existir."""
    if not os.path.exists(gitignore_path):
        return
    with open(gitignore_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    new_lines = [l for l in lines if l.strip() != pattern]
    if len(new_lines) != len(lines):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)


def has_readme(folder):
    """Verifica se ja existe algum README na pasta (case-insensitive)."""
    try:
        for f in os.listdir(folder):
            lower = f.lower()
            if lower in ("readme.md", "readme.txt", "readme.rst", "readme"):
                return True
    except OSError:
        pass
    return False


def generate_readme(repo_name, description, username, project_types):
    md = []
    md.append(f"# {repo_name}")
    md.append("")
    if description:
        md.append(f"> {description}")
        md.append("")

    md.append("## Sobre o projeto")
    md.append("")
    md.append(description or (
        f"**{repo_name}** e um projeto em desenvolvimento. "
        "Adicione aqui uma breve descricao do que ele faz, qual problema resolve e quem deve usa-lo."
    ))
    md.append("")

    md.append("## Pre-requisitos")
    md.append("")
    if "python" in project_types:
        md.append("- [Python 3.9+](https://www.python.org/downloads/)")
    if "node" in project_types:
        md.append("- [Node.js 18+](https://nodejs.org/)")
    if "java" in project_types:
        md.append("- [Java 17+](https://adoptium.net/)")
    if "go" in project_types:
        md.append("- [Go 1.21+](https://go.dev/dl/)")
    if "rust" in project_types:
        md.append("- [Rust 1.70+](https://www.rust-lang.org/tools/install)")
    if "dotnet" in project_types:
        md.append("- [.NET SDK 8.0+](https://dotnet.microsoft.com/download)")
    md.append("- [Git](https://git-scm.com/downloads)")
    md.append("")

    md.append("## Instalacao")
    md.append("")
    md.append("Clone o repositorio:")
    md.append("")
    md.append("```bash")
    md.append(f"git clone https://github.com/{username}/{repo_name}.git")
    md.append(f"cd {repo_name}")
    md.append("```")
    md.append("")

    if "python" in project_types:
        md.append("### Python")
        md.append("")
        md.append("```bash")
        md.append("# Criar ambiente virtual")
        md.append("python -m venv .venv")
        md.append("")
        md.append("# Ativar (Windows)")
        md.append(".venv\\Scripts\\activate")
        md.append("")
        md.append("# Ativar (Linux/Mac)")
        md.append("source .venv/bin/activate")
        md.append("")
        md.append("# Instalar dependencias")
        md.append("pip install -r requirements.txt")
        md.append("```")
        md.append("")

    if "node" in project_types:
        md.append("### Node.js")
        md.append("")
        md.append("```bash")
        md.append("# Instalar dependencias")
        md.append("npm install")
        md.append("# ou yarn install / pnpm install")
        md.append("```")
        md.append("")

    if "go" in project_types:
        md.append("### Go")
        md.append("")
        md.append("```bash")
        md.append("go mod download")
        md.append("```")
        md.append("")

    if "rust" in project_types:
        md.append("### Rust")
        md.append("")
        md.append("```bash")
        md.append("cargo build --release")
        md.append("```")
        md.append("")

    if "java" in project_types:
        md.append("### Java")
        md.append("")
        md.append("```bash")
        md.append("# Maven")
        md.append("mvn clean install")
        md.append("")
        md.append("# Gradle")
        md.append("./gradlew build")
        md.append("```")
        md.append("")

    if "dotnet" in project_types:
        md.append("### .NET")
        md.append("")
        md.append("```bash")
        md.append("dotnet restore")
        md.append("dotnet build")
        md.append("```")
        md.append("")

    md.append("## Configuracao")
    md.append("")
    md.append("Copie o arquivo `.env.example` para `.env` e preencha os valores:")
    md.append("")
    md.append("```bash")
    md.append("# Linux/Mac")
    md.append("cp .env.example .env")
    md.append("")
    md.append("# Windows")
    md.append("copy .env.example .env")
    md.append("```")
    md.append("")

    md.append("## Como usar")
    md.append("")
    if "python" in project_types:
        md.append("```bash")
        md.append("python main.py")
        md.append("```")
    elif "node" in project_types:
        md.append("```bash")
        md.append("npm start")
        md.append("# ou em modo de desenvolvimento")
        md.append("npm run dev")
        md.append("```")
    elif "go" in project_types:
        md.append("```bash")
        md.append("go run .")
        md.append("```")
    else:
        md.append("_Documente aqui como executar o projeto._")
    md.append("")

    md.append("## Contribuindo")
    md.append("")
    md.append("Contribuicoes sao bem-vindas! Sinta-se livre para abrir uma issue ou enviar um pull request.")
    md.append("")

    md.append("## Licenca")
    md.append("")
    md.append("Este projeto esta sob a licenca MIT.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("_README gerado automaticamente pelo **GitAutomatico**._")
    md.append("")
    return "\n".join(md)


# ============================================================
#  GITIGNORE INTERATIVO
# ============================================================

# Lista ORIGINAL imutavel (backup de fabrica)
FACTORY_IGNORE_PATTERNS = [
    # OS
    ".DS_Store", "Thumbs.db", "desktop.ini", "ehthumbs.db", "$RECYCLE.BIN/",
    # Editores
    ".vscode/", ".idea/", "*.swp", "*.swo", "*.sublime-*", "*.code-workspace", ".history/",
    # Logs
    "*.log", "logs/",
    # Node
    "node_modules/", "**/node_modules/", ".next/", ".nuxt/", ".pnp.*",
    "npm-debug.log*", "yarn-debug.log*", "yarn-error.log*", "pnpm-debug.log*",
    # Python
    "__pycache__/", "**/__pycache__/", ".venv/", "venv/", "env/", "ENV/",
    "*.py[cod]", ".pytest_cache/", ".mypy_cache/", ".ruff_cache/",
    "*.egg-info/", ".eggs/", ".coverage", "htmlcov/", ".tox/", ".ipynb_checkpoints/",
    # Build / dist
    "build/", "**/build/", "dist/", "**/dist/", "out/", "**/out/",
    # Java
    "*.class", "*.jar", "*.war", "target/", ".gradle/", ".classpath", ".project",
    # .NET
    "bin/", "obj/", "*.user", "*.suo", "*.pdb", ".vs/",
    # Go
    "*.exe", "*.test", "vendor/",
    # Rust
    "**/*.rs.bk",
    # Sensiveis
    ".env", ".env.local", ".env.*.local", "*.pem", "*.key", "secrets.json",
    # Cache misc
    ".cache/", ".parcel-cache/", ".turbo/", ".gradle/", "*.tmp", "*.bak",
]


def get_default_patterns() -> list:
    """Retorna a lista padrao ativa (editada pelo usuario ou fabrica)."""
    saved = load_default_ignore()
    if saved:
        return saved
    return list(FACTORY_IGNORE_PATTERNS)


def ask_gitignore_mode() -> tuple:
    """
    Pergunta ao usuario qual modo de gitignore usar.
    Retorna (mode, patterns) onde mode e 'default' | 'custom' | 'view'.
    """
    while True:
        mode = questionary.select(
            "Como deseja configurar o .gitignore?",
            choices=[
                questionary.Choice("Lista padrao completa (recomendado)", value="default"),
                questionary.Choice("Definir lista personalizada",           value="custom"),
                questionary.Choice("Visualizar lista padrao",               value="view"),
            ],
            style=custom_style,
        ).ask()

        if mode == "view":
            current = get_default_patterns()
            console.print()
            console.print(Panel(
                "\n".join(current),
                title="[cyan]Lista padrao de gitignore[/cyan]",
                border_style="cyan", box=box.ROUNDED,
            ))
            console.print()
            continue  # volta pro menu

        if mode == "custom":
            saved = load_custom_ignore()
            if saved:
                console.print(f"[dim]Lista salva ({len(saved)} entradas):[/dim]")
                for p in saved:
                    console.print(f"  [bright_black]-[/bright_black] {p}")
                use_saved = questionary.confirm(
                    "Usar lista salva?", default=True, style=custom_style
                ).ask()
                if use_saved:
                    return "custom", saved

            console.print("[dim]Digite os padroes a ignorar, um por linha. Linha em branco para terminar.[/dim]")
            patterns = []
            while True:
                entry = questionary.text(
                    f"Padrao #{len(patterns)+1} (ENTER para finalizar):",
                    style=custom_style
                ).ask()
                if entry is None or entry.strip() == "":
                    break
                patterns.append(entry.strip())
            if patterns:
                save_custom_ignore(patterns)
                success(f"{len(patterns)} padroes salvos para proximas vezes.")
                return "custom", patterns
            else:
                warn("Nenhum padrao informado. Usando lista padrao.")
                return "default", get_default_patterns()

        # default
        return "default", get_default_patterns()


def build_gitignore_from_patterns(patterns: list) -> str:
    """Gera conteudo de .gitignore a partir de uma lista de padroes."""
    lines = ["# Gerado pelo GitAutomatico", ""]
    for p in patterns:
        lines.append(p)
    return "\n".join(lines) + "\n"


def prepare_folder(folder, repo_name, description, username, is_private, include_env, gitignore_patterns=None):
    """
    Prepara a pasta antes do envio:
      - cria .gitignore (com padroes do stack) se nao existir
      - trata .env conforme visibilidade + escolha do usuario
      - cria README.md se nao existir
    Retorna lista de acoes realizadas (strings).
    """
    actions = []
    project_types = detect_project_type(folder)

    gitignore_path    = os.path.join(folder, ".gitignore")
    env_path          = os.path.join(folder, ".env")
    env_example_path  = os.path.join(folder, ".env.example")
    readme_path       = os.path.join(folder, "README.md")
    has_env           = os.path.exists(env_path)

    # 1) .gitignore
    if not os.path.exists(gitignore_path):
        if gitignore_patterns:
            content = build_gitignore_from_patterns(gitignore_patterns)
            label = f"personalizado ({len(gitignore_patterns)} padroes)"
        else:
            content = generate_gitignore(project_types)
            types_str = ", ".join(sorted(project_types)) if project_types else "padrao"
            label = f"stack detectado: {types_str}"
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(content)
        actions.append(f".gitignore criado ({label})")
    else:
        huge = detect_huge_dirs(folder)
        added_to_existing = []
        for d in huge:
            if not is_pattern_in_gitignore(gitignore_path, d):
                ensure_in_gitignore(gitignore_path, f"{d}/")
                added_to_existing.append(d)
        if added_to_existing:
            actions.append(f"Adicionado ao .gitignore existente: {', '.join(added_to_existing)}")

    # 2) .env
    if has_env:
        if is_private and include_env:
            remove_from_gitignore(gitignore_path, ".env")
            actions.append(".env SERA ENVIADO (repo privado, escolha do usuario)")
        else:
            if not os.path.exists(env_example_path):
                with open(env_example_path, "w", encoding="utf-8") as f:
                    f.write(make_env_example_content(env_path))
                actions.append(".env.example criado a partir do .env")
            ensure_in_gitignore(gitignore_path, ".env")
            motivo = "repo publico" if not is_private else "escolha do usuario"
            actions.append(f".env sera IGNORADO ({motivo})")

    # 3) README.md
    if not has_readme(folder):
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(generate_readme(repo_name, description, username, project_types))
        actions.append("README.md criado automaticamente")

    return actions


def ask_include_env(folder, is_private):
    """
    Se for repo privado E existir .env, pergunta se deve incluir.
    Repo publico: sempre False (e mostra aviso).
    Sem .env: retorna False (nao tem o que incluir).
    """
    env_path = os.path.join(folder, ".env")
    if not os.path.exists(env_path):
        return False

    if not is_private:
        console.print()
        warn("Arquivo [bold].env[/bold] detectado. Como o repositorio e [bold red]PUBLICO[/bold red], "
             "ele NAO sera enviado. Sera criado um [bold].env.example[/bold] no lugar.")
        return False

    console.print()
    info("Arquivo [bold].env[/bold] detectado. O repositorio e [bold green]PRIVADO[/bold green].")
    return questionary.confirm(
        "Deseja INCLUIR o .env no envio?",
        default=False,
        style=custom_style,
    ).ask() or False


# ============================================================
#  GIT ADD COM CONTADOR EM TEMPO REAL
# ============================================================
def git_add_with_counter(folder):
    """
    Roda 'git add --verbose .' transmitindo a saida em tempo real
    e mostrando contador + ultimo arquivo. Evita aparencia de "preso".
    """
    process = subprocess.Popen(
        ["git", "add", "--verbose", "."],
        cwd=folder,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    state = {"count": 0, "last": ""}

    def render():
        t = Text()
        t.append("  [>] ", style="bold cyan")
        t.append("Indexando arquivos: ", style="cyan")
        t.append(f"{state['count']}", style="bold green")
        if state["last"]:
            disp = state["last"]
            if len(disp) > 70:
                disp = "..." + disp[-67:]
            t.append(f"  {disp}", style="bright_black")
        return t

    try:
        with Live(render(), console=console, refresh_per_second=10, transient=False) as live:
            for raw in iter(process.stdout.readline, ""):
                line = raw.rstrip()
                if not line:
                    continue
                state["count"] += 1
                if line.startswith("add '") and line.endswith("'"):
                    state["last"] = line[5:-1]
                else:
                    state["last"] = line
                live.update(render())
            process.wait()
            live.update(render())
    finally:
        if process.poll() is None:
            process.terminate()

    return process.returncode, state["count"]


def warn_huge_dirs_if_any(folder):
    """Avisa o usuario sobre pastas pesadas detectadas (sem bloquear)."""
    huge = detect_huge_dirs(folder)
    if not huge:
        return
    console.print()
    warn(f"Pastas potencialmente grandes detectadas: [bold]{', '.join(huge)}[/bold]")
    console.print("  [dim]Elas serao adicionadas ao .gitignore (se ainda nao estiverem) e ignoradas no envio.[/dim]")


# ============================================================
#  GIT OPS
# ============================================================
def run_git(args, cwd, check=False):
    r = subprocess.run(
        ["git", *args],
        cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip())
    return r


def build_auth_url(clone_url, username):
    return clone_url.replace("https://", f"https://{username}:{GITHUB_TOKEN}@")


def push_to_new_repo(folder, repo_info, username, description, include_env, gitignore_patterns=None):
    is_private = bool(repo_info.get("private", False))

    # Prepara a pasta: .gitignore, README, .env handling
    info("Preparando arquivos do projeto...")
    actions = prepare_folder(folder, repo_info["name"], description, username, is_private, include_env, gitignore_patterns)
    if actions:
        for a in actions:
            console.print(f"  [bright_black]+[/bright_black] [white]{a}[/white]")
    else:
        console.print("  [dim](nenhum arquivo novo gerado - tudo ja existe)[/dim]")
    console.print()

    warn_huge_dirs_if_any(folder)

    auth_url = build_auth_url(repo_info["clone_url"], username)

    # 1) Init / branch (rapido, ok com spinner)
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        t = progress.add_task("[cyan]Preparando repositorio local...", total=None)

        git_dir = os.path.join(folder, ".git")
        if not os.path.exists(git_dir):
            progress.update(t, description="[cyan]Inicializando repositorio local...")
            run_git(["init"], folder, check=True)
            run_git(["branch", "-M", "main"], folder)

        # Desliga conversao CRLF (mais rapido + sem warnings em pastas grandes)
        run_git(["config", "core.autocrlf", "false"], folder)
        run_git(["config", "core.safecrlf", "false"], folder)

    # 2) git add com contador em tempo real (etapa potencialmente lenta)
    rc, added = git_add_with_counter(folder)
    if rc != 0:
        return False, f"git add falhou (codigo {rc})"
    success(f"{added} arquivos indexados.")
    console.print()

    # 3) commit / remote / push
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        t = progress.add_task("[cyan]Finalizando...", total=None)

        # Configura identity se nao tiver
        cfg_name = run_git(["config", "user.name"], folder)
        cfg_mail = run_git(["config", "user.email"], folder)
        if cfg_name.returncode != 0 or not cfg_name.stdout.strip():
            run_git(["config", "user.name", username], folder)
        if cfg_mail.returncode != 0 or not cfg_mail.stdout.strip():
            run_git(["config", "user.email", f"{username}@users.noreply.github.com"], folder)

        progress.update(t, description="[cyan]Criando commit...")
        c = run_git(["commit", "-m", "Initial commit via GitAutomatico"], folder)
        if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr).lower():
            # Se ja tinha commits, ignora
            pass

        progress.update(t, description="[cyan]Configurando remote origin...")
        run_git(["remote", "remove", "origin"], folder)
        run_git(["remote", "add", "origin", auth_url], folder, check=True)

        progress.update(t, description="[cyan]Enviando para o GitHub...")
        push = run_git(["push", "-u", "origin", "main", "--force"], folder)

        if push.returncode == 0:
            progress.update(t, description="[green]Push concluido!")
            return True, ""
        else:
            # Tenta master se main falhou
            run_git(["branch", "-M", "main"], folder)
            push2 = run_git(["push", "-u", "origin", "main", "--force"], folder)
            if push2.returncode == 0:
                return True, ""
            msg = (push2.stderr or push2.stdout).strip()
            # Mascarar o token nos logs
            msg = msg.replace(GITHUB_TOKEN, "***TOKEN***")
            return False, msg


def push_to_existing_repo(folder, repo_info, username, include_env, gitignore_patterns=None,
                           target_branch=None, branch_mode="default", commit_msg=None):
    """
    Clona o repositorio existente em um diretorio temporario,
    copia o conteudo da pasta selecionada por cima,
    aplica prepare_folder (gitignore/README/.env) e da push.

    branch_mode: 'default' (branch padrao), 'new' (cria branch nova), 'existing' (branch existente)
    target_branch: nome da branch destino (se None, usa default_branch)
    """
    auth_url = build_auth_url(repo_info["clone_url"], username)
    default_branch = repo_info.get("default_branch") or "main"
    is_private = bool(repo_info.get("private", False))
    push_branch = target_branch or default_branch

    tmp = tempfile.mkdtemp(prefix="gitautomatico_")
    clone_dir = os.path.join(tmp, "repo")

    try:
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            t = progress.add_task("[cyan]Clonando repositorio existente...", total=None)

            r = subprocess.run(
                ["git", "clone", auth_url, clone_dir],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                msg = (r.stderr or r.stdout).strip().replace(GITHUB_TOKEN, "***TOKEN***")
                return False, f"Falha ao clonar: {msg}"

            # Gerenciar branch
            if branch_mode == "new":
                progress.update(t, description=f"[cyan]Criando branch '{push_branch}'...")
                run_git(["checkout", "-b", push_branch], clone_dir, check=True)
            elif branch_mode == "existing" and push_branch != default_branch:
                progress.update(t, description=f"[cyan]Mudando para branch '{push_branch}'...")
                # Tenta checkout da branch remota
                checkout = run_git(["checkout", push_branch], clone_dir)
                if checkout.returncode != 0:
                    # Tenta tracking
                    checkout2 = run_git(["checkout", "-b", push_branch, f"origin/{push_branch}"], clone_dir)
                    if checkout2.returncode != 0:
                        return False, f"Branch '{push_branch}' nao encontrada."

            progress.update(t, description="[cyan]Copiando arquivos da pasta selecionada...")

            # Copia o conteudo da pasta selecionada para dentro do clone (sem sobrescrever .git)
            for item in os.listdir(folder):
                if item == ".git":
                    continue
                src = os.path.join(folder, item)
                dst = os.path.join(clone_dir, item)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst, ignore_errors=True)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

        # Prepara a pasta clonada (fora do Progress pra poder imprimir)
        info("Preparando arquivos do projeto...")
        actions = prepare_folder(
            clone_dir, repo_info["name"],
            repo_info.get("description") or "",
            username, is_private, include_env, gitignore_patterns,
        )
        if actions:
            for a in actions:
                console.print(f"  [bright_black]+[/bright_black] [white]{a}[/white]")
        else:
            console.print("  [dim](nenhum arquivo novo gerado - tudo ja existe)[/dim]")
        console.print()

        warn_huge_dirs_if_any(clone_dir)

        # Identity
        run_git(["config", "user.name", username], clone_dir)
        run_git(["config", "user.email", f"{username}@users.noreply.github.com"], clone_dir)

        # git add com contador em tempo real
        rc, added = git_add_with_counter(clone_dir)
        if rc != 0:
            return False, f"git add falhou (codigo {rc})"
        success(f"{added} arquivos indexados.")
        console.print()

        final_msg = commit_msg or "Update via GitAutomatico"

        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            t = progress.add_task("[cyan]Verificando alteracoes...", total=None)

            status = run_git(["status", "--porcelain"], clone_dir)
            if not status.stdout.strip():
                progress.update(t, description="[yellow]Nada para commitar (arquivos identicos).")
                return True, "no_changes"

            progress.update(t, description="[cyan]Criando commit...")
            run_git(["commit", "-m", final_msg], clone_dir, check=True)

            progress.update(t, description=f"[cyan]Enviando para origin/{push_branch}...")
            push = run_git(["push", "origin", push_branch], clone_dir)
            if push.returncode != 0:
                msg = (push.stderr or push.stdout).strip().replace(GITHUB_TOKEN, "***TOKEN***")
                return False, msg

            progress.update(t, description="[green]Push concluido!")
            return True, ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)




# ============================================================
#  SELECAO DE PASTA (tkinter)
# ============================================================
def select_folder(title="Selecione a pasta"):
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title=title, mustexist=True)
        root.destroy()
        return folder or None
    except Exception as e:
        err(f"Falha ao abrir janela de selecao: {e}")
        return None


# ============================================================
#  FLUXOS
# ============================================================
def flow_create(username):
    console.rule("[bold magenta]Criar novo repositorio[/bold magenta]")

    repo_name = questionary.text(
        "Nome do repositorio:",
        style=custom_style,
        validate=lambda v: True if v.strip() else "Informe um nome valido.",
    ).ask()
    if not repo_name:
        return
    repo_name = repo_name.strip().replace(" ", "-")

    visibility = questionary.select(
        "Visibilidade:",
        choices=[
            questionary.Choice("Publico  (qualquer um pode ver)", value="public"),
            questionary.Choice("Privado  (apenas voce)", value="private"),
        ],
        style=custom_style,
    ).ask()
    if visibility is None:
        return

    description = questionary.text(
        "Descricao (opcional, ENTER para pular):", style=custom_style
    ).ask() or ""

    is_private = visibility == "private"
    info(f"Criando repositorio '[bold]{repo_name}[/bold]' como [bold]{'privado' if is_private else 'publico'}[/bold]...")

    repo = gh_create_repo(repo_name, is_private, description)
    if not repo:
        pause_exit(1)

    success(f"Repositorio criado: [link={repo['html_url']}]{repo['html_url']}[/link]")
    console.print()

    info("Selecione a pasta que deseja enviar para o repositorio...")
    folder = select_folder("Selecione a pasta para enviar ao repositorio")
    if not folder:
        warn("Nenhuma pasta selecionada. Operacao cancelada.")
        return

    # Pergunta sobre .env (so pergunta se for privado e tiver .env)
    include_env = ask_include_env(folder, is_private)

    # Pergunta sobre .gitignore
    console.print()
    info("Configurando .gitignore para o repositorio...")
    _ig_mode, gitignore_patterns = ask_gitignore_mode()

    env_status = "—"
    env_path = os.path.join(folder, ".env")
    if os.path.exists(env_path):
        if is_private and include_env:
            env_status = "[green]sera enviado[/green]"
        else:
            env_status = "[yellow]ignorado / virara .env.example[/yellow]"

    console.print()
    console.print(Panel(
        f"[bold]Pasta:[/bold]      {folder}\n"
        f"[bold]Repo: [/bold]      {repo['html_url']}\n"
        f"[bold]Visib.:[/bold]     {'privado' if is_private else 'publico'}\n"
        f"[bold].env:[/bold]       {env_status}\n"
        f"[bold]Gitignore:[/bold]  {'padrao' if _ig_mode == 'default' else f'personalizado ({len(gitignore_patterns)} padroes)'}\n"
        f"[bold]Extras:[/bold]     README gerado se nao existir",
        border_style="cyan", box=box.ROUNDED, title="Resumo", title_align="left",
    ))

    confirm = questionary.confirm("Confirmar envio?", default=True, style=custom_style).ask()
    if not confirm:
        warn("Operacao cancelada pelo usuario.")
        return

    ok, msg = push_to_new_repo(folder, repo, username, description, include_env, gitignore_patterns)
    play_notification_sound()
    console.print()
    if ok:
        success(f"Tudo certo! Acesse: [link={repo['html_url']}]{repo['html_url']}[/link]")
    else:
        err("Falha no push.")
        console.print(Panel(msg, border_style="red", title="Detalhes do erro"))


def flow_existing(username):
    console.rule("[bold magenta]Usar repositorio existente[/bold magenta]")

    repos = gh_list_repos(affiliation="owner,collaborator")
    if not repos:
        warn("Nenhum repositorio encontrado na sua conta.")
        return

    # Mostra tabela bonita
    table = Table(box=box.SIMPLE_HEAVY, header_style="bold magenta", show_lines=False)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Nome", style="cyan bold")
    table.add_column("Dono", style="white")
    table.add_column("Visib.", justify="center")
    table.add_column("Atualizado", style="dim")
    for i, r in enumerate(repos[:15], 1):
        vis = "[red]priv[/red]" if r["private"] else "[green]pub[/green]"
        upd = (r.get("updated_at") or "")[:10]
        owner_name = r.get("owner", {}).get("login", "?")
        is_own = owner_name == username
        owner_display = f"[bold]{owner_name}[/bold]" if is_own else f"[dim]{owner_name}[/dim]"
        table.add_row(str(i), r["name"], owner_display, vis, upd)
    console.print(table)
    if len(repos) > 15:
        console.print(f"[dim]...e mais {len(repos) - 15} repositorios na lista de selecao abaixo.[/dim]")
    console.print()

    choices = []
    for r in repos:
        tag = "[priv]" if r["private"] else "[pub] "
        owner_name = r.get("owner", {}).get("login", "?")
        is_own = owner_name == username
        prefix = "" if is_own else f"({owner_name}) "
        desc = (r.get("description") or "").strip()
        label = f"{tag} {prefix}{r['name']}"
        if desc:
            label += f"  -  {desc[:60]}"
        choices.append(questionary.Choice(label, value=r))

    selected = questionary.select(
        f"Escolha um repositorio ({len(repos)} encontrados):",
        choices=choices,
        style=custom_style,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if selected is None:
        return

    success(f"Selecionado: [bold]{selected['name']}[/bold]  ->  {selected['html_url']}")
    console.print()

    owner = selected.get("owner", {}).get("login", username)
    default_branch = selected.get("default_branch") or "main"

    # ---- Estrategia de branch ----
    console.print()
    info("Escolha onde deseja enviar os arquivos:")

    # Carrega branches existentes para mostrar opcao
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Carregando branches..."),
        console=console, transient=True,
    ) as p:
        p.add_task("branches", total=None)
        branches = gh_list_branches(owner, selected["name"])

    branch_names = [b["name"] for b in branches]
    non_default = [b for b in branch_names if b != default_branch]

    branch_choices = [
        questionary.Choice(f"Direto na branch padrao ({default_branch})", value="default"),
        questionary.Choice("Criar uma branch nova", value="new"),
    ]
    if non_default:
        branch_choices.append(
            questionary.Choice(f"Atualizar branch existente ({len(non_default)} disponiveis)", value="existing"),
        )

    branch_strategy = questionary.select(
        "Estrategia de branch:",
        choices=branch_choices,
        style=custom_style,
    ).ask()
    if branch_strategy is None:
        return

    target_branch = None
    branch_mode = "default"

    if branch_strategy == "new":
        branch_mode = "new"
        target_branch = questionary.text(
            "Nome da nova branch:",
            style=custom_style,
            validate=lambda v: True if v.strip() and " " not in v.strip() else "Nome invalido (sem espacos).",
        ).ask()
        if not target_branch:
            return
        target_branch = target_branch.strip()
        if target_branch in branch_names:
            warn(f"Branch '{target_branch}' ja existe. Sera feito push nela como branch existente.")
            branch_mode = "existing"
    elif branch_strategy == "existing":
        branch_mode = "existing"
        br_choices = [questionary.Choice(b, value=b) for b in non_default]
        target_branch = questionary.select(
            "Selecione a branch:",
            choices=br_choices,
            style=custom_style,
            use_search_filter=True,
        ).ask()
        if not target_branch:
            return

    push_branch_display = target_branch or default_branch

    # ---- Mensagem de commit ----
    console.print()
    commit_msg = questionary.text(
        "Mensagem do commit (ENTER para padrao):",
        default="Update via GitAutomatico",
        style=custom_style,
    ).ask()
    if commit_msg is None:
        return

    info("Selecione a pasta com os arquivos que deseja enviar...")
    folder = select_folder("Selecione a pasta a ser enviada")
    if not folder:
        warn("Nenhuma pasta selecionada. Operacao cancelada.")
        return

    is_private = bool(selected.get("private", False))
    include_env = ask_include_env(folder, is_private)

    # Pergunta sobre .gitignore
    console.print()
    info("Configurando .gitignore para o repositorio...")
    _ig_mode, gitignore_patterns = ask_gitignore_mode()

    env_status = "—"
    env_path = os.path.join(folder, ".env")
    if os.path.exists(env_path):
        if is_private and include_env:
            env_status = "[green]sera enviado[/green]"
        else:
            env_status = "[yellow]ignorado / virara .env.example[/yellow]"

    branch_info = f"{push_branch_display}"
    if branch_mode == "new":
        branch_info += " [yellow](nova)[/yellow]"
    elif branch_mode == "existing" and push_branch_display != default_branch:
        branch_info += " [cyan](existente)[/cyan]"

    console.print()
    console.print(Panel(
        f"[bold]Pasta origem:[/bold]  {folder}\n"
        f"[bold]Repo destino:[/bold]  {selected['html_url']}\n"
        f"[bold]Branch:      [/bold]  {branch_info}\n"
        f"[bold]Commit:      [/bold]  {commit_msg}\n"
        f"[bold]Visib.:     [/bold]  {'privado' if is_private else 'publico'}\n"
        f"[bold].env:        [/bold]  {env_status}\n"
        f"[bold]Gitignore:  [/bold]  {'padrao' if _ig_mode == 'default' else f'personalizado ({len(gitignore_patterns)} padroes)'}\n"
        f"[bold]Extras:     [/bold]  README gerado se nao existir",
        border_style="cyan", box=box.ROUNDED, title="Resumo", title_align="left",
    ))

    confirm = questionary.confirm(
        "Os arquivos serao adicionados/sobrescritos no repositorio. Continuar?",
        default=True, style=custom_style,
    ).ask()
    if not confirm:
        warn("Operacao cancelada pelo usuario.")
        return

    ok, msg = push_to_existing_repo(
        folder, selected, username, include_env, gitignore_patterns,
        target_branch=target_branch, branch_mode=branch_mode, commit_msg=commit_msg,
    )
    play_notification_sound()
    console.print()
    if ok:
        if msg == "no_changes":
            warn("Nenhuma alteracao detectada — repositorio ja esta sincronizado.")
        else:
            success(f"Push concluido! Acesse: [link={selected['html_url']}]{selected['html_url']}[/link]")
            if branch_mode == "new":
                info(f"Branch '[bold]{target_branch}[/bold]' criada. Voce pode criar um Pull Request pelo menu principal.")
    else:
        err("Falha no push.")
        console.print(Panel(msg, border_style="red", title="Detalhes do erro"))


# ============================================================
#  FLUXO UNIFICADO DE UPLOAD
# ============================================================
def flow_upload(username):
    """Pergunta se e novo repositorio ou atualizacao de existente, depois executa."""
    console.print()
    op = questionary.select(
        "Esta operacao e:",
        choices=[
            questionary.Choice("Novo repositorio  (criar e enviar)",         value="create"),
            questionary.Choice("Atualizacao  (enviar para repositorio existente)", value="existing"),
        ],
        style=custom_style,
    ).ask()
    if op is None:
        return
    console.print()
    if op == "create":
        flow_create(username)
    else:
        flow_existing(username)


# ============================================================
#  FLUXO PULL REQUEST
# ============================================================
def flow_pull_request(username):
    """Cria Pull Requests em repositorios que tem branches alem da main."""
    console.rule("[bold magenta]Criar Pull Request[/bold magenta]")

    repos = gh_list_repos()
    if not repos:
        warn("Nenhum repositorio encontrado.")
        return

    # Filtra repos que tem mais de 1 branch
    info("Buscando repositorios com branches extras...")
    repos_with_branches = []

    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Verificando branches dos repositorios..."),
        console=console, transient=True,
    ) as p:
        p.add_task("check", total=None)
        for repo in repos:
            owner = repo.get("owner", {}).get("login", username)
            branches = gh_list_branches(owner, repo["name"])
            if len(branches) > 1:
                repos_with_branches.append((repo, branches))

    if not repos_with_branches:
        warn("Nenhum repositorio encontrado com branches alem da padrao.")
        info("Crie uma branch nova ao atualizar um repositorio pelo menu 'Enviar pasta'.")
        return

    # Tabela dos repos com branches
    table = Table(
        box=box.SIMPLE_HEAVY, header_style="bold magenta",
        show_lines=False, title=f"[bold]{len(repos_with_branches)} repositorios com branches[/bold]",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Nome", style="cyan bold")
    table.add_column("Branches", justify="center", style="yellow")
    table.add_column("Visib.", justify="center")
    for i, (repo, brs) in enumerate(repos_with_branches, 1):
        vis = "[red]priv[/red]" if repo["private"] else "[green]pub[/green]"
        br_names = ", ".join(b["name"] for b in brs[:5])
        if len(brs) > 5:
            br_names += f" +{len(brs)-5}"
        table.add_row(str(i), repo["name"], br_names, vis)
    console.print(table)
    console.print()

    # Selecionar repo
    choices = []
    for repo, brs in repos_with_branches:
        br_count = len(brs)
        label = f"{repo['name']}  ({br_count} branches)"
        choices.append(questionary.Choice(label, value=(repo, brs)))

    answer = questionary.select(
        "Selecione o repositorio para criar PR:",
        choices=choices,
        style=custom_style,
        use_search_filter=True,
        use_jk_keys=False,
    ).ask()
    if answer is None:
        return

    selected_repo, selected_branches = answer
    owner = selected_repo.get("owner", {}).get("login", username)
    default_branch = selected_repo.get("default_branch") or "main"
    branch_names = [b["name"] for b in selected_branches]

    success(f"Repo: [bold]{selected_repo['name']}[/bold]")
    console.print()

    # Branch de origem (head) - sem a default
    non_default = [b for b in branch_names if b != default_branch]
    if not non_default:
        warn("Nenhuma branch diferente da padrao encontrada.")
        return

    head_branch = questionary.select(
        "Branch de ORIGEM (head) - de onde vem as mudancas:",
        choices=[questionary.Choice(b, value=b) for b in non_default],
        style=custom_style,
    ).ask()
    if not head_branch:
        return

    # Branch de destino (base)
    base_options = [b for b in branch_names if b != head_branch]
    if len(base_options) == 1:
        base_branch = base_options[0]
        info(f"Branch de destino: [bold]{base_branch}[/bold] (unica opcao)")
    else:
        base_branch = questionary.select(
            "Branch de DESTINO (base) - onde as mudancas serao aplicadas:",
            choices=[questionary.Choice(b, value=b) for b in base_options],
            style=custom_style,
        ).ask()
        if not base_branch:
            return

    # Titulo e descricao do PR
    console.print()
    pr_title = questionary.text(
        "Titulo do Pull Request:",
        default=f"Merge {head_branch} into {base_branch}",
        style=custom_style,
        validate=lambda v: True if v.strip() else "Informe um titulo.",
    ).ask()
    if not pr_title:
        return

    pr_body = questionary.text(
        "Descricao do PR (ENTER para pular):",
        default="",
        style=custom_style,
    ).ask() or ""

    # Resumo
    console.print()
    console.print(Panel(
        f"[bold]Repositorio:[/bold]  {selected_repo['name']}\n"
        f"[bold]Origem:     [/bold]  [yellow]{head_branch}[/yellow]\n"
        f"[bold]Destino:    [/bold]  [green]{base_branch}[/green]\n"
        f"[bold]Titulo:     [/bold]  {pr_title}\n"
        f"[bold]Descricao:  [/bold]  {pr_body or '[dim]sem descricao[/dim]'}",
        border_style="cyan", box=box.ROUNDED, title="Resumo do Pull Request", title_align="left",
    ))

    confirm = questionary.confirm("Criar Pull Request?", default=True, style=custom_style).ask()
    if not confirm:
        warn("Operacao cancelada.")
        return

    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[cyan]Criando Pull Request..."),
        console=console, transient=True,
    ) as p:
        p.add_task("pr", total=None)
        ok, result = gh_create_pull_request(owner, selected_repo["name"], pr_title, head_branch, base_branch, pr_body)

    console.print()
    if ok:
        pr_url = result.get("html_url", "")
        pr_number = result.get("number", "?")
        success(f"Pull Request #{pr_number} criado com sucesso!")
        if pr_url:
            info(f"Acesse: [link={pr_url}]{pr_url}[/link]")
    else:
        err(f"Falha ao criar Pull Request: {result}")


# ============================================================
#  FLUXO VISUALIZAR REPOSITORIOS
# ============================================================
def flow_view_repos(username):
    """Lista repositorios e permite apagar ou trocar visibilidade."""
    while True:
        console.rule("[bold magenta]Seus repositorios[/bold magenta]")

        repos = gh_list_repos()
        if not repos:
            warn("Nenhum repositorio encontrado na sua conta.")
            return

        # Tabela completa
        table = Table(
            box=box.SIMPLE_HEAVY, header_style="bold magenta",
            show_lines=False, title=f"[bold]{len(repos)} repositorios[/bold]",
        )
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Nome", style="cyan bold")
        table.add_column("Visib.", justify="center")
        table.add_column("Descricao", style="dim", max_width=40)
        table.add_column("Linguagem", style="white", justify="center")
        table.add_column("Atualizado", style="dim")
        for i, r in enumerate(repos, 1):
            vis = "[red]privado[/red]" if r["private"] else "[green]publico[/green]"
            upd = (r.get("updated_at") or "")[:10]
            lang = r.get("language") or "—"
            desc = (r.get("description") or "")[:40]
            table.add_row(str(i), r["name"], vis, desc, lang, upd)
        console.print(table)
        console.print()

        # Menu de acao
        repo_action = questionary.select(
            "O que deseja fazer?",
            choices=[
                questionary.Choice("Selecionar repositorio para gerenciar", value="select"),
                questionary.Choice("Voltar ao menu principal",              value="back"),
            ],
            style=custom_style,
        ).ask()

        if repo_action in (None, "back"):
            return

        # Selecionar repo
        choices = []
        for r in repos:
            tag = "[priv]" if r["private"] else "[pub] "
            desc = (r.get("description") or "").strip()
            label = f"{tag} {r['name']}"
            if desc:
                label += f"  -  {desc[:60]}"
            choices.append(questionary.Choice(label, value=r))

        selected = questionary.select(
            f"Selecione o repositorio ({len(repos)} encontrados):",
            choices=choices,
            style=custom_style,
            use_search_filter=True,
            use_jk_keys=False,
        ).ask()
        if selected is None:
            continue

        is_private = bool(selected.get("private", False))
        vis_label = "privado" if is_private else "publico"
        vis_color = "red" if is_private else "green"
        owner = selected.get("owner", {}).get("login", username)

        # Detalhes do repo selecionado
        console.print()
        detail_table = Table.grid(padding=(0, 2))
        detail_table.add_column(style="bold cyan")
        detail_table.add_column(style="white")
        detail_table.add_row("Nome:",       f"[bold]{selected['name']}[/bold]")
        detail_table.add_row("URL:",        f"[link={selected['html_url']}]{selected['html_url']}[/link]")
        detail_table.add_row("Visib.:",     f"[{vis_color}]{vis_label}[/{vis_color}]")
        detail_table.add_row("Descricao:",  selected.get("description") or "[dim]sem descricao[/dim]")
        detail_table.add_row("Linguagem:",  selected.get("language") or "[dim]nao detectada[/dim]")
        detail_table.add_row("Branch:",     selected.get("default_branch") or "main")
        detail_table.add_row("Criado:",     (selected.get("created_at") or "")[:10])
        detail_table.add_row("Atualizado:", (selected.get("updated_at") or "")[:10])
        console.print(Panel(
            detail_table,
            title=f"[bold cyan]{selected['name']}[/bold cyan]",
            border_style="cyan", box=box.ROUNDED, title_align="left",
        ))
        console.print()

        toggle_label = "Tornar privado" if not is_private else "Tornar publico"
        new_vis = "privado" if not is_private else "publico"

        manage_action = questionary.select(
            f"Gerenciar '{selected['name']}':",
            choices=[
                questionary.Choice(f"Trocar visibilidade  ({vis_label} -> {new_vis})", value="toggle"),
                questionary.Choice("Apagar repositorio",                               value="delete"),
                questionary.Choice("Voltar a lista",                                   value="back"),
            ],
            style=custom_style,
        ).ask()

        if manage_action in (None, "back"):
            console.print()
            continue

        if manage_action == "toggle":
            make_private = not is_private
            new_vis_confirm = "[bold red]PRIVADO[/bold red]" if make_private else "[bold green]PUBLICO[/bold green]"
            console.print()
            warn(f"Voce esta prestes a tornar [bold]{selected['name']}[/bold] {new_vis_confirm}.")
            confirm = questionary.confirm(
                f"Confirmar alteracao de visibilidade?",
                default=False, style=custom_style,
            ).ask()
            if not confirm:
                warn("Operacao cancelada.")
                console.print()
                continue

            with Progress(
                SpinnerColumn(style="cyan"),
                TextColumn("[cyan]Alterando visibilidade..."),
                console=console, transient=True,
            ) as p:
                p.add_task("toggle", total=None)
                ok, result = gh_toggle_visibility(owner, selected["name"], make_private)

            console.print()
            if ok:
                final_vis = "privado" if make_private else "publico"
                success(f"Repositorio [bold]{selected['name']}[/bold] agora e [bold]{final_vis}[/bold].")
            else:
                err(f"Falha ao alterar visibilidade: {result}")

        elif manage_action == "delete":
            console.print()
            console.print(Panel(
                f"[bold red]ATENCAO![/bold red]\n\n"
                f"Voce esta prestes a [bold red]APAGAR PERMANENTEMENTE[/bold red] o repositorio:\n\n"
                f"  [bold]{owner}/{selected['name']}[/bold]\n\n"
                f"Esta acao e [bold]IRREVERSIVEL[/bold]. Todo o historico, issues,\n"
                f"pull requests e configuracoes serao perdidos.",
                border_style="red", box=box.DOUBLE, title="[red]Confirmacao de exclusao[/red]",
            ))

            # Dupla confirmacao
            confirm1 = questionary.confirm(
                "Tem certeza que deseja APAGAR este repositorio?",
                default=False, style=custom_style,
            ).ask()
            if not confirm1:
                warn("Operacao cancelada.")
                console.print()
                continue

            confirm_name = questionary.text(
                f"Digite o nome do repositorio para confirmar ({selected['name']}):",
                style=custom_style,
            ).ask()
            if confirm_name is None or confirm_name.strip() != selected["name"]:
                warn("Nome nao confere. Operacao cancelada.")
                console.print()
                continue

            with Progress(
                SpinnerColumn(style="cyan"),
                TextColumn("[cyan]Apagando repositorio..."),
                console=console, transient=True,
            ) as p:
                p.add_task("delete", total=None)
                ok, msg = gh_delete_repo(owner, selected["name"])

            console.print()
            if ok:
                success(f"Repositorio [bold]{selected['name']}[/bold] apagado com sucesso.")
            else:
                err(f"Falha ao apagar: {msg}")

        console.print()
        cont = questionary.confirm("Continuar gerenciando repositorios?", default=True, style=custom_style).ask()
        if not cont:
            return
        console.print()


# ============================================================
#  MAIN
# ============================================================
def main():
    banner()
    check_token()
    git_version = check_git_installed()
    console.print(f"[dim]{git_version}[/dim]\n")

    user = gh_get_user()
    username = user["login"]

    user_panel = Table.grid(padding=(0, 2))
    user_panel.add_column(style="bold cyan")
    user_panel.add_column(style="white")
    user_panel.add_row("Usuario:", f"[bold]{username}[/bold]")
    user_panel.add_row("Nome:",    user.get("name") or "[dim]nao definido[/dim]")
    user_panel.add_row("Config:",  f"[dim]{get_config_dir()}[/dim]")
    user_panel.add_row("Repos:",   f"{user.get('public_repos', 0)} publicos / {user.get('total_private_repos', 0)} privados")
    console.print(Panel(user_panel, title="[bold green]Autenticado[/bold green]",
                        border_style="green", box=box.ROUNDED, title_align="left"))
    console.print()

    while True:
        action = questionary.select(
            "O que deseja fazer?",
            choices=[
                questionary.Choice("Enviar pasta para o GitHub",             value="upload"),
                questionary.Choice("Pull Request",                           value="pull_request"),
                questionary.Choice("Visualizar repositorios",                value="view_repos"),
                questionary.Choice("Gerenciar listas de gitignore",            value="gitignore"),
                questionary.Separator(),
                questionary.Choice("Trocar token do GitHub",                 value="token"),
                questionary.Choice("Sair",                                   value="exit"),
            ],
            style=custom_style,
        ).ask()

        if action in (None, "exit"):
            console.print("\n[bold cyan]Ate logo![/bold cyan]\n")
            break

        console.print()
        if action == "upload":
            flow_upload(username)
        elif action == "pull_request":
            flow_pull_request(username)
        elif action == "view_repos":
            flow_view_repos(username)
        elif action == "gitignore":
            _manage_gitignore()
        elif action == "token":
            reset_token()
            check_token()
            user = gh_get_user()
            username = user["login"]
            success(f"Novo usuario autenticado: {username}")

        console.print()
        again = questionary.confirm("Deseja realizar outra operacao?", default=False, style=custom_style).ask()
        if not again:
            console.print("\n[bold cyan]Ate logo![/bold cyan]\n")
            break
        banner()


def _manage_gitignore():
    """Menu para gerenciar listas de gitignore."""
    while True:
        # Verifica estado das listas
        has_custom_default = DEFAULT_IGNORE_FILE.exists()
        has_custom_list = CUSTOM_IGNORE_FILE.exists()
        current_default = get_default_patterns()

        status_default = "[yellow]editada[/yellow]" if has_custom_default else "[green]fabrica[/green]"
        status_custom = f"[green]{len(load_custom_ignore())} padroes[/green]" if has_custom_list else "[dim]nao definida[/dim]"

        console.print()
        console.print(Panel(
            f"[bold]Lista padrao:[/bold]         {status_default} ({len(current_default)} padroes)\n"
            f"[bold]Lista personalizada:[/bold]  {status_custom}",
            title="[cyan]Status das listas[/cyan]",
            border_style="cyan", box=box.ROUNDED, title_align="left",
        ))
        console.print()

        op = questionary.select(
            "Gerenciar gitignore:",
            choices=[
                questionary.Choice("Visualizar lista padrao atual",                     value="view_default"),
                questionary.Choice("Editar lista padrao (remover/adicionar padroes)",   value="edit_default"),
                questionary.Choice("Restaurar lista padrao de fabrica",                 value="restore_factory"),
                questionary.Separator(),
                questionary.Choice("Editar lista personalizada (avulsa)",               value="edit_custom"),
                questionary.Choice("Apagar lista personalizada salva",                  value="delete_custom"),
                questionary.Separator(),
                questionary.Choice("Voltar",                                            value="back"),
            ],
            style=custom_style,
        ).ask()

        if op in (None, "back"):
            return

        if op == "view_default":
            console.print()
            source = "[yellow]editada pelo usuario[/yellow]" if has_custom_default else "[green]fabrica (original)[/green]"
            patterns = get_default_patterns()
            numbered = []
            for i, p in enumerate(patterns, 1):
                numbered.append(f"  [dim]{i:3}.[/dim] {p}")
            console.print(Panel(
                "\n".join(numbered),
                title=f"[cyan]Lista padrao ({len(patterns)} padroes) - {source}[/cyan]",
                border_style="cyan", box=box.ROUNDED,
            ))

        elif op == "edit_default":
            _edit_default_gitignore()

        elif op == "restore_factory":
            if not has_custom_default:
                warn("A lista padrao ja e a de fabrica.")
            else:
                confirm = questionary.confirm(
                    "Restaurar lista padrao para a versao de fabrica? Suas edicoes serao perdidas.",
                    default=False, style=custom_style,
                ).ask()
                if confirm:
                    DEFAULT_IGNORE_FILE.unlink(missing_ok=True)
                    success(f"Lista padrao restaurada ({len(FACTORY_IGNORE_PATTERNS)} padroes de fabrica).")
                else:
                    warn("Operacao cancelada.")

        elif op == "edit_custom":
            ask_gitignore_mode()

        elif op == "delete_custom":
            if CUSTOM_IGNORE_FILE.exists():
                CUSTOM_IGNORE_FILE.unlink()
                success("Lista personalizada removida.")
            else:
                warn("Nenhuma lista personalizada salva.")

        console.print()
        cont = questionary.confirm("Continuar gerenciando listas?", default=True, style=custom_style).ask()
        if not cont:
            return


def _edit_default_gitignore():
    """Permite ao usuario editar a lista padrao de gitignore interativamente."""
    current = get_default_patterns()

    console.print()
    console.rule("[bold magenta]Editar lista padrao de gitignore[/bold magenta]")
    console.print()
    console.print("[dim]Use ESPACO para marcar/desmarcar e ENTER para confirmar.[/dim]")
    console.print("[dim]Padroes DESMARCADOS serao removidos da lista.[/dim]")
    console.print()

    # Checkbox para selecionar quais manter
    choices = [questionary.Choice(p, checked=True) for p in current]
    kept = questionary.checkbox(
        f"Selecione os padroes a MANTER ({len(current)} atuais):",
        choices=choices,
        style=custom_style,
    ).ask()

    if kept is None:
        warn("Operacao cancelada.")
        return

    removed_count = len(current) - len(kept)
    if removed_count > 0:
        console.print(f"  [yellow]{removed_count} padrao(oes) removido(s)[/yellow]")

    # Perguntar se quer adicionar novos
    console.print()
    add_more = questionary.confirm(
        "Deseja adicionar novos padroes?",
        default=False, style=custom_style,
    ).ask()

    new_patterns = list(kept)  # copia
    if add_more:
        console.print("[dim]Digite os padroes a adicionar, um por linha. Linha em branco para terminar.[/dim]")
        while True:
            entry = questionary.text(
                f"Novo padrao #{len(new_patterns) - len(kept) + 1} (ENTER para finalizar):",
                style=custom_style,
            ).ask()
            if entry is None or entry.strip() == "":
                break
            pat = entry.strip()
            if pat in new_patterns:
                warn(f"'{pat}' ja esta na lista.")
            else:
                new_patterns.append(pat)
                success(f"Adicionado: {pat}")

    # Resumo e confirmacao
    diff_removed = [p for p in current if p not in new_patterns]
    diff_added = [p for p in new_patterns if p not in current]

    console.print()
    summary_lines = [f"[bold]Total final:[/bold] {len(new_patterns)} padroes"]
    if diff_removed:
        summary_lines.append(f"[bold red]Removidos ({len(diff_removed)}):[/bold red]")
        for p in diff_removed:
            summary_lines.append(f"  [red]- {p}[/red]")
    if diff_added:
        summary_lines.append(f"[bold green]Adicionados ({len(diff_added)}):[/bold green]")
        for p in diff_added:
            summary_lines.append(f"  [green]+ {p}[/green]")
    if not diff_removed and not diff_added:
        summary_lines.append("[dim]Nenhuma alteracao.[/dim]")

    console.print(Panel(
        "\n".join(summary_lines),
        title="[cyan]Resumo das alteracoes[/cyan]",
        border_style="cyan", box=box.ROUNDED, title_align="left",
    ))

    if not diff_removed and not diff_added:
        info("Lista nao foi alterada.")
        return

    confirm = questionary.confirm(
        "Salvar alteracoes na lista padrao?",
        default=True, style=custom_style,
    ).ask()
    if confirm:
        save_default_ignore(new_patterns)
        success(f"Lista padrao atualizada com {len(new_patterns)} padroes.")
    else:
        warn("Alteracoes descartadas.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Operacao cancelada pelo usuario.[/yellow]")
    except requests.exceptions.RequestException as e:
        err(f"Erro de rede: {e}")
        pause_exit(1)
    except Exception as e:
        err(f"Erro inesperado: {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        pause_exit(1)
    pause_exit(0)
