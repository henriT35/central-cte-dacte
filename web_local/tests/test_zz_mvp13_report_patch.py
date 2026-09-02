# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
from zipfile import ZipFile

WEB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEB_ROOT.parent
ENGINE_ROOT = PROJECT_ROOT / "engine"
if str(WEB_ROOT) not in sys.path:
    sys.path.insert(0, str(WEB_ROOT))
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from services.xml_report_web_patch import (  # noqa: E402
    correct_report_model,
    patch_report_xlsx,
    prepare_report_files,
)


def _report_runtime():
    from central_cte_modular.reports import xml_validation_report as report_module
    from central_cte_modular.reports.xlsx_openxml import formula_value
    return report_module, formula_value


def _info() -> dict[str, object]:
    return {
        "tipo": "CT-e",
        "numero": "3564265",
        "serie": "5",
        "valor": "517,98",
        "emitente": "W S TRANSPORTES DE CARGAS E LOGISTICA LTDA",
        "emit": {"cnpjcpf": "15186966000132"},
        "dest": {"mun": "JI-PARANÁ - RO"},
        "origem": "COLOMBO / PR",
        "destino": "JI-PARANÁ / RO",
        "docs": [{"n_doc": "38322"}],
        "validacao": {
            "status": "DIVERGENTE EXTRA +",
            "nf": "38322",
            "base_frete": 0.01,
            "valor_total_xml": None,
            "valor_comparado": None,
            "componente_comparado": "",
            "esperado": 200.00,
            "diferenca": None,
            "tolerancia": 1.00,
            "partner_id": "W_S",
            "regra_extra": "REENTREGA",
            "trace": [],
        },
    }


def test_model_web_corrige_extra_e_sentinela_sem_alterar_motor() -> None:
    report_module, formula_value = _report_runtime()
    files = prepare_report_files([_info()])
    generator = report_module.XmlValidationReportGenerator()
    model = generator.build(files)
    correct_report_model(report_module, model)

    detail = model.detail_rows[0]
    audit = model.audit_rows[0]
    headers = list(report_module.DETAIL_HEADERS)
    audit_headers = list(report_module.AUDIT_HEADERS)

    assert formula_value(detail[headers.index("Valor Comparado")]) == 517.98
    assert formula_value(detail[headers.index("Diferença")]) == 317.98
    assert formula_value(detail[headers.index("Frete Base / Receita")]) in (None, "")
    assert formula_value(detail[headers.index("Lucro Bruto Estimado")]) in (None, "")
    assert formula_value(detail[headers.index("Margem Bruta Estimada")]) in (None, "")
    assert formula_value(detail[headers.index("Classificação da Margem")]) == "SEM FRETE BASE"
    assert "VALOR SENTINELA R$ 0,01" in str(
        audit[audit_headers.index("Fonte do Frete Base / Receita")]
    )
    assert model.metrics["total_base"] == 0.0
    assert model.metrics["total_profit"] == 0.0


def test_xlsx_web_explicita_volume_divergencia_e_limite_sentinela() -> None:
    report_module, _formula_value = _report_runtime()
    files = prepare_report_files([_info()])
    generator = report_module.XmlValidationReportGenerator()
    model = generator.build(files)
    correct_report_model(report_module, model)

    with TemporaryDirectory() as temporary:
        output = Path(temporary) / "relatorio.xlsx"
        generator.writer.write(output, model)
        patch_report_xlsx(output, report_module, model)
        with ZipFile(output) as archive:
            assert archive.testzip() is None
            panel = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            detail = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
            ElementTree.fromstring(panel)
            ElementTree.fromstring(detail)

    assert "Volume financeiro sob atenção" in panel
    assert "Divergência financeira apurada" in panel
    assert "não representa prejuízo" in panel
    assert "Frete base sentinela até" in panel
    assert "<v>317.98</v>" in panel
    assert "$T$81" in detail
    assert "SEM FRETE BASE" in detail
