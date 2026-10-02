# Informações Adicionais
## Integridade do pacote
`SHA256SUMS.txt` tem 610 entradas; 8 divergiram no ZIP auditado: `00_INICIAR_LOCAL_ONLINE.bat`, `.ps1`, `00_PARAR_LOCAL_ONLINE.bat`, `.ps1`, `CRIAR_PRIMEIRO_DESENVOLVEDOR.bat`, `web_local/tools/SSW_POSTGRES_BRIDGE.ps1` e dois `RECORD` de vendor.

## Estado local empacotado
ZIP contém `web_local/data/security/server_secret.bin`, `sessions.sqlite3` e QA local fora do manifesto Git. `.gitignore` os exclui e o diretório de segurança não foi encontrado no `main` público.

## Fonte de tabelas
Além do compilado e dos 17 XLSX individuais, `tabelas/cadastro_tabelas_parceiros.xlsx` guarda instruções, regras, regiões, diagnósticos, pendências e histórico. Entradas `PENDENTE_*`/`CONFERIR_*` não equivalem automaticamente a regra homologada.
