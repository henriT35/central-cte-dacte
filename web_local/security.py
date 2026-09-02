# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PASSWORD_ITERATIONS = 310_000
SESSION_TTL_SECONDS = 8 * 60 * 60
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_MAX_FAILURES = 5
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,39}$")
ROLES = {"desenvolvedor", "admin", "operador", "consulta"}
TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%"
TEMP_PASSWORD_LENGTH = 16


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path, fallback: Any) -> Any:
    try:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    temporary.replace(path)


def normalize_username(value: Any) -> str:
    return str(value or "").strip().lower()


def validate_username(value: Any) -> str:
    username = normalize_username(value)
    if not USERNAME_PATTERN.fullmatch(username):
        raise ValueError("O usuário deve ter de 3 a 40 caracteres: letras minúsculas, números, ponto, hífen ou sublinhado.")
    return username


def validate_password(value: Any) -> str:
    password = str(value or "")
    if len(password) < 10:
        raise ValueError("A senha deve ter pelo menos 10 caracteres.")
    if len(password) > 200:
        raise ValueError("A senha excede o limite permitido.")
    if not any(char.isalpha() for char in password) or not any(char.isdigit() for char in password):
        raise ValueError("A senha deve conter pelo menos uma letra e um número.")
    return password


def generate_temporary_password(length: int = TEMP_PASSWORD_LENGTH) -> str:
    size = max(12, min(int(length or TEMP_PASSWORD_LENGTH), 64))
    while True:
        candidate = "".join(secrets.choice(TEMP_PASSWORD_ALPHABET) for _ in range(size))
        if any(char.isalpha() for char in candidate) and any(char.isdigit() for char in candidate):
            return candidate


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = PASSWORD_ITERATIONS) -> dict[str, Any]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return {
        "algorithm": "pbkdf2-sha256",
        "iterations": iterations,
        "salt": salt.hex(),
        "digest": digest.hex(),
    }


def verify_password(password: str, record: Mapping[str, Any]) -> bool:
    try:
        iterations = int(record.get("iterations") or PASSWORD_ITERATIONS)
        salt = bytes.fromhex(str(record.get("salt") or ""))
        expected = bytes.fromhex(str(record.get("digest") or ""))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return bool(expected) and hmac.compare_digest(actual, expected)
    except Exception:
        return False


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    display_name: str
    role: str

    def as_public_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "role": self.role,
        }


