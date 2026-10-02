# 28 — Diagnóstico
## Sistema não inicia
Python/Docker → porta 8765/processo antigo → escrita em data/cache → dependências → `/api/health` → logs.

## Login
Verificar setup, rate limit, storage de segurança, cookie/HTTPS/proxy.

## 403
Conferir papel/capability e CSRF; Consulta é read-only exceto QA.

## XML inesperado
Identificar CT-e/chave → Base SSW ativa → parceiro/XLSX → trace/fotografia → reproduzir em teste sentinela; não corrigir fórmula na UI.

## Parceiro sem cadastro
Conferir XLSX individual e sincronização do compilado.

## PDF/assinatura
Conferir readiness, WeasyPrint/Pillow/poppler, perfil e decisão persistida.

## PostgreSQL
Verificar enabled/host/porta/db/user/senha/SSL/firewall e manter read-only.

## Backup/restore
Validar SHA, ZIP, espaço, formato e permissões; preferir ensaio em ambiente descartável.
