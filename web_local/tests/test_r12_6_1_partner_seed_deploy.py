from __future__ import annotations

from pathlib import Path

from engine.central_cte_modular.repositories.partner_table_repository import PartnerTableRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED = PROJECT_ROOT / "deploy" / "vps" / "seed" / "partner_tables"


def test_release_partner_seed_is_complete_and_valid() -> None:
    files = sorted((SEED / "files").glob("*.xlsx"))
    assert len(files) == 16
    assert (SEED / "compiled_signature.txt").is_file()
    assert (SEED / "release_seed_version.txt").read_text(encoding="utf-8").strip().endswith("R12.10")
    tables = PartnerTableRepository().load(SEED / "cadastro_tabelas_parceiros_compilada.xlsx")
    assert len(tables["partners"]) == 16
    assert len(tables["rules"]) == 289
    assert len(tables["regions"]) == 390
    assert len(tables["extras"]) == 104
    assert tables["partners"]["AC_LOG_C_VARGAS"]["cnpj"] == "34059736000157"


def test_docker_image_copies_only_safe_partner_seed() -> None:
    dockerfile = (PROJECT_ROOT / "deploy" / "vps" / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / "deploy" / "vps" / ".dockerignore").read_text(encoding="utf-8")
    entrypoint = (PROJECT_ROOT / "deploy" / "vps" / "scripts" / "container_entrypoint.sh").read_text(encoding="utf-8")
    assert "COPY deploy/vps/seed/partner_tables/ /app/seed/partner_tables/" in dockerfile
    assert "web_local/data" in dockerignore
    assert 'PARTNER_TARGET_ROOT="$DATA_ROOT/partner_tables"' in entrypoint
    assert "release_seed_version" in entrypoint
    assert "history/release_seed_" in entrypoint


def test_version_is_r12_6_1() -> None:
    server = (PROJECT_ROOT / "web_local" / "server.py").read_text(encoding="utf-8")
    app_js = (PROJECT_ROOT / "web_local" / "static" / "app.js").read_text(encoding="utf-8")
    compose = (PROJECT_ROOT / "deploy" / "vps" / "compose.yaml").read_text(encoding="utf-8")
    assert "MVP13 R12.13" in server
    assert "MVP13 R12.13" in app_js
    assert "central-cte-dacte:r12.13" in compose
