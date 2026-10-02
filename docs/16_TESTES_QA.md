# 16 — Testes, QA e Homologação
`pytest --collect-only` encontrou **207 testes** em 33 arquivos.

| Verificação | Resultado |
|---|---|
| Compilação Python própria | 222/222 OK |
| Bateria crítica recente | 65 passed / 2 failed |
| Suíte completa | não concluída em 150s |
| Deploy VPS externo | não executado nesta auditoria |

## Duas falhas confirmadas
1. `test_r12_13_9_manual_signed_pdf.py::test_local_launcher_restarts_stale_version` espera string R12.13.9.
2. `test_r12_13_6_partner_catalog_autosync.py::test_server_syncs_catalog_for_all_users_and_before_xml_processing` espera APP_VERSION R12.13.9.

São expectativas de versão antigas, não evidência direta de regressão comercial.

Não marcar homologação completa sem execução total e testes externos quando aplicável.
