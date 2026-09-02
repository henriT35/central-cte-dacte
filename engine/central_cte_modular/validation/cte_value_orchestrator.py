from __future__ import annotations

"""Orquestração modular da validação comercial de CT-e.

Este módulo contém o fluxo que antes vivia em ``validate_cte_value`` no
monólito. Ele recebe as dependências explicitamente e não importa o motor
legado. O adaptador de bootstrap decide entre modular, sombra e rollback.
"""

from dataclasses import dataclass
from typing import Any, Callable

ORCHESTRATOR_VERSION = "2.7.0-rc17"


@dataclass(frozen=True)
class ValidationDependencies:
    base_rows_have_same_route: Callable[..., Any]
    calculate_extra_expected: Callable[..., Any]
    candidate_summary: Callable[..., Any]
    choose_extra_rule: Callable[..., Any]
    choose_partner_rule: Callable[..., Any]
    choose_weight_special_rule: Callable[..., Any]
    comparison_value_from_xml: Callable[..., Any]
    component_value: Callable[..., Any]
    detect_partner_charge_type: Callable[..., Any]
    detect_partner_manual_extra: Callable[..., Any]
    diagnostico_nf_fora_base_periodo: Callable[..., Any]
    find_base_by_nf: Callable[..., Any]
    fmt_percent: Callable[..., Any]
    format_component_list: Callable[..., Any]
    format_peso_xml_debug: Callable[..., Any]
    get_nfs_from_info: Callable[..., Any]
    identify_partner: Callable[..., Any]
    money: Callable[..., Any]
    non_frete_peso_components_value: Callable[..., Any]
    normalize_base_calculo: Callable[..., Any]
    parse_number_br: Callable[..., Any]
    peso_base_kg_from_info: Callable[..., Any]
    rule_pedagio_expected: Callable[..., Any]
    should_use_frete_peso: Callable[..., Any]
    status_nf_fora_base_periodo: Callable[..., Any]
    sum_base_for_rule: Callable[..., Any]
    summarize_base_statuses: Callable[..., Any]
    validate_rodotec_components_fallback: Callable[..., Any]
    xml_validation_partner_policy: Callable[..., Any]