class AuthManager:
    def __init__(self, security_root: Path):
        self.root = Path(security_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.users_path = self.root / "users.json"
        self.secret_path = self.root / "server_secret.bin"
        self.audit_path = self.root / "audit.jsonl"
        self.deleted_users_path = self.root / "deleted_users.json"
        self.sessions_path = self.root / "sessions.sqlite3"
        self._lock = threading.RLock()
        self._login_failures: dict[str, deque[float]] = defaultdict(deque)
        self._secret = self._load_or_create_secret()
        self._init_session_store()

    def _load_or_create_secret(self) -> bytes:
        try:
            if self.secret_path.is_file():
                data = self.secret_path.read_bytes()
                if len(data) >= 32:
                    return data
        except Exception:
            pass
        secret = secrets.token_bytes(48)
        self.secret_path.write_bytes(secret)
        try:
            os.chmod(self.secret_path, 0o600)
        except OSError:
            pass
        return secret


    def _session_connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.sessions_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _init_session_store(self) -> None:
        with self._session_connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    username TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    csrf TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_seen REAL NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)")
        try:
            os.chmod(self.sessions_path, 0o600)
        except OSError:
            pass

    def _session_hash(self, token: str) -> str:
        return hmac.new(self._secret, token.encode("utf-8"), hashlib.sha256).hexdigest()

    def _users(self) -> list[dict[str, Any]]:
        payload = read_json(self.users_path, [])
        return payload if isinstance(payload, list) else []

    def _save_users(self, users: list[dict[str, Any]]) -> None:
        write_json_atomic(self.users_path, users)
        try:
            os.chmod(self.users_path, 0o600)
        except OSError:
            pass

    def setup_required(self) -> bool:
        return not any(bool(item.get("active", True)) for item in self._users())

    def _public_user(self, record: Mapping[str, Any]) -> AuthenticatedUser:
        return AuthenticatedUser(
            id=str(record.get("id") or ""),
            username=str(record.get("username") or ""),
            display_name=str(record.get("display_name") or record.get("username") or "Usuário"),
            role=str(record.get("role") or "consulta"),
        )

    def setup_admin(self, username: Any, display_name: Any, password: Any) -> AuthenticatedUser:
        with self._lock:
            if not self.setup_required():
                raise PermissionError("A configuração inicial já foi concluída.")
            username_value = validate_username(username)
            password_value = validate_password(password)
            record = {
                "id": uuid.uuid4().hex,
                "username": username_value,
                "display_name": str(display_name or username_value).strip()[:100] or username_value,
                "role": "admin",
                "active": True,
                "password": hash_password(password_value),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "last_login_at": "",
                "must_change_password": False,
                "password_changed_at": now_iso(),
                "password_reset_at": "",
                "password_reset_by": "",
            }
            self._save_users([record])
            self.audit("auth.setup", user=self._public_user(record), outcome="success")
            return self._public_user(record)

    def create_user(
        self,
        username: Any,
        display_name: Any,
        role: Any,
        password: Any,
        *,
        actor: AuthenticatedUser,
        must_change_password: bool = False,
    ) -> AuthenticatedUser:
        if actor.role not in {"admin", "desenvolvedor"}:
            raise PermissionError("Somente administradores ou desenvolvedores podem cadastrar usuários.")
        username_value = validate_username(username)
        password_value = validate_password(password)
        role_value = str(role or "operador").strip().lower()
        if role_value not in ROLES:
            raise ValueError("Perfil de acesso inválido.")
        if role_value == "desenvolvedor" and actor.role != "desenvolvedor":
            raise PermissionError("Somente um desenvolvedor pode criar outro perfil Desenvolvedor.")
        with self._lock:
            users = self._users()
            if any(normalize_username(item.get("username")) == username_value for item in users):
                raise ValueError("Já existe um usuário com esse nome.")
            record = {
                "id": uuid.uuid4().hex,
                "username": username_value,
                "display_name": str(display_name or username_value).strip()[:100] or username_value,
                "role": role_value,
                "active": True,
                "password": hash_password(password_value),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "last_login_at": "",
                "must_change_password": bool(must_change_password),
                "password_changed_at": now_iso(),
                "password_reset_at": "",
                "password_reset_by": "",
            }
            users.append(record)
            self._save_users(users)
            created = self._public_user(record)
            self.audit(
                "user.create",
                user=actor,
                outcome="success",
                metadata={"target": created.as_public_dict(), "must_change_password": bool(must_change_password)},
            )
            return created

    def user_security_state(self, user_id: str) -> dict[str, Any]:
        record = next((item for item in self._users() if str(item.get("id")) == str(user_id)), None)
        if record is None:
            return {
                "must_change_password": False,
                "password_changed_at": "",
                "password_reset_at": "",
                "password_reset_by": "",
            }
        return {
            "must_change_password": bool(record.get("must_change_password", False)),
            "password_changed_at": str(record.get("password_changed_at") or ""),
            "password_reset_at": str(record.get("password_reset_at") or ""),
            "password_reset_by": str(record.get("password_reset_by") or ""),
        }

    def requires_password_change(self, user_id: str) -> bool:
        return bool(self.user_security_state(user_id).get("must_change_password", False))

    def reset_password(
        self,
        user_id: str,
        password: Any,
        *,
        actor: AuthenticatedUser,
        must_change_password: bool = True,
    ) -> AuthenticatedUser:
        if actor.role != "desenvolvedor":
            raise PermissionError("Somente o perfil Desenvolvedor pode redefinir senhas de terceiros.")
        if str(user_id) == str(actor.id):
            raise PermissionError("Para sua própria conta, use a opção Alterar minha senha.")
        password_value = validate_password(password)
        with self._lock:
            users = self._users()
            target: dict[str, Any] | None = None
            for record in users:
                if str(record.get("id")) == str(user_id):
                    target = record
                    break
            if target is None:
                raise KeyError("Usuário não encontrado.")
            if not bool(target.get("active", True)):
                raise ValueError("Ative a conta antes de redefinir a senha.")
            changed_at = now_iso()
            target["password"] = hash_password(password_value)
            target["must_change_password"] = bool(must_change_password)
            target["password_changed_at"] = changed_at
            target["password_reset_at"] = changed_at
            target["password_reset_by"] = actor.id
            target["updated_at"] = changed_at
            self._save_users(users)
            self.revoke_user_sessions(str(target.get("id")))
            public = self._public_user(target)
            self.audit(
                "user.password_reset",
                user=actor,
                outcome="success",
                metadata={
                    "target_user_id": public.id,
                    "must_change_password": bool(must_change_password),
                    "sessions_revoked": True,
                    "temporary": False,
                },
            )
            return public

    def create_temporary_password(
        self,
        user_id: str,
        *,
        actor: AuthenticatedUser,
        must_change_password: bool = True,
    ) -> dict[str, Any]:
        temporary_password = generate_temporary_password()
        public = self.reset_password(
            user_id,
            temporary_password,
            actor=actor,
            must_change_password=must_change_password,
        )
        self.audit(
            "user.temporary_password",
            user=actor,
            outcome="success",
            metadata={
                "target_user_id": public.id,
                "must_change_password": bool(must_change_password),
                "sessions_revoked": True,
            },
        )
        return {
            "user": public.as_public_dict(),
            "temporary_password": temporary_password,
            "must_change_password": bool(must_change_password),
            "sessions_revoked": True,
        }

    def change_own_password(
        self,
        user_id: str,
        current_password: Any,
        new_password: Any,
        *,
        actor: AuthenticatedUser,
    ) -> AuthenticatedUser:
        if str(user_id) != str(actor.id):
            raise PermissionError("A alteração da própria senha não pode atingir outra conta.")
        current_value = str(current_password or "")
        new_value = validate_password(new_password)
        with self._lock:
            users = self._users()
            target = next((item for item in users if str(item.get("id")) == str(user_id)), None)
            if target is None or not bool(target.get("active", True)):
                raise KeyError("Usuário não encontrado ou inativo.")
            if not verify_password(current_value, target.get("password") or {}):
                self.audit("user.password_change", user=actor, outcome="failure", metadata={"reason": "current_password_invalid"})
                raise ValueError("A senha atual está incorreta.")
            if verify_password(new_value, target.get("password") or {}):
                raise ValueError("A nova senha deve ser diferente da senha atual.")
            changed_at = now_iso()
            target["password"] = hash_password(new_value)
            target["must_change_password"] = False
            target["password_changed_at"] = changed_at
            target["updated_at"] = changed_at
            self._save_users(users)
            self.revoke_user_sessions(str(user_id))
            public = self._public_user(target)
            self.audit(
                "user.password_change",
                user=actor,
                outcome="success",
                metadata={"sessions_revoked": True, "forced_change_completed": True},
            )
            return public

    def revoke_sessions_managed(self, user_id: str, *, actor: AuthenticatedUser) -> dict[str, Any]:
        if actor.role != "desenvolvedor":
            raise PermissionError("Somente o perfil Desenvolvedor pode revogar sessões de terceiros.")
        target = next((item for item in self._users() if str(item.get("id")) == str(user_id)), None)
        if target is None:
            raise KeyError("Usuário não encontrado.")
        self.revoke_user_sessions(str(user_id))
        public = self._public_user(target)
        self.audit("user.sessions_revoke", user=actor, outcome="success", metadata={"target_user_id": public.id})
        return {"revoked": True, "user": public.as_public_dict()}

    def update_user(
        self,
        user_id: str,
        *,
        username: Any | None = None,
        display_name: Any,
        role: Any,
        active: Any,
        actor: AuthenticatedUser,
    ) -> AuthenticatedUser:
        if actor.role != "desenvolvedor":
            raise PermissionError("Somente o perfil Desenvolvedor pode editar usuários e perfis.")
        role_value = str(role or "consulta").strip().lower()
        if role_value not in ROLES:
            raise ValueError("Perfil de acesso inválido.")
        username_value = validate_username(username) if username is not None else ""
        active_value = bool(active)
        with self._lock:
            users = self._users()
            target: dict[str, Any] | None = None
            for record in users:
                if str(record.get("id")) == str(user_id):
                    target = record
                    break
            if target is None:
                raise KeyError("Usuário não encontrado.")
            old_username = normalize_username(target.get("username"))
            new_username = username_value or old_username
            if any(
                str(item.get("id")) != str(user_id)
                and normalize_username(item.get("username")) == new_username
                for item in users
            ):
                raise ValueError("Já existe outro usuário com esse nome de acesso.")
            if str(target.get("id")) == actor.id and (role_value != "desenvolvedor" or not active_value):
                raise PermissionError("O Desenvolvedor conectado não pode remover o próprio acesso.")
            old_role = str(target.get("role") or "consulta").strip().lower()
            old_active = bool(target.get("active", True))
            if old_role == "desenvolvedor" and old_active and (role_value != "desenvolvedor" or not active_value):
                remaining = [
                    item for item in users
                    if str(item.get("id")) != str(user_id)
                    and bool(item.get("active", True))
                    and str(item.get("role") or "").strip().lower() == "desenvolvedor"
                ]
                if not remaining:
                    raise PermissionError("Não é possível remover o último Desenvolvedor ativo.")
            target["username"] = new_username
            target["display_name"] = str(display_name or new_username or "Usuário").strip()[:100] or new_username
            target["role"] = role_value
            target["active"] = active_value
            target["updated_at"] = now_iso()
            self._save_users(users)
            if old_username != new_username or old_role != role_value or old_active != active_value:
                self.revoke_user_sessions(str(target.get("id")))
            public = self._public_user(target)
            self.audit(
                "user.update",
                user=actor,
                outcome="success",
                metadata={
                    "target_user_id": public.id,
                    "old_username": old_username,
                    "new_username": new_username,
                    "old_role": old_role,
                    "new_role": role_value,
                    "old_active": old_active,
                    "new_active": active_value,
                },
            )
            return public

    def delete_user(self, user_id: str, *, actor: AuthenticatedUser) -> dict[str, Any]:
        if actor.role != "desenvolvedor":
            raise PermissionError("Somente o perfil Desenvolvedor pode excluir usuários.")
        if str(user_id) == actor.id:
            raise PermissionError("O Desenvolvedor conectado não pode excluir a própria conta.")
        with self._lock:
            users = self._users()
            target = next((record for record in users if str(record.get("id")) == str(user_id)), None)
            if target is None:
                raise KeyError("Usuário não encontrado.")
            if bool(target.get("active", True)) and str(target.get("role") or "").strip().lower() == "desenvolvedor":
                remaining = [
                    item for item in users
                    if str(item.get("id")) != str(user_id)
                    and bool(item.get("active", True))
                    and str(item.get("role") or "").strip().lower() == "desenvolvedor"
                ]
                if not remaining:
                    raise PermissionError("Não é possível excluir o último Desenvolvedor ativo.")
            archive = read_json(self.deleted_users_path, [])
            if not isinstance(archive, list):
                archive = []
            archived = dict(target)
            archived["deleted_at"] = now_iso()
            archived["deleted_by"] = actor.as_public_dict()
            archive.insert(0, archived)
            write_json_atomic(self.deleted_users_path, archive[:1000])
            users = [record for record in users if str(record.get("id")) != str(user_id)]
            self._save_users(users)
            self.revoke_user_sessions(str(user_id))
            public = self._public_user(target).as_public_dict()
            self.audit("user.delete", user=actor, outcome="success", metadata={"target": public, "workspace_preserved": True})
            return {"deleted": True, "user": public, "workspace_preserved": True}

    def list_users(self, *, actor: AuthenticatedUser) -> list[dict[str, Any]]:
        if actor.role != "desenvolvedor":
            raise PermissionError("Somente o perfil Desenvolvedor pode listar e administrar usuários.")
        session_counts: dict[str, int] = {}
        with self._session_connection() as connection:
            self._cleanup_sessions_locked(time.time(), connection=connection)
            rows = connection.execute("SELECT user_id, COUNT(*) AS total FROM sessions GROUP BY user_id").fetchall()
            session_counts = {str(row["user_id"]): int(row["total"] or 0) for row in rows}
        result: list[dict[str, Any]] = []
        for record in self._users():
            public = self._public_user(record).as_public_dict()
            public.update({
                "active": bool(record.get("active", True)),
                "created_at": str(record.get("created_at") or ""),
                "updated_at": str(record.get("updated_at") or ""),
                "last_login_at": str(record.get("last_login_at") or ""),
                "must_change_password": bool(record.get("must_change_password", False)),
                "password_changed_at": str(record.get("password_changed_at") or ""),
                "password_reset_at": str(record.get("password_reset_at") or ""),
                "password_reset_by": str(record.get("password_reset_by") or ""),
                "active_sessions": int(session_counts.get(str(record.get("id")), 0)),
            })
            result.append(public)
        return sorted(result, key=lambda item: item["username"])

    def developer_exists(self) -> bool:
        return any(
            bool(record.get("active", True)) and str(record.get("role") or "").strip().lower() == "desenvolvedor"
            for record in self._users()
        )

    def create_first_developer_local(self, username: Any, display_name: Any, password: Any) -> AuthenticatedUser:
        """Cria o primeiro Desenvolvedor somente por execução local no computador.

        Esta operação não é publicada na API HTTP. Depois que o primeiro perfil
        existe, ele pode criar outros desenvolvedores pela tela protegida.
        """
        username_value = validate_username(username)
        password_value = validate_password(password)
        with self._lock:
            users = self._users()
            if any(bool(item.get("active", True)) and str(item.get("role") or "").lower() == "desenvolvedor" for item in users):
                raise PermissionError("O primeiro perfil Desenvolvedor já foi criado.")
            if any(normalize_username(item.get("username")) == username_value for item in users):
                raise ValueError("Já existe um usuário com esse nome.")
            record = {
                "id": uuid.uuid4().hex,
                "username": username_value,
                "display_name": str(display_name or username_value).strip()[:100] or username_value,
                "role": "desenvolvedor",
                "active": True,
                "password": hash_password(password_value),
                "created_at": now_iso(),
                "updated_at": now_iso(),
                "last_login_at": "",
                "must_change_password": False,
                "password_changed_at": now_iso(),
                "password_reset_at": "",
                "password_reset_by": "",
                "created_offline": True,
            }
            users.append(record)
            self._save_users(users)
            created = self._public_user(record)
            self.audit("developer.first.create_local", user=created, outcome="success")
            return created

    def _find_user(self, username: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        users = self._users()
        for record in users:
            if normalize_username(record.get("username")) == normalize_username(username):
                return users, record
        return users, None

    def can_attempt_login(self, remote_key: str) -> tuple[bool, int]:
        now = time.time()
        queue = self._login_failures[remote_key]
        while queue and now - queue[0] > LOGIN_WINDOW_SECONDS:
            queue.popleft()
        if len(queue) >= LOGIN_MAX_FAILURES:
            retry_after = max(1, int(LOGIN_WINDOW_SECONDS - (now - queue[0])))
            return False, retry_after
        return True, 0

    def authenticate(self, username: Any, password: Any, *, remote_key: str) -> AuthenticatedUser | None:
        allowed, _ = self.can_attempt_login(remote_key)
        if not allowed:
            return None
        with self._lock:
            users, record = self._find_user(str(username or ""))
            if record is None or not bool(record.get("active", True)) or not verify_password(str(password or ""), record.get("password") or {}):
                self._login_failures[remote_key].append(time.time())
                self.audit("auth.login", outcome="failure", remote=remote_key, metadata={"username": normalize_username(username)})
                return None
            self._login_failures.pop(remote_key, None)
            record["last_login_at"] = now_iso()
            record["updated_at"] = now_iso()
            self._save_users(users)
            user = self._public_user(record)
            self.audit("auth.login", user=user, outcome="success", remote=remote_key)
            return user

    def create_session(self, user: AuthenticatedUser) -> tuple[str, dict[str, Any]]:
        token = secrets.token_urlsafe(48)
        now = time.time()
        session = {
            "user": user,
            "csrf": secrets.token_urlsafe(32),
            "created_at": now,
            "expires_at": now + SESSION_TTL_SECONDS,
            "last_seen": now,
        }
        token_hash = self._session_hash(token)
        with self._lock, self._session_connection() as connection:
            self._cleanup_sessions_locked(now, connection=connection)
            connection.execute(
                """
                INSERT INTO sessions(
                    token_hash, user_id, username, display_name, role, csrf,
                    created_at, expires_at, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    token_hash, user.id, user.username, user.display_name, user.role,
                    session["csrf"], session["created_at"], session["expires_at"], session["last_seen"],
                ),
            )
        return token, session

    def get_session(self, token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        now = time.time()
        token_hash = self._session_hash(token)
        with self._lock, self._session_connection() as connection:
            self._cleanup_sessions_locked(now, connection=connection)
            row = connection.execute(
                "SELECT * FROM sessions WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row is None:
                return None
            connection.execute(
                "UPDATE sessions SET last_seen = ? WHERE token_hash = ?",
                (now, token_hash),
            )
        user = AuthenticatedUser(
            id=str(row["user_id"]),
            username=str(row["username"]),
            display_name=str(row["display_name"]),
            role=str(row["role"]),
        )
        return {
            "user": user,
            "csrf": str(row["csrf"]),
            "created_at": float(row["created_at"]),
            "expires_at": float(row["expires_at"]),
            "last_seen": now,
        }

    def destroy_session(self, token: str | None, *, remote: str = "") -> None:
        if not token:
            return
        token_hash = self._session_hash(token)
        row = None
        with self._lock, self._session_connection() as connection:
            row = connection.execute(
                "SELECT user_id, username, display_name, role FROM sessions WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
            connection.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
        user = None
        if row is not None:
            user = AuthenticatedUser(
                id=str(row["user_id"]),
                username=str(row["username"]),
                display_name=str(row["display_name"]),
                role=str(row["role"]),
            )
        self.audit("auth.logout", user=user, outcome="success", remote=remote)

    def revoke_user_sessions(self, user_id: str) -> None:
        with self._lock, self._session_connection() as connection:
            connection.execute("DELETE FROM sessions WHERE user_id = ?", (str(user_id),))

    def _cleanup_sessions_locked(
        self,
        now: float,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        owns_connection = connection is None
        active_connection = connection or self._session_connection()
        try:
            active_connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (float(now),))
            if owns_connection:
                active_connection.commit()
        finally:
            if owns_connection:
                active_connection.close()

    def verify_csrf(self, session: Mapping[str, Any], supplied: Any) -> bool:
        expected = str(session.get("csrf") or "")
        return bool(expected) and hmac.compare_digest(expected, str(supplied or ""))

    def audit(
        self,
        action: str,
        *,
        user: AuthenticatedUser | None = None,
        outcome: str = "success",
        remote: str = "",
        request_id: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        entry = {
            "timestamp": now_iso(),
            "action": str(action),
            "outcome": str(outcome),
            "request_id": str(request_id),
            "remote": str(remote),
            "user": user.as_public_dict() if isinstance(user, AuthenticatedUser) else None,
            "metadata": dict(metadata or {}),
        }
        line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as stream:
                stream.write(line)

    def recent_audit(self, *, actor: AuthenticatedUser, limit: int = 200) -> list[dict[str, Any]]:
        if actor.role not in {"admin", "desenvolvedor"}:
            raise PermissionError("Somente administradores ou desenvolvedores podem consultar o log de auditoria.")
        try:
            lines = self.audit_path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 1000)):]
        except Exception:
            return []
        result: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    result.append(item)
            except Exception:
                continue
        return result
