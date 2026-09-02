# -*- coding: utf-8 -*-
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = WEB_ROOT.parent
DATA_ROOT = Path(os.environ.get("CENTRAL_CTE_DATA_ROOT") or (WEB_ROOT / "data")).expanduser().resolve()
SECURITY_ROOT = DATA_ROOT / "security"

if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))

from security import AuthManager  # noqa: E402


def main() -> int:
    print("\nCENTRAL CT-e / DACTE — CRIAÇÃO LOCAL DO PRIMEIRO DESENVOLVEDOR\n")
    print("Feche o servidor antes de continuar. Esta função não é publicada na internet.")
    auth = AuthManager(SECURITY_ROOT)
    if auth.developer_exists():
        print("\nO primeiro perfil Desenvolvedor já existe.")
        print("Entre com esse perfil para criar outros desenvolvedores pela tela de usuários.")
        return 2
    username = input("Usuário: ").strip()
    display_name = input("Nome de exibição: ").strip()
    password = getpass.getpass("Senha (mínimo de 10 caracteres, com letra e número): ")
    confirmation = getpass.getpass("Confirme a senha: ")
    if password != confirmation:
        print("\nAs senhas não são iguais.")
        return 3
    try:
        user = auth.create_first_developer_local(username, display_name, password)
    except Exception as exc:
        print(f"\nNão foi possível criar o Desenvolvedor: {exc}")
        return 4
    print("\nPerfil Desenvolvedor criado com segurança.")
    print(f"Usuário: {user.username}")
    print("Agora inicie a Central CT-e e faça login normalmente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
