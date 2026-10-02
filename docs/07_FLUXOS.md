# 07 — Fluxos
## Autenticação
```mermaid
flowchart TD
 A[Abrir] --> B{/api/auth/status}
 B -->|sem usuário| C[/api/auth/setup]
 C --> D[Cria Desenvolvedor + sessão]
 B -->|já configurado| E[/api/auth/login]
 D --> F[/api/bootstrap]
 E --> F
```

## XML
Upload → deduplicação → Base SSW + tabela de parceiro → RC26.6 → fotografia da decisão → autorização manual quando necessária → state/output.

## Fatura
Upload PDF → parser → duplicata/rejeição → reconciliação → persistência → relatório XLSX.

## DACTE/Assinatura
Seleção CT-es → carregar estado persistido → renderer oficial → PDF; assinatura é visual, não ICP-Brasil.

## Base SSW
Stage de `.sswweb` → validação → commit atômico → backup do conjunto anterior → base ativa.

## PostgreSQL
Read-only/ponte LAN → snapshot sombra → comparação com Base SSW → diagnóstico; **sem promoção automática**.
