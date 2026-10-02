# 23 — Segurança
## Controles presentes
PBKDF2-SHA256/310k + salt; sessão token/HMAC; CSRF; HttpOnly/SameSite/ Secure em HTTPS; rate limit; allowlist Host; CSP/X-Frame-Options/nosniff/referrer; limites de upload; raízes permitidas de download; restore anti-path-traversal; container non-root/read-only/no-new-privileges/cap_drop; PostgreSQL read-only.

## Segredos
Nunca versionar `.env`, chaves/certs, `server_secret.bin`, sessões, credenciais PostgreSQL/S3 ou tokens.

## Achado de empacotamento
ZIP auditado contém runtime de segurança local; Git público verificado não contém esse diretório. Gerar release de checkout limpo/git archive.

## Repo público
Tabelas comerciais estão versionadas. Confirmar que podem ser públicas.

## IP/HTTP
Não manter exposição internet com dados sensíveis sem TLS.