class ModularCteValueOrchestrator:
    """Executa a decisão de valor do CT-e sem chamar o orquestrador legado."""

    REQUIRED_RESULT_FIELDS = frozenset({"nf", "status", "trace", "partner_id"})

    def __init__(self, dependencies: ValidationDependencies) -> None:
        self.d = dependencies

    @classmethod
    def validate_contract(cls, result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise TypeError(f"Resultado modular inválido: esperado dict, recebido {type(result).__name__}")
        missing = sorted(cls.REQUIRED_RESULT_FIELDS.difference(result))
        if missing:
            raise ValueError(f"Resultado modular sem campos obrigatórios: {', '.join(missing)}")
        if not isinstance(result.get("trace"), list):
            raise TypeError("Resultado modular inválido: trace deve ser uma lista")
        if not str(result.get("status") or "").strip():
            raise ValueError("Resultado modular inválido: status vazio")
        return result

    def validate(self, info, base_data, tables):
        nfs = self.d.get_nfs_from_info(info)
        nf = nfs[0] if nfs else ''
        result = {'nf': ', '.join(nfs) if nfs else nf, 'base_frete': None, 'percentual': None, 'frete_minimo': None, 'esperado': None, 'diferenca': None, 'tolerancia': None, 'status': 'PENDENTE', 'detalhe': '', 'partner_id': '', 'tipo_cobranca': '', 'regra_extra': '', 'base_calculo': '', 'modo_calculo': '', 'peso_base_kg': None, 'peso_xml_fonte': '', 'peso_xml_todos': '', 'regra_peso_especial': '', 'limite_peso_especial_kg': None, 'percentual_original_regra': None, 'peso_reverso_kg': None, 'dif_peso_kg': None, 'auditoria_peso_status': '', 'auditoria_peso_obs': '', 'tonelagem_taxa': None, 'frete_peso_xml': None, 'frete_peso_calculado': None, 'taxa_kg': None, 'adicionais_xml': None, 'valor_total_xml': None, 'valor_comparado': None, 'componente_comparado': '', 'comparacao_fallback_total': False, 'nfs_nao_encontradas': [], 'nfs_incompativeis': [], 'nfs_ignoradas': [], 'validacao_com_nf_valida': False, 'validacao_parcial': False, 'trace': [], 'base_candidates_summary': []}
        trace = result['trace']
        trace.append('Iniciando validação do XML.')
        if info.get('tipo') != 'CT-e':
            result['status'] = 'NÃO É CT-e'
            trace.append(f"Tipo identificado: {info.get('tipo', '-')}. Este item não será validado como CT-e.")
            return result
        trace.append(f"CT-e parceiro lido: número {info.get('numero', '-')}, série {info.get('serie', '-')}, valor R$ {self.d.money(info.get('valor', ''))}.")
        charge_type = self.d.detect_partner_charge_type(info)
        original_charge_type = charge_type
        if charge_type == 'SUBSTITUICAO':
            trace.append('Tipo SUBSTITUIÇÃO identificado. Configuração atual: usar regra normal da cidade/tabela para conferir o valor, sem bloquear como EXTRA REVISAR.')
            charge_type = 'NORMAL'
        result['tipo_cobranca'] = original_charge_type
        trace.append(f'Tipo de cobrança identificado pelo XML: {original_charge_type}.')
        if not nfs:
            result['status'] = 'NF NÃO LIDA'
            trace.append('Nenhuma NF foi encontrada nos documentos originários do XML.')
            return result
        if len(nfs) == 1:
            trace.append(f'NF originária identificada no XML: {nf}.')
        else:
            trace.append(f"Múltiplas NFs originárias identificadas no XML: {', '.join(nfs)}.")
            trace.append('O programa irá somar os fretes base das NFs quando todas apontarem para a mesma rota. Se as rotas forem diferentes, exigirá revisão manual.')
        if not base_data:
            result['status'] = 'BASE NÃO CARREGADA'
            trace.append('A base Rodovitor ainda não foi carregada.')
            return result
        early_pid = self.d.identify_partner(info, tables) if tables else None
        policy = self.d.xml_validation_partner_policy(early_pid)
        actual_xml_value = self.d.parse_number_br(info.get('valor', ''))
        base_rows = []
        statuses = []
        all_candidates = []
        missing_nfs = []
        blocked_nfs = []
        incompatible_nfs = []
        for one_nf in nfs:
            base_row, base_status, candidates = self.d.find_base_by_nf(base_data, one_nf, info, preferred_type='COMPLEMENTAR' if original_charge_type == 'COMPLEMENTAR' and policy.get('aceitar_complementar_exato_base') else '', actual_value=actual_xml_value, tolerance=tables.get('tolerance', 1.0) if tables else 1.0, allow_substitute=bool(policy.get('aceitar_substituto_com_vinculo_forte')), require_compatibility=len(nfs) > 1)
            statuses.append(base_status)
            all_candidates.extend(candidates)
            trace.append(f'Busca na base Rodovitor para NF {one_nf}: {len(candidates)} ocorrência(s) encontrada(s).')
            if candidates:
                normal_count = sum((1 for c in candidates if c.get('tipo_base') == 'NORMAL'))
                comp_count = sum((1 for c in candidates if c.get('tipo_base') == 'COMPLEMENTAR'))
                other_count = max(len(candidates) - normal_count - comp_count, 0)
                trace.append(f'NF {one_nf}: {normal_count} normal(is), {comp_count} complementar(es), {other_count} outra(s).')
            if not base_row:
                if base_status == 'NF NÃO ENCONTRADA':
                    missing_nfs.append(one_nf)
                    trace.append(f'Nenhuma linha da base carregada/período atual possui a NF {one_nf}. Esta NF será tratada como fora da base/período, ou como NF acessória se houver outra NF válida no mesmo XML.')
                    continue
                if base_status == 'NF INCOMPATÍVEL':
                    incompatible_nfs.append(one_nf)
                    blocked_nfs.append((one_nf, base_status, len(candidates)))
                    trace.append(f'A NF {one_nf} existe na base, mas o CNPJ/destinatário/rota não são compatíveis com este XML. A ocorrência foi descartada para evitar falsa múltipla rota ou falso OK.')
                    continue
                blocked_nfs.append((one_nf, base_status, len(candidates)))
                if base_status == 'ORIGINAL NÃO ENCONTRADO':
                    trace.append(f'A NF {one_nf} existe na base, mas não foi encontrado CT-e NORMAL/ORIGINAL para usar como base de cálculo.')
                else:
                    trace.append(f'A NF {one_nf} não pôde ser usada na base. Status: {base_status}.')
                continue
            trace.append(f'Linha base escolhida para NF {one_nf}: {self.d.candidate_summary(base_row)}.')
            base_rows.append(base_row)
        result['base_candidates_summary'] = [self.d.candidate_summary(c) for c in all_candidates[:30]]
        result['nfs_nao_encontradas'] = missing_nfs
        result['nfs_incompativeis'] = incompatible_nfs
        ignored_nfs = list(dict.fromkeys(list(missing_nfs) + list(incompatible_nfs) + [one_nf for one_nf, _status, _qtd in blocked_nfs if one_nf not in incompatible_nfs]))
        result['nfs_ignoradas'] = ignored_nfs
        result['validacao_com_nf_valida'] = bool(base_rows and ignored_nfs)
        result['validacao_parcial'] = False if base_rows else bool(ignored_nfs)
        if blocked_nfs and (not base_rows):
            one_nf, base_status, qtd = blocked_nfs[0]
            result['status'] = base_status
            result['detalhe'] = f'NF {one_nf}: {qtd} ocorrência(s)' if qtd else f'NF {one_nf} não pôde ser usada na base Rodovitor'
            return result
        if not base_rows:
            result['status'] = self.d.status_nf_fora_base_periodo()
            result['detalhe'] = 'Nenhuma NF do XML foi localizada na base carregada/período atual'
            trace.append(self.d.diagnostico_nf_fora_base_periodo(nfs))
            trace.append('O cálculo automático foi bloqueado porque não há linha de base para cruzar com o XML.')
            return result
        if missing_nfs:
            trace.append(f"NF(s) acessória(s) não localizada(s) e ignorada(s): {', '.join(missing_nfs)}.")
            trace.append('Como existe ao menos uma NF válida com vínculo confiável, isso não transforma o CT-e em validação parcial nem exige revisão por si só.')
        if blocked_nfs:
            ignored_detail = ', '.join((f'{one_nf} ({base_status})' for one_nf, base_status, _qtd in blocked_nfs))
            trace.append(f'NF(s) descartada(s) por falta de vínculo utilizável: {ignored_detail}.')
            trace.append('O cálculo seguirá somente com as NFs válidas. As descartadas serão registradas no log como NFs ignoradas.')
        usable_statuses = [s for s in statuses if s not in ('NF NÃO ENCONTRADA', 'NF INCOMPATÍVEL')]
        base_status = self.d.summarize_base_statuses(usable_statuses or statuses)
        if len(base_rows) > 1 and (not self.d.base_rows_have_same_route(base_rows)):
            result['status'] = 'MÚLTIPLAS ROTAS'
            result['base_frete'] = sum((r.get('valor_frete_planilha', 0.0) or r.get('valor_frete', 0.0) for r in base_rows))
            result['detalhe'] = 'NFs do XML apontam para rotas diferentes na base'
            trace.append('As NFs do mesmo XML foram localizadas, mas apontam para origem/destino diferentes na base. O cálculo automático foi bloqueado para evitar comparação errada.')
            return result
        result['base_frete'] = sum((r.get('valor_frete_planilha', 0.0) or r.get('valor_frete', 0.0) for r in base_rows))
        base_row = base_rows[0]
        if result.get('validacao_parcial'):
            trace.append(f'Frete base será calculado com {len(base_rows)} NF(s) válida(s) encontrada(s) na base, de {len(nfs)} NF(s) lida(s) no XML.')
        fontes = sorted(set((r.get('fonte_frete', 'PLANILHA') for r in base_rows)))
        detalhe_frete = f"{base_status}; frete base: {'+'.join(fontes)}"
        if len(base_rows) > 1:
            trace.append(f"Frete base total somado das {len(base_rows)} NF(s): R$ {self.d.money(result['base_frete'])}.")
        if base_status == 'NF AMBÍGUA':
            trace.append('Ao menos uma NF possui mais de um CT-e NORMAL e o desempate não foi conclusivo. O programa calcula com a melhor linha encontrada, mas mantém status para revisão.')
        elif base_status == 'BASE OK - DESEMPATADA':
            trace.append('Ao menos uma NF tinha mais de um CT-e NORMAL, mas o sistema conseguiu desempatar usando CNPJ/cidade/UF/valor.')
        if any((r.get('fonte_frete') == 'ORIGEM' for r in base_rows)):
            trace.append('Uma ou mais linhas usaram Valor do Frete do CTRC Origem porque o frete da linha estava zerado/baixo ou era subcontratação.')
        pid = early_pid or (self.d.identify_partner(info, tables) if tables else None)
        result['partner_id'] = pid or ''
        if not tables:
            result['status'] = 'TABELAS NÃO CARREGADAS'
            trace.append('A planilha de tabelas/cadastro dos parceiros ainda não foi carregada.')
            return result
        if not pid:
            result['status'] = 'PARCEIRO SEM CADASTRO'
            result['detalhe'] = detalhe_frete
            emit = info.get('emit', {}) or {}
            trace.append(f"Não foi encontrado cadastro para o parceiro emitente. Nome XML: {info.get('emitente', '-')}; CNPJ XML: {emit.get('cnpjcpf', '-')}.")
            return result
        partner_name = (tables.get('partners', {}).get(pid, {}) or {}).get('name', '')
        trace.append(f"Parceiro identificado: {pid} - {partner_name or 'sem nome no cadastro'}.")
        if charge_type == 'NORMAL':
            manual_charge = self.d.detect_partner_manual_extra(pid, info, tables)
            if manual_charge:
                charge_type = manual_charge
                original_charge_type = manual_charge
                result['tipo_cobranca'] = manual_charge
                trace.append(f"Operação especial identificada antes da tabela normal: {manual_charge}.")
        if charge_type == 'ANULACAO':
            trace.append('O XML foi identificado como CT-e de ANULAÇÃO.')
            trace.append('O programa vai mostrar o cálculo normal/tabela apenas para conferência da anulação, sem bloquear como EXTRA REVISAR.')
        if original_charge_type == 'COMPLEMENTAR' and policy.get('complementar_herda_regra_normal'):
            complementary_rows = [r for r in base_rows if r.get('tipo_base') == 'COMPLEMENTAR']
            if complementary_rows:
                expected = sum((r.get('valor_frete_planilha', 0.0) or r.get('valor_frete', 0.0) for r in complementary_rows))
                actual = self.d.parse_number_br(info.get('valor', ''))
                tolerance = tables.get('tolerance', 1.0)
                diff = actual - expected
                result.update({'base_frete': expected, 'base_calculo': 'COMPLEMENTAR_EXATO_BASE', 'modo_calculo': 'COMPLEMENTAR_BASE', 'valor_total_xml': actual, 'valor_comparado': actual, 'componente_comparado': 'VALOR TOTAL XML', 'esperado': expected, 'diferenca': diff, 'tolerancia': tolerance, 'detalhe': f'{detalhe_frete}; complementar exato localizado na base por NF + valor'})
                trace.append('Política MB aplicada: CT-e complementar localizado exatamente na base por NF + valor + vínculo do XML.')
                trace.append(f'Valor complementar na base: R$ {self.d.money(expected)}. Valor XML: R$ {self.d.money(actual)}. Diferença: R$ {self.d.money(diff)}.')
                result['status'] = 'OK COMPLEMENTAR' if abs(diff) <= tolerance else 'DIVERGENTE COMPLEMENTAR +' if diff > 0 else 'DIVERGENTE COMPLEMENTAR -'
                return result
            trace.append('Política MB aplicada: não existe complementar exato na base; a cobrança complementar herdará a regra percentual normal da rota.')
            charge_type = 'NORMAL'
        if charge_type != 'NORMAL' and charge_type != 'ANULACAO':
            trace.append(f'Como o XML parece ser {charge_type}, o programa procurou regra específica na aba REGRAS_EXTRAS antes de aplicar a tabela normal.')
            extra_rule = self.d.choose_extra_rule(pid, charge_type, tables, base_row)
            if not extra_rule:
                result['status'] = 'EXTRA REVISAR'
                result['detalhe'] = f'{detalhe_frete}; cobrança {charge_type} sem regra específica cadastrada'
                trace.append('Nenhuma regra específica foi encontrada na aba REGRAS_EXTRAS para este tipo de cobrança. Bloqueado para revisão manual para evitar falso OK.')
                return result
            calc_base, calc_sources = self.d.sum_base_for_rule(base_rows, extra_rule.get('base_calculo', 'ORIGINAL'))
            result['base_frete'] = calc_base
            result['base_calculo'] = self.d.normalize_base_calculo(extra_rule.get('base_calculo', 'ORIGINAL'))
            expected = self.d.calculate_extra_expected(result['base_frete'], extra_rule)
            actual = self.d.parse_number_br(info.get('valor', ''))
            diff = actual - expected
            result['percentual'] = extra_rule.get('percent', 0.0) or 0.0
            result['frete_minimo'] = extra_rule.get('minimum', 0.0) or 0.0
            result['esperado'] = expected
            result['diferenca'] = diff
            result['regra_extra'] = extra_rule.get('tipo_extra', '') or charge_type
            result['detalhe'] = f"{detalhe_frete}; regra extra: {extra_rule.get('tipo_extra', charge_type)}"
            tolerance = tables.get('tolerance', 1.0)
            result['tolerancia'] = tolerance
            trace.append(f"Regra extra aplicada: {extra_rule.get('tipo_extra', charge_type)}; fonte {extra_rule.get('source', 'REGRAS_EXTRAS')}; base de cálculo {result.get('base_calculo', '-')}; fonte efetiva {'+'.join(calc_sources)}.")
            trace.append(f"Parâmetros da regra extra: percentual {self.d.fmt_percent(result['percentual']) or '-'}; valor fixo R$ {self.d.money(extra_rule.get('valor_fixo', 0.0))}; mínimo R$ {self.d.money(result['frete_minimo'])}.")
            review_status = str(extra_rule.get('status_revisao', '') or '').upper()
            manual_review = ('MANUAL' in review_status or review_status == 'PENDENTE' or ('REVIS' in review_status and review_status != 'REVISAR_OK'))
            if manual_review or expected <= 0:
                result['status'] = 'EXTRA REVISAR'
                trace.append('A cobrança extra foi corretamente separada do frete normal e exige conferência manual; nenhuma aprovação automática foi realizada.')
                return result
            trace.append(f'Valor esperado pela regra extra: R$ {self.d.money(expected)}. Valor XML: R$ {self.d.money(actual)}. Diferença: R$ {self.d.money(diff)}. Tolerância: R$ {self.d.money(tolerance)}.')
            if abs(diff) <= tolerance:
                result['status'] = 'OK EXTRA'
                trace.append('Diferença dentro da tolerância. Validação de cobrança extra OK.')
            elif actual > expected:
                result['status'] = 'DIVERGENTE EXTRA +'
                trace.append('Valor do XML está acima do esperado pela regra extra.')
            else:
                result['status'] = 'DIVERGENTE EXTRA -'
                trace.append('Valor do XML está abaixo do esperado pela regra extra.')
            return result
        peso_rule_kg, peso_rule_source = self.d.peso_base_kg_from_info(info)
        rule_base_row = dict(base_row)
        rule_base_row['peso_regra_kg'] = peso_rule_kg
        rule = self.d.choose_partner_rule(pid, rule_base_row, tables)
        if rule and rule.get('source') == 'REGIOES_FALLBACK_INTERIOR_AP':
            trace.append(f"Regra regional MB aplicada: destino {base_row.get('destino_cidade', '-')}/{base_row.get('destino_uf', '-')} classificado como interior do Amapá. Percentual e mínimo vieram da região MB INTERIORES-AP cadastrada.")
        if not rule:
            fallback = self.d.validate_rodotec_components_fallback(info, pid, tables, base_row, tables.get('tolerance', 1.0))
            if fallback:
                result.update({key: value for key, value in fallback.items() if key != 'trace_extra'})
                result['detalhe'] = f"{detalhe_frete}; {fallback.get('detalhe', '')}"
                trace.extend(fallback.get('trace_extra', []))
                return result
            result['status'] = 'REGRA NÃO ENCONTRADA'
            result['detalhe'] = detalhe_frete
            trace.append('Parceiro existe no cadastro, mas nenhuma regra bateu com origem/destino/região da base.')
            trace.append(f"Origem base: {base_row.get('origem_cidade', '-')}/{base_row.get('origem_uf', '-')}; destino base: {base_row.get('destino_cidade', '-')}/{base_row.get('destino_uf', '-')}.")
            reg_count = sum((1 for reg in tables.get('regions', []) if reg.get('partner_id') == pid))
            trace.append(f'Regiões cadastradas para o parceiro {pid}: {reg_count}. Se a cidade existir na aba REGIOES, o programa deve aplicar a regra por cidade.')
            return result
        special_rule = self.d.choose_weight_special_rule(pid, base_row, tables, peso_rule_kg)
        if special_rule:
            original_percent = rule.get('percent', 0.0) or 0.0
            result['regra_peso_especial'] = 'SIM'
            result['limite_peso_especial_kg'] = special_rule.get('peso_min_kg')
            result['percentual_original_regra'] = original_percent
            result['peso_base_kg'] = peso_rule_kg
            result['peso_xml_fonte'] = peso_rule_source
            result['peso_xml_todos'] = self.d.format_peso_xml_debug(info)
            trace.append(f"Regra especial por peso encontrada: peso {self.d.money(peso_rule_kg)} kg acima de {self.d.money(special_rule.get('peso_min_kg') or 0)} kg.")
            trace.append(f"Percentual original da regra normal seria {self.d.fmt_percent(original_percent) or '-'}; percentual especial aplicado será {self.d.fmt_percent(special_rule.get('percent', 0.0)) or '-'}; base {special_rule.get('base_calculo', '-')}; mínimo R$ {self.d.money(special_rule.get('minimum', 0.0))}.")
            if special_rule.get('observacao'):
                trace.append(f"Observação da regra especial: {special_rule.get('observacao')}.")
            rule = special_rule
        percent = rule.get('percent', 0.0)
        minimum = rule.get('minimum', 0.0)
        if percent <= 0 and minimum <= 0:
            result['status'] = 'REGRA SEM VALOR'
            result['detalhe'] = detalhe_frete
            trace.append('A regra encontrada não possui percentual nem frete mínimo. O cálculo foi bloqueado para evitar falso OK com valor esperado zero.')
            trace.append(f"Regra encontrada: origem {rule.get('origem_cidade') or '*'} / {rule.get('origem_uf') or '*'} → destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
            return result
        if self.d.should_use_frete_peso(rule, info):
            ton_rate = rule.get('ton_rate', 0.0) or 0.0
            peso_kg, peso_source = self.d.peso_base_kg_from_info(info)
            frete_peso_xml, frete_peso_found = self.d.component_value(info, 'FRETE PESO')
            adicionais_xml, adicionais_found = self.d.non_frete_peso_components_value(info)
            actual, comp_label, fallback_total, comp_found, total_xml = self.d.comparison_value_from_xml(info, 'FRETE_PESO')
            tolerance = tables.get('tolerance', 1.0)
            result['modo_calculo'] = 'FRETE_PESO'
            result['base_calculo'] = 'FRETE_PESO'
            result['peso_base_kg'] = peso_kg
            result['peso_xml_fonte'] = peso_source
            result['peso_xml_todos'] = self.d.format_peso_xml_debug(info)
            result['tonelagem_taxa'] = ton_rate
            result['taxa_kg'] = ton_rate / 1000.0 if ton_rate else None
            result['frete_peso_xml'] = frete_peso_xml
            result['adicionais_xml'] = adicionais_xml
            result['valor_total_xml'] = total_xml
            result['valor_comparado'] = actual
            result['componente_comparado'] = comp_label
            result['comparacao_fallback_total'] = fallback_total
            result['percentual'] = None
            result['frete_minimo'] = minimum
            result['tolerancia'] = tolerance
            if ton_rate <= 0 or peso_kg <= 0:
                result['status'] = 'REGRA FRETE PESO SEM DADOS'
                result['detalhe'] = f"{detalhe_frete}; regra: {rule.get('source', 'REGIOES')} {rule.get('regiao', '')}; falta tonelagem ou peso"
                trace.append('A regra indica cálculo por FRETE PESO, mas faltou tonelagem R$/Ton ou peso base no XML.')
                trace.append(f'Peso base lido: {self.d.money(peso_kg)} kg; tonelagem: R$ {self.d.money(ton_rate)}/ton.')
                return result
            frete_peso_calc = peso_kg / 1000.0 * ton_rate
            hybrid_c_vargas = bool(pid == 'AC_LOG_C_VARGAS' and percent > 0 and ton_rate > 0)
            expected_percent = None
            calc_sources = []
            if hybrid_c_vargas:
                calc_base, calc_sources = self.d.sum_base_for_rule(base_rows, rule.get('base_calculo', 'ORIGINAL'))
                result['base_frete'] = calc_base
                result['base_calculo'] = self.d.normalize_base_calculo(rule.get('base_calculo', 'ORIGINAL'))
                result['percentual'] = percent
                expected_percent = calc_base * percent
                frete_peso_esperado = max(frete_peso_calc, minimum, expected_percent)
                result['modo_calculo'] = 'HIBRIDO_PERCENTUAL_FRETE_PESO'
                if frete_peso_esperado == expected_percent:
                    result['criterio_frete_aplicado'] = 'PERCENTUAL'
                elif frete_peso_esperado == frete_peso_calc:
                    result['criterio_frete_aplicado'] = 'FRETE_PESO'
                else:
                    result['criterio_frete_aplicado'] = 'FRETE_MINIMO'
                result['frete_percentual_calculado'] = expected_percent
                result['frete_peso_referencia'] = frete_peso_calc
            else:
                frete_peso_esperado = max(frete_peso_calc, minimum)
            minimum_applied = bool(minimum and frete_peso_esperado == minimum and (minimum > frete_peso_calc) and (expected_percent is None or minimum > expected_percent))
            expected = frete_peso_esperado
            diff = actual - expected
            taxa_kg = ton_rate / 1000.0 if ton_rate else 0.0
            peso_reverso = None
            dif_peso = None
            audit_status = ''
            audit_obs = ''
            if minimum_applied:
                audit_status = 'FRETE MÍNIMO'
                audit_obs = 'Frete mínimo aplicado; o valor cobrado não permite conferir o peso real por cálculo reverso.'
            elif fallback_total:
                audit_status = 'SEM COMPONENTE FRETE PESO'
                audit_obs = 'O XML não trouxe componente FRETE PESO claro; foi usado fallback do valor total.'
            elif taxa_kg > 0 and actual > 0:
                peso_reverso = actual / taxa_kg
                dif_peso = peso_kg - peso_reverso
                if abs(dif_peso) <= 0.05:
                    audit_status = 'PESO OK'
                    audit_obs = 'Peso do XML bate com o cálculo reverso do componente FRETE PESO.'
                else:
                    audit_status = 'CONFERIR PESO'
                    audit_obs = 'Peso usado no XML não bate com o peso reverso calculado pelo FRETE PESO.'
            else:
                audit_status = 'SEM AUDITORIA'
                audit_obs = 'Faltou taxa por kg ou valor comparado para auditar o peso.'
            result['frete_peso_calculado'] = frete_peso_esperado
            result['peso_reverso_kg'] = peso_reverso
            result['dif_peso_kg'] = dif_peso
            result['auditoria_peso_status'] = audit_status
            result['auditoria_peso_obs'] = audit_obs
            result['esperado'] = expected
            result['diferenca'] = diff
            result['base_frete'] = result.get('base_frete')
            min_label = '; frete mínimo aplicado' if minimum_applied else ''
            result['detalhe'] = f"{detalhe_frete}; cálculo FRETE PESO; {rule.get('source', 'REGIOES')} {rule.get('regiao', '')}{min_label}".strip()
            trace.append(f"Regra aplicada: destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
            trace.append(f'Modo de cálculo detectado: FRETE PESO por kg/tonelagem.')
            trace.append(f"Peso usado: {self.d.money(peso_kg)} kg ({peso_source or 'sem fonte'}). Tonelagem da tabela: R$ {self.d.money(ton_rate)} por tonelada.")
            trace.append(f'Base visual do peso: R$ {self.d.money(ton_rate / 1000.0)} por kg ({self.d.money(ton_rate)} ÷ 1000).')
            trace.append(f'Cálculo frete peso: {self.d.money(peso_kg)} kg × R$ {self.d.money(ton_rate / 1000.0)}/kg = R$ {self.d.money(frete_peso_calc)}.')
            if hybrid_c_vargas:
                trace.append(
                    f'AC Log / C Vargas — regra híbrida: percentual R$ {self.d.money(result.get("base_frete"))} × {self.d.fmt_percent(percent)} = R$ {self.d.money(expected_percent)}; '
                    f'frete-peso R$ {self.d.money(frete_peso_calc)}; mínimo R$ {self.d.money(minimum)}. '
                    f'Vale o MAIOR valor: R$ {self.d.money(expected)} ({result.get("criterio_frete_aplicado")}).'
                )
            if result.get('peso_xml_todos'):
                trace.append(f"Pesos encontrados no XML: {result.get('peso_xml_todos')}.")
            if result.get('peso_reverso_kg') is not None:
                trace.append(f"Auditoria de peso: peso reverso = R$ {self.d.money(actual)} ÷ R$ {self.d.money(ton_rate / 1000.0)}/kg = {self.d.money(result.get('peso_reverso_kg'))} kg; diferença = {self.d.money(result.get('dif_peso_kg'))} kg; status {result.get('auditoria_peso_status')}.")
            else:
                trace.append(f"Auditoria de peso: {result.get('auditoria_peso_status') or '-'} - {result.get('auditoria_peso_obs') or '-'}")
            if frete_peso_found:
                trace.append('Componente FRETE PESO no XML: ' + ', '.join((f"{n or '-'} R$ {self.d.money(v)}" for n, v in frete_peso_found)))
            if minimum_applied:
                trace.append(f'Frete mínimo aplicado ao FRETE PESO porque R$ {self.d.money(minimum)} é maior que R$ {self.d.money(frete_peso_calc)}.')
            if adicionais_found:
                trace.append('Componentes adicionais do XML encontrados, mas NÃO entram nesta comparação principal: ' + ', '.join((f"{n or '-'} R$ {self.d.money(v)}" for n, v in adicionais_found)) + f' | Total adicionais informativo: R$ {self.d.money(adicionais_xml)}.')
            else:
                trace.append('Nenhum componente adicional ao FRETE PESO foi encontrado.')
            trace.append(f'Componente comparado do XML: {comp_label} = R$ {self.d.money(actual)}.')
            if fallback_total:
                trace.append('Atenção: componente principal não encontrado; o programa usou o VALOR TOTAL DO SERVIÇO como fallback.')
            trace.append(f'Valor esperado para comparação: R$ {self.d.money(expected)}. Diferença: R$ {self.d.money(diff)}. Tolerância: R$ {self.d.money(tolerance)}.')
            partial_suffix = ''
            min_suffix = ' FRETE MÍNIMO' if minimum_applied else ''
            anul_suffix = ' ANULAÇÃO' if charge_type == 'ANULACAO' else ''
            if 'PENDENTE' in rule.get('status_revisao', ''):
                result['status'] = 'REGRA PENDENTE' + partial_suffix + anul_suffix
                trace.append('A regra usada está marcada como PENDENTE/REVISAR na planilha de tabelas.')
            elif base_status == 'NF AMBÍGUA':
                result['status'] = 'NF AMBÍGUA' + partial_suffix + anul_suffix
                trace.append('Mesmo com cálculo feito, a NF segue ambígua.')
            elif abs(diff) <= tolerance:
                if hybrid_c_vargas:
                    result['status'] = ('OK AC LOG / C VARGAS' + partial_suffix + anul_suffix).strip()
                    trace.append('Diferença dentro da tolerância. Validação OK pela regra híbrida AC Log / C Vargas (maior entre percentual, frete-peso e mínimo).')
                else:
                    result['status'] = ('OK FRETE PESO' + min_suffix + partial_suffix + anul_suffix).strip()
                    if result.get('nfs_ignoradas'):
                        trace.append('Diferença dentro da tolerância. Validação OK por FRETE PESO usando a(s) NF(s) válida(s); NFs sem vínculo confiável foram apenas ignoradas e registradas no log.')
                    else:
                        trace.append('Diferença dentro da tolerância. Validação OK por FRETE PESO.')
            elif actual > expected:
                result['status'] = (('DIVERGENTE AC LOG / C VARGAS +' if hybrid_c_vargas else 'DIVERGENTE FRETE PESO +') + min_suffix + partial_suffix + anul_suffix).strip()
                trace.append('Valor do XML está acima do esperado pela regra híbrida AC Log / C Vargas.' if hybrid_c_vargas else 'Valor do XML está acima do esperado pelo cálculo de FRETE PESO.')
            else:
                result['status'] = (('DIVERGENTE AC LOG / C VARGAS -' if hybrid_c_vargas else 'DIVERGENTE FRETE PESO -') + min_suffix + partial_suffix + anul_suffix).strip()
                trace.append('Valor do XML está abaixo do esperado pela regra híbrida AC Log / C Vargas.' if hybrid_c_vargas else 'Valor do XML está abaixo do esperado pelo cálculo de FRETE PESO.')
            if charge_type == 'ANULACAO':
                trace.append('Observação: por ser ANULAÇÃO, este cálculo é exibido para entendimento/conferência do documento de anulação.')
            return result
        calc_base, calc_sources = self.d.sum_base_for_rule(base_rows, rule.get('base_calculo', 'ORIGINAL'))
        result['base_frete'] = calc_base
        result['base_calculo'] = self.d.normalize_base_calculo(rule.get('base_calculo', 'ORIGINAL'))
        if rule.get('modo_calculo'):
            result['modo_calculo'] = rule.get('modo_calculo')
        expected_percent = result['base_frete'] * percent
        expected_base = max(expected_percent, minimum)
        toll_rule_expected, toll_detail = self.d.rule_pedagio_expected(rule, info)
        actual, comp_label, fallback_total, comp_found, total_xml = self.d.comparison_value_from_xml(info, 'FRETE_VALOR')
        toll_xml_separate, toll_xml_items = self.d.component_value(info, 'PEDAGIO', 'PEDÁGIO')
        toll_expected = toll_rule_expected
        if toll_xml_separate > 0 and not fallback_total:
            # FRETE VALOR e PEDÁGIO são componentes separados no XML.
            toll_expected = 0.0
        expected = expected_base + toll_expected
        diff = actual - expected
        minimum_applied = bool(minimum and expected_base == minimum and (minimum > expected_percent))
        result['valor_total_xml'] = total_xml
        result['valor_comparado'] = actual
        result['componente_comparado'] = comp_label
        result['comparacao_fallback_total'] = fallback_total
        result['percentual'] = percent
        result['frete_minimo'] = minimum
        result['esperado'] = expected
        result['pedagio_esperado'] = toll_expected
        result['pedagio_regra'] = toll_rule_expected
        result['pedagio_xml_separado'] = toll_xml_separate
        result['pedagio_detalhe'] = toll_detail
        result['diferenca'] = diff
        min_label = '; frete mínimo aplicado' if minimum_applied else ''
        result['detalhe'] = f"{detalhe_frete}; base cálculo: {result['base_calculo']}; regra: {rule.get('source', 'REGRAS_PERCENTUAL')} {rule.get('regiao', '')}{min_label}".strip()
        tolerance = tables.get('tolerance', 1.0)
        result['tolerancia'] = tolerance
        trace.append(f"Regra aplicada: origem {rule.get('origem_cidade') or '*'} / {rule.get('origem_uf') or '*'} → destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
        trace.append(f"Percentual da regra: {self.d.fmt_percent(percent) or '-'}; frete mínimo: R$ {self.d.money(minimum)}; base de cálculo: {result['base_calculo']}; fonte efetiva {'+'.join(calc_sources)}.")
        if result['base_calculo'] == 'SEM_ICMS':
            trace.append('Este parceiro/regra está configurado para calcular sobre o Valor do Frete sem ICMS da base Rodovitor.')
        trace.append(f"Cálculo percentual: R$ {self.d.money(result['base_frete'])} × {self.d.fmt_percent(percent)} = R$ {self.d.money(expected_percent)}.")
        if toll_xml_separate > 0 and toll_rule_expected > 0 and toll_expected == 0:
            trace.append(f"Pedágio separado no XML auditado: R$ {self.d.money(toll_xml_separate)}. Ele não foi somado ao FRETE VALOR esperado para evitar dupla cobrança ({toll_detail}).")
        elif toll_expected > 0:
            trace.append(f"Pedágio da regra acrescentado ao FRETE VALOR esperado: R$ {self.d.money(toll_expected)} ({toll_detail}).")
        if minimum_applied:
            trace.append(f'Frete mínimo aplicado porque R$ {self.d.money(minimum)} é maior que o cálculo percentual.')
        else:
            trace.append('Frete mínimo não superou o cálculo percentual.')
        if comp_found:
            trace.append(f'Componente comparado do XML: {comp_label} = R$ {self.d.money(actual)} ({self.d.format_component_list(comp_found)}).')
        else:
            trace.append(f'Componente comparado do XML: {comp_label} = R$ {self.d.money(actual)}.')
        if fallback_total:
            trace.append('Atenção: FRETE VALOR/FRETE PESO não foi encontrado nos componentes; o programa usou o VALOR TOTAL DO SERVIÇO como fallback.')
        trace.append(f'Valor esperado para comparação: R$ {self.d.money(expected)}. Diferença: R$ {self.d.money(diff)}. Tolerância: R$ {self.d.money(tolerance)}.')
        partial_suffix = ''
        anul_suffix = ' ANULAÇÃO' if charge_type == 'ANULACAO' else ''
        if 'PENDENTE' in rule.get('status_revisao', ''):
            result['status'] = 'REGRA PENDENTE' + partial_suffix + anul_suffix
            trace.append('A regra usada está marcada como PENDENTE/REVISAR na planilha de tabelas, então o resultado precisa de conferência manual.')
        elif base_status == 'NF AMBÍGUA':
            result['status'] = 'NF AMBÍGUA' + partial_suffix + anul_suffix
            trace.append('Mesmo com cálculo feito, a NF segue ambígua porque há mais de um CT-e normal na base.')
        elif abs(diff) <= tolerance:
            result['status'] = (('OK FRETE MÍNIMO' if minimum_applied else 'OK') + partial_suffix + anul_suffix).strip()
            if result.get('nfs_ignoradas'):
                trace.append('Diferença dentro da tolerância. Validação OK usando a(s) NF(s) válida(s); NFs sem vínculo confiável foram apenas ignoradas e registradas no log.')
            elif minimum_applied:
                trace.append('Diferença dentro da tolerância. Validação OK com frete mínimo aplicado.')
            else:
                trace.append('Diferença dentro da tolerância. Validação OK.')
        elif actual > expected:
            result['status'] = (('DIVERGENTE FRETE MÍNIMO +' if minimum_applied else 'DIVERGENTE +') + partial_suffix + anul_suffix).strip()
            if minimum_applied:
                trace.append('Valor do XML está acima do frete mínimo esperado. Conferir se há ICMS, taxa ou regra especial não cadastrada.')
            else:
                trace.append('Valor do XML está acima do esperado. Possível cobrança maior, complementar ou extra não cadastrado.')
        else:
            result['status'] = (('DIVERGENTE FRETE MÍNIMO -' if minimum_applied else 'DIVERGENTE -') + partial_suffix + anul_suffix).strip()
            if minimum_applied:
                trace.append('Valor do XML está abaixo do frete mínimo esperado. Conferir tabela/regra/parceiro.')
            else:
                trace.append('Valor do XML está abaixo do esperado. Conferir tabela/regra/parceiro.')
        if charge_type == 'ANULACAO':
            trace.append('Observação: por ser ANULAÇÃO, este cálculo é exibido para entendimento/conferência do documento de anulação.')
        return result
