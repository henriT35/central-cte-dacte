#!/bin/sh
set -eu

DATA_ROOT="${CENTRAL_CTE_DATA_ROOT:-/data}"
PARTNER_SEED_ROOT="${CENTRAL_CTE_PARTNER_SEED_ROOT:-/app/seed/partner_tables}"
PARTNER_TARGET_ROOT="$DATA_ROOT/partner_tables"
CACHE_ROOT="${CENTRAL_CTE_CACHE_ROOT:-/app/cache}"

seed_partner_tables() {
  [ -f "$PARTNER_SEED_ROOT/release_seed_version.txt" ] || return 0
  [ -f "$PARTNER_SEED_ROOT/cadastro_tabelas_parceiros_compilada.xlsx" ] || {
    echo "ERRO: semente compilada de parceiros ausente em $PARTNER_SEED_ROOT" >&2
    return 1
  }

  incoming_version="$(cat "$PARTNER_SEED_ROOT/release_seed_version.txt")"
  current_version=""
  if [ -f "$PARTNER_TARGET_ROOT/.release_seed_version" ]; then
    current_version="$(cat "$PARTNER_TARGET_ROOT/.release_seed_version")"
  fi
  [ "$incoming_version" = "$current_version" ] && return 0

  timestamp="$(date +%Y%m%d_%H%M%S)"
  backup_root="$PARTNER_TARGET_ROOT/history/release_seed_${timestamp}"
  mkdir -p "$PARTNER_TARGET_ROOT/files" "$PARTNER_TARGET_ROOT/history" "$backup_root/files"

  for name in cadastro_tabelas_parceiros_compilada.xlsx compiled_signature.txt .release_seed_version; do
    if [ -f "$PARTNER_TARGET_ROOT/$name" ]; then
      cp -p "$PARTNER_TARGET_ROOT/$name" "$backup_root/$name"
    fi
  done
  if [ -d "$PARTNER_TARGET_ROOT/files" ]; then
    for source in "$PARTNER_TARGET_ROOT/files/"*.xlsx; do
      [ -f "$source" ] || continue
      cp -p "$source" "$backup_root/files/$(basename "$source")"
    done
  fi

  temporary="$PARTNER_TARGET_ROOT/.seed_${timestamp}"
  rm -rf "$temporary"
  mkdir -p "$temporary/files"
  cp -p "$PARTNER_SEED_ROOT/cadastro_tabelas_parceiros_compilada.xlsx" "$temporary/"
  cp -p "$PARTNER_SEED_ROOT/compiled_signature.txt" "$temporary/"
  for source in "$PARTNER_SEED_ROOT/files/"*.xlsx; do
    [ -f "$source" ] || continue
    cp -p "$source" "$temporary/files/$(basename "$source")"
  done

  cp -p "$temporary/cadastro_tabelas_parceiros_compilada.xlsx" "$PARTNER_TARGET_ROOT/"
  cp -p "$temporary/compiled_signature.txt" "$PARTNER_TARGET_ROOT/"
  for source in "$temporary/files/"*.xlsx; do
    [ -f "$source" ] || continue
    cp -p "$source" "$PARTNER_TARGET_ROOT/files/$(basename "$source")"
  done
  printf '%s\n' "$incoming_version" > "$PARTNER_TARGET_ROOT/.release_seed_version"
  rm -rf "$temporary"

  echo "Tabelas oficiais sincronizadas no volume persistente: $incoming_version"
}

# Somente o contêiner principal prepara a estrutura persistente. Os serviços
# de backup e monitor usam a mesma imagem em modo read-only e não devem tentar
# criar diretórios na raiz interna da imagem.
case " $* " in
  *" web_local/server.py "*)
    mkdir -p \
      "$DATA_ROOT/security" \
      "$DATA_ROOT/workspaces" \
      "$DATA_ROOT/backups" \
      "$DATA_ROOT/runtime/logs" \
      "$DATA_ROOT/runtime/sessoes" \
      "$DATA_ROOT/runtime/relatorios" \
      "$DATA_ROOT/runtime/faturas" \
      "$DATA_ROOT/runtime/xmls" \
      "$DATA_ROOT/runtime/saida_html" \
      "$DATA_ROOT/runtime/modelos" \
      "$DATA_ROOT/runtime/config" \
      "$DATA_ROOT/runtime/legacy_core/sessoes" \
      "$DATA_ROOT/runtime/legacy_core/logs" \
      "$DATA_ROOT/runtime/legacy/sessoes" \
      "$DATA_ROOT/runtime/legacy/logs" \
      "$DATA_ROOT/runtime/legacy/xmls" \
      "$DATA_ROOT/runtime/legacy/relatorios" \
      "$PARTNER_TARGET_ROOT/files" \
      "$PARTNER_TARGET_ROOT/history" \
      "$CACHE_ROOT/legacy_core" \
      "$CACHE_ROOT/legacy"
    seed_partner_tables
    ;;
esac

exec "$@"
