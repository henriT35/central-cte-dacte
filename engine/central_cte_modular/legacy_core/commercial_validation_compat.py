from __future__ import annotations

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions


def identify_partner(info, tables):
    if not tables:
        return None
    emit = info.get("emit", {}) or {}
    cnpj = only_digits(emit.get("cnpjcpf", ""))
    if cnpj and cnpj in tables.get("cnpj_to_id", {}):
        return tables["cnpj_to_id"][cnpj]
    name = norm_text(info.get("emitente", ""))
    if name:
        aliases = list(tables.get("aliases", []))
        for alias, pid in aliases:
            if alias and alias == name:
                return pid
        partial = []
        for alias, pid in aliases:
            if alias and (alias in name or name in alias) and pid not in partial:
                partial.append(pid)
        if len(partial) == 1:
            return partial[0]
    return None


def detect_partner_charge_type(info):
    """Classifica cobrança normal, extra ou documento especial com prioridade segura."""
    pieces = [
        info.get("tpCTe", ""), info.get("tpServ", ""), info.get("natOp", ""),
        info.get("cfop", ""), info.get("obs", ""), info.get("produto", ""),
        info.get("outras_carac", ""),
    ]
    for comp in info.get("componentes", []) or []:
        pieces.append(comp.get("nome", ""))
    txt = norm_text(" ".join(str(x or "") for x in pieces))
    if "COTACAO" in txt and "AUTORIZ" in txt:
        return "COTACAO_AUTORIZADA"
    if "FRETE REF" in txt and (buscar_sigla_como_token(txt, "COT") or "COTACAO" in txt):
        return "COTACAO_ESPECIAL"
    if "ANUL" in txt:
        return "ANULACAO"
    if "SUBSTIT" in txt:
        return "SUBSTITUICAO"
    if "TABELA ANTIGA" in txt or "FRETE ANTIGO" in txt:
        return "TABELA_ANTIGA"
    if "REEMBOLSO" in txt and "DESCARG" in txt:
        return "REEMBOLSO_DESCARGA"
    if "CAPATAZIA" in txt:
        return "CAPATAZIA"
    if "TEMPO EXCEDIDO" in txt or "PERMANENCIA EXCEDIDA" in txt or "CUSTO EXTRA 5" in txt or "5 HORAS" in txt:
        return "TEMPO_EXCEDIDO"
    if buscar_sigla_como_token(txt, "TDA") or "DIFICULDADE DE ACESSO" in txt:
        return "TDA"
    if "TDE" in txt or "DIFICULDADE DE ENTREGA" in txt:
        return "TDE"
    if any(token in txt for token in ("REENTREGA", "REEENTREGA", "RE ENTREGA", "2 ENTREGA", "SEGUNDA ENTREGA")):
        return "REENTREGA"
    if "DEVOLUCAO" in txt or "RETORNO DE MERCADORIA" in txt:
        return "DEVOLUCAO"
    if "COMPLEMENT" in txt or "COMPL" in txt:
        return "COMPLEMENTAR"
    return "NORMAL"

def extra_matches_charge_type(extra, charge_type):
    tipo = norm_text(extra.get("tipo_extra", ""))
    ch = norm_text(charge_type)
    if not tipo or ch == "NORMAL":
        return False
    # Evita que TDA seja encontrado por substring em ESTADIA.
    if ch == "TDA":
        return tipo == "TDA" or "DIFICULDADE ACESSO" in tipo
    if ch in tipo or tipo in ch:
        return True
    aliases = {
        "COMPLEMENTAR": ["COMPLEMENTO", "COMPLEMENTAR", "COMPL", "DIFERENCA", "AJUSTE"],
        "DEVOLUCAO": ["DEVOLUCAO", "RETORNO"],
        "REENTREGA": ["REENTREGA", "RE ENTREGA", "2 ENTREGA", "SEGUNDA ENTREGA"],
        "ANULACAO": ["ANULACAO", "ANUL"],
        "SUBSTITUICAO": ["SUBSTITUICAO", "SUBSTIT"],
        "REEMBOLSO_DESCARGA": ["REEMBOLSO DESCARGA", "DESCARGA", "TPD DESCARGAS"],
        "CAPATAZIA": ["CAPATAZIA"],
        "TDA": ["TDA", "DIFICULDADE ACESSO"],
        "TDE": ["TDE", "DIFICULDADE ENTREGA"],
        "TEMPO_EXCEDIDO": ["TEMPO EXCEDIDO", "PERMANENCIA", "ESTADIA"],
        "TABELA_ANTIGA": ["TABELA ANTIGA", "HISTORICA", "FRETE ANTIGO"],
        "VEICULO_DEDICADO": ["VEICULO DEDICADO", "OPERACAO DEDICADA", "COLETA PALETES"],
        "COTACAO_AUTORIZADA": ["COTACAO AUTORIZADA", "COTACAO_AUTORIZADA"],
        "COTACAO_ESPECIAL": ["COTACAO ESPECIAL", "COTACAO_ESPECIAL", "FRETE REF"],
    }
    return any(alias in tipo for alias in aliases.get(ch, []))

def extra_condition_matches(extra, base_row=None):
    condition = norm_text(extra.get("condicao", ""))
    if not condition:
        return True
    row = base_row or {}
    city = norm_location(row.get("destino_cidade", ""))
    state = norm_text(row.get("destino_uf", ""))
    for raw_clause in re.split(r"[;|]", condition):
        clause = raw_clause.strip()
        if not clause:
            continue
        if clause.startswith("DESTINO!="):
            wanted = clause.split("!=", 1)[1].strip()
            wanted_city = norm_location(wanted.split("/", 1)[0])
            if city == wanted_city:
                return False
        elif clause.startswith("DESTINO="):
            wanted = clause.split("=", 1)[1].strip()
            parts = wanted.split("/", 1)
            if norm_location(parts[0]) != city:
                return False
            if len(parts) > 1 and norm_text(parts[1]) != state:
                return False
        elif clause.startswith("UF="):
            if norm_text(clause.split("=", 1)[1]) != state:
                return False
    return True


def choose_extra_rule(pid, charge_type, tables, base_row=None):
    if not pid or not tables or charge_type == "NORMAL":
        return None
    inheritance = {
        "MILAYDE_LOBATO": "FENIX",
        "EUNUQUES_LOPES": "EM",
        "MB_SERVICOS_LOG": "MB_AMAZONIA",
    }
    accepted = [pid]
    inherited = inheritance.get(pid)
    if inherited:
        accepted.append(inherited)
    candidates = []
    for extra in tables.get("extras", []) or []:
        partner = extra.get("partner_id")
        if partner not in accepted:
            continue
        if not extra_matches_charge_type(extra, charge_type):
            continue
        if not extra_condition_matches(extra, base_row):
            continue
        score = 20 if partner == pid else 10
        if extra.get("condicao"):
            score += 4
        if extra.get("percent"):
            score += 2
        if extra.get("valor_fixo"):
            score += 2
        if extra.get("minimum"):
            score += 1
        selected = dict(extra)
        if partner != pid:
            selected["inherited_from"] = partner
            selected["partner_id_original"] = partner
            selected["partner_id"] = pid
        candidates.append((score, selected))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def calculate_extra_expected(base_frete, extra_rule):
    percent = extra_rule.get("percent", 0.0) or 0.0
    fixed = extra_rule.get("valor_fixo", 0.0) or 0.0
    minimum = extra_rule.get("minimum", 0.0) or 0.0
    values = []
    if percent > 0:
        values.append(base_frete * percent)
    if fixed > 0:
        values.append(fixed)
    expected = max(values) if values else 0.0
    if minimum > expected:
        expected = minimum
    return expected


def get_nfs_from_info(info):
    """Retorna todas as NFs encontradas no XML, sem duplicar."""
    nfs = []
    seen = set()
    for d in info.get("docs", []) or []:
        nf = normalize_nf(d.get("n_doc", ""))
        if nf and nf not in seen:
            seen.add(nf)
            nfs.append(nf)
    return nfs


def get_nf_from_info(info):
    nfs = get_nfs_from_info(info)
    return nfs[0] if nfs else ""


def is_generic_destination(name):
    n = norm_text(name)
    generic_terms = ["INTERIOR", "INTERIORES", "REGIAO", "REGIÃO", "POLO", "OUTROS", "DIVERSOS", "CLIENTE"]
    return any(t in n for t in generic_terms)


def rule_matches_location(rule, base_row):
    dest_city = base_row.get("destino_cidade", "") if base_row else ""
    dest_uf = base_row.get("destino_uf", "") if base_row else ""
    orig_city = base_row.get("origem_cidade", "") if base_row else ""
    orig_uf = base_row.get("origem_uf", "") if base_row else ""
    score = 0
    if rule.get("destino_cidade"):
        if rule["destino_cidade"] == dest_city:
            score += 60
        elif is_generic_destination(rule["destino_cidade"]) and (not rule.get("destino_uf") or rule.get("destino_uf") == dest_uf):
            score += 12
        else:
            return None
    if rule.get("destino_uf"):
        if rule["destino_uf"] == dest_uf:
            score += 18
        else:
            return None
    if rule.get("origem_cidade"):
        if rule["origem_cidade"] == orig_city:
            score += 25
        else:
            return None
    if rule.get("origem_uf"):
        if rule["origem_uf"] == orig_uf:
            score += 10
        else:
            return None
    if rule.get("regiao"):
        score += 2
    if rule.get("percent"):
        score += 1
    return score


def rule_matches_weight(rule, base_row):
    lower = float(rule.get("peso_min_kg", 0.0) or 0.0)
    upper = float(rule.get("peso_max_kg", 0.0) or 0.0)
    if lower <= 0 and upper <= 0:
        return True
    if not base_row:
        return False
    weight = float(base_row.get("peso_regra_kg", 0.0) or base_row.get("peso_kg", 0.0) or 0.0)
    if weight <= 0:
        return False
    if lower > 0:
        if rule.get("peso_min_inclusivo", True):
            if weight < lower:
                return False
        elif weight <= lower:
            return False
    if upper > 0:
        if rule.get("peso_max_inclusivo", True):
            if weight > upper:
                return False
        elif weight >= upper:
            return False
    return True


def choose_partner_rule(pid, base_row, tables):
    if not pid or not tables or not base_row:
        return None

    # Função local porque este módulo é rebundado no namespace legado em tempo
    # de execução. Helpers globais novos não são necessariamente copiados pelo
    # rebinder histórico.
    def _rule_matches_weight(rule, row):
        lower = float(rule.get("peso_min_kg", 0.0) or 0.0)
        upper = float(rule.get("peso_max_kg", 0.0) or 0.0)
        if lower <= 0 and upper <= 0:
            return True
        weight = float((row or {}).get("peso_regra_kg", 0.0) or (row or {}).get("peso_kg", 0.0) or 0.0)
        if weight <= 0:
            return False
        if lower > 0:
            if rule.get("peso_min_inclusivo", True):
                if weight < lower:
                    return False
            elif weight <= lower:
                return False
        if upper > 0:
            if rule.get("peso_max_inclusivo", True):
                if weight > upper:
                    return False
            elif weight >= upper:
                return False
        return True

    rules = [r for r in tables.get("rules", []) if r.get("partner_id") == pid]
    scored = []

    # 1) Regras diretas da aba REGRAS_PERCENTUAL.
    for r in rules:
        if not _rule_matches_weight(r, base_row):
            continue
        score = rule_matches_location(r, base_row)
        if score is not None:
            scored.append((score, r))

    # 2) Regras por cidade/região da aba REGIOES.
    #
    # Bug corrigido na Beta 1.1.21:
    # antes o código retornava None quando o parceiro não tinha regra ativa em
    # REGRAS_PERCENTUAL. Isso bloqueava parceiros como Rodotec/W_S_TRANSPORTES,
    # cuja tabela foi detalhada cidade por cidade na aba REGIOES.
    dest_city = base_row.get("destino_cidade", "") if base_row else ""
    dest_uf = base_row.get("destino_uf", "") if base_row else ""
    orig_city = base_row.get("origem_cidade", "") if base_row else ""
    orig_uf = base_row.get("origem_uf", "") if base_row else ""

    matching_regions = []
    for reg in tables.get("regions", []):
        if reg.get("partner_id") != pid:
            continue
        if reg.get("cidade") and reg.get("cidade") != dest_city:
            continue
        if reg.get("uf") and reg.get("uf") != dest_uf:
            continue
        if not _rule_matches_weight(reg, base_row):
            continue
        matching_regions.append(reg)

    for reg in matching_regions:
        reg_name = reg.get("regiao", "")

        # Se existir uma regra percentual por nome de região, aplica também.
        for r in rules:
            if reg_name and r.get("regiao") == reg_name and _rule_matches_weight(r, base_row):
                scored.append((45, r))

        # Mas se a própria aba REGIOES já tiver percentual/frete mínimo,
        # ela deve bastar para calcular.
        if reg.get("percent") or reg.get("minimum"):
            score = 60
            if reg.get("cidade") == dest_city and reg.get("uf") == dest_uf:
                score = 80
            scored.append((score, {
                "partner_id": pid,
                "origem_cidade": orig_city,
                "origem_uf": orig_uf,
                "destino_cidade": dest_city,
                "destino_uf": dest_uf,
                "regiao": reg_name,
                "percent": reg.get("percent", 0.0),
                "minimum": reg.get("minimum", 0.0),
                "ton_rate": reg.get("ton_rate", 0.0),
                "modo_calculo": reg.get("modo_calculo", ""),
                "base_calculo": normalize_base_calculo(reg.get("base_calculo", "ORIGINAL")),
                "inclui_complementar": "NAO",
                "status_revisao": reg.get("status_revisao", ""),
                "gris_ativo": reg.get("gris_ativo", False),
                "percentual_gris": reg.get("percentual_gris", 0.0) or reg.get("gris_percentual", 0.0),
                "pedagio_ativo": reg.get("pedagio_ativo", False),
                "valor_pedagio": reg.get("valor_pedagio", 0.0) or reg.get("pedagio_valor", 0.0),
                "fracao_pedagio_kg": reg.get("fracao_pedagio_kg", 0.0) or reg.get("pedagio_fracao_kg", 0.0),
                "tipo_pedagio": reg.get("tipo_pedagio", ""),
                "raw": reg.get("raw", {}),
                "tipo_trecho": reg.get("tipo_trecho", ""),
                "peso_min_kg": reg.get("peso_min_kg", 0.0),
                "peso_max_kg": reg.get("peso_max_kg", 0.0),
                "peso_min_inclusivo": reg.get("peso_min_inclusivo", True),
                "peso_max_inclusivo": reg.get("peso_max_inclusivo", True),
                "source": "REGIOES",
            }))

    # Política conservadora MB: Macapá/Santana usam as regras exatas; qualquer
    # outra cidade do AP pode herdar a região MB INTERIORES-AP cadastrada.
    # Os percentuais e mínimos continuam vindo da planilha, não do código.
    policy = xml_validation_partner_policy(pid)
    if not scored and policy.get("fallback_regional_interior_ap") and dest_uf == "AP" and dest_city not in {"MACAPA", "SANTANA"}:
        templates = []
        for r in rules:
            if (
                "MB INTERIORES" in norm_text(r.get("regiao", ""))
                and (r.get("percent") or r.get("minimum"))
                and _rule_matches_weight(r, base_row)
            ):
                templates.append(r)
        for reg in tables.get("regions", []):
            if reg.get("partner_id") != pid:
                continue
            if "MB INTERIORES" not in norm_text(reg.get("regiao", "")):
                continue
            if not (reg.get("percent") or reg.get("minimum")):
                continue
            if not _rule_matches_weight(reg, base_row):
                continue
            templates.append({
                "partner_id": pid,
                "origem_cidade": orig_city,
                "origem_uf": orig_uf,
                "destino_cidade": dest_city,
                "destino_uf": dest_uf,
                "regiao": reg.get("regiao", "MB INTERIORES-AP"),
                "percent": reg.get("percent", 0.0),
                "minimum": reg.get("minimum", 0.0),
                "ton_rate": reg.get("ton_rate", 0.0),
                "modo_calculo": reg.get("modo_calculo", ""),
                "base_calculo": normalize_base_calculo(reg.get("base_calculo", "ORIGINAL")),
                "inclui_complementar": "NAO",
                "status_revisao": reg.get("status_revisao", ""),
                "gris_ativo": reg.get("gris_ativo", False),
                "percentual_gris": reg.get("percentual_gris", 0.0) or reg.get("gris_percentual", 0.0),
                "pedagio_ativo": reg.get("pedagio_ativo", False),
                "valor_pedagio": reg.get("valor_pedagio", 0.0) or reg.get("pedagio_valor", 0.0),
                "fracao_pedagio_kg": reg.get("fracao_pedagio_kg", 0.0) or reg.get("pedagio_fracao_kg", 0.0),
                "tipo_pedagio": reg.get("tipo_pedagio", ""),
                "raw": reg.get("raw", {}),
                "tipo_trecho": reg.get("tipo_trecho", ""),
                "peso_min_kg": reg.get("peso_min_kg", 0.0),
                "peso_max_kg": reg.get("peso_max_kg", 0.0),
                "peso_min_inclusivo": reg.get("peso_min_inclusivo", True),
                "peso_max_inclusivo": reg.get("peso_max_inclusivo", True),
                "source": "REGIOES_FALLBACK_INTERIOR_AP",
            })
        if templates:
            template = dict(templates[0])
            template.update({
                "origem_cidade": orig_city,
                "origem_uf": orig_uf,
                "destino_cidade": dest_city,
                "destino_uf": dest_uf,
                "source": "REGIOES_FALLBACK_INTERIOR_AP",
            })
            scored.append((55, template))

    if not scored:
        return None

    scored.sort(
        key=lambda item: (
            item[0],
            1 if (item[1].get("peso_min_kg") or item[1].get("peso_max_kg")) else 0,
            -float(item[1].get("peso_min_kg", 0.0) or 0.0),
            item[1].get("percent", 0),
            item[1].get("minimum", 0),
        ),
        reverse=True,
    )
    return scored[0][1]



def candidate_summary(row):
    if not row:
        return "-"
    raw_source = norm_text(row.get("fonte_frete", ""))
    source_label = {
        "ORIGEM": "Frete do CTRC/CT-e de origem",
        "PLANILHA": "Frete atual do registro SSW",
    }.get(raw_source, raw_source or "não informado")
    parts = [
        f"CT-e {row.get('cte', '') or '-'}",
        f"Tipo {row.get('tipo_base', '') or '-'}",
        "Formato da base SSW Web",
        f"Frete atual R$ {money(row.get('valor_frete_planilha', 0.0) or row.get('valor_frete', 0.0))}",
        f"Frete origem R$ {money(row.get('valor_frete_origem', 0.0))}",
        f"Fonte do valor {source_label}",
        f"Destino {row.get('destino_cidade', '') or '-'} / {row.get('destino_uf', '') or '-'}",
    ]
    if row.get("cte_origem") or row.get("ctrc_origem"):
        parts.append(f"Origem {row.get('cte_origem') or row.get('ctrc_origem')}")
    return " | ".join(parts)




def special_weight_city_match(rule_city, dest_city):
    rc = norm_text(rule_city)
    dc = norm_text(dest_city)
    if not rc:
        return 10
    if rc == dc:
        return 100
    if rc in {"DIVERSOS", "DEMAIS", "DEMAIS CIDADES", "DEMAIS CIDADES TO", "INTERIOR", "INTERIORES"}:
        return 50
    if rc and dc and (rc in dc or dc in rc):
        return 70
    return None


def choose_weight_special_rule(pid, base_row, tables, peso_kg):
    """Escolhe regra especial por peso, usada quando a tabela muda o percentual acima de um limite.

    Exemplo: MRV/Exclusiva cobra percentual menor quando o CT-e passa de 10.000 kg.
    A regra fica na aba REGRAS_PESO_ESPECIAL para não ficar escondida no código.
    """
    if not pid or not base_row or not tables or not peso_kg:
        return None
    dest_city = norm_text(base_row.get("destino_cidade", ""))
    dest_uf = norm_text(base_row.get("destino_uf", ""))
    orig_city = norm_text(base_row.get("origem_cidade", ""))
    orig_uf = norm_text(base_row.get("origem_uf", ""))
    scored = []
    for r in tables.get("peso_especial", []) or []:
        if r.get("partner_id") != pid:
            continue
        limit = r.get("peso_min_kg", 0.0) or 0.0
        # A tabela diz "acima de 10.000 kg"; portanto 10.000 exatos não ativa.
        if limit and peso_kg <= limit:
            continue
        rule_uf = norm_text(r.get("destino_uf", ""))
        if rule_uf and rule_uf != dest_uf:
            continue
        city_score = special_weight_city_match(r.get("destino_cidade", ""), dest_city)
        if city_score is None:
            continue
        score = city_score + (20 if rule_uf and rule_uf == dest_uf else 0) + (limit / 100000.0)
        scored.append((score, r))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1].get("percent", 0.0)), reverse=True)
    selected = dict(scored[0][1])
    selected.update({
        "origem_cidade": orig_city,
        "origem_uf": orig_uf,
        "destino_cidade": dest_city,
        "destino_uf": dest_uf,
        "ton_rate": 0.0,
        "inclui_complementar": "NAO",
    })
    return selected


def normalize_base_calculo(value):
    text = norm_text(value or "ORIGINAL")
    if not text:
        return "ORIGINAL"
    text = text.replace("-", " ").replace("_", " ")
    if ("SEM" in text and "ICMS" in text) or ("FRETE" in text and "SEMICMS" in text):
        return "SEM_ICMS"
    if "MERCADORIA" in text or "VALOR CARGA" in text or "VALOR DA CARGA" in text:
        return "MERCADORIA"
    if "ORIGEM" in text:
        return "ORIGEM"
    return "ORIGINAL"

def base_value_for_rule(row, base_calculo):
    calc = normalize_base_calculo(base_calculo)
    if calc == "SEM_ICMS":
        sem_icms = row.get("valor_frete_sem_icms", 0.0) or 0.0
        if sem_icms > 0:
            return sem_icms, "SEM_ICMS"
        return row.get("valor_frete", 0.0) or 0.0, "SEM_ICMS_INDISPONIVEL_USOU_ORIGINAL"
    if calc == "MERCADORIA":
        merchandise = row.get("valor_mercadoria", 0.0) or 0.0
        if merchandise > 0:
            return merchandise, "MERCADORIA"
        return 0.0, "MERCADORIA_INDISPONIVEL"
    if calc == "ORIGEM":
        origem = row.get("valor_frete_origem", 0.0) or 0.0
        if origem > 0:
            return origem, "ORIGEM"
        return row.get("valor_frete", 0.0) or 0.0, "ORIGEM_INDISPONIVEL_USOU_ORIGINAL"
    atual = row.get("valor_frete_planilha", 0.0) or 0.0
    if atual > 0:
        return atual, "ORIGINAL"
    return row.get("valor_frete", 0.0) or 0.0, "ORIGINAL_FALLBACK_LEGADO"

def sum_base_for_rule(rows, base_calculo):
    total = 0.0
    sources = []
    for row in rows:
        value, source = base_value_for_rule(row, base_calculo)
        total += value
        if source not in sources:
            sources.append(source)
    return total, sources


def component_value(info, *name_parts):
    wanted = [norm_text(p) for p in name_parts if str(p or "").strip()]
    total = 0.0
    found = []
    for comp in info.get("componentes", []) or []:
        nome = norm_text(comp.get("nome", ""))
        if wanted and not any(w in nome for w in wanted):
            continue
        val = parse_number_br(comp.get("valor", ""))
        total += val
        found.append((comp.get("nome", ""), val))
    return total, found


def total_components_value(info):
    total = 0.0
    for comp in info.get("componentes", []) or []:
        total += parse_number_br(comp.get("valor", ""))
    return total


def non_frete_peso_components_value(info):
    total = 0.0
    found = []
    for comp in info.get("componentes", []) or []:
        nome_norm = norm_text(comp.get("nome", ""))
        val = parse_number_br(comp.get("valor", ""))
        if "FRETE" in nome_norm and "PESO" in nome_norm:
            continue
        total += val
        if val:
            found.append((comp.get("nome", ""), val))
    return total, found


def peso_base_kg_from_info(info):
    for key in ("peso_base", "peso_aferido", "peso_bruto"):
        val = parse_number_br(info.get(key, ""))
        if val > 0:
            return val, key
    return 0.0, ""


def peso_xml_debug_from_info(info):
    """Lista todos os pesos relevantes encontrados no XML.

    O cálculo continua usando a primeira fonte válida na ordem:
    peso_base, peso_aferido e peso_bruto. Esta função só ajuda na auditoria.
    """
    labels = {
        "peso_base": "Peso base",
        "peso_aferido": "Peso aferido",
        "peso_bruto": "Peso bruto",
        "cubagem": "Cubagem",
    }
    items = []
    for key in ("peso_base", "peso_aferido", "peso_bruto", "cubagem"):
        raw = str(info.get(key, "") or "").strip()
        val = parse_number_br(raw)
        if raw or val:
            items.append({"campo": key, "label": labels.get(key, key), "raw": raw, "valor": val})
    return items


def format_peso_xml_debug(info):
    items = peso_xml_debug_from_info(info)
    if not items:
        return ""
    parts = []
    for item in items:
        if item.get("valor", 0.0):
            parts.append(f"{item['label']}: {money(item['valor'])}")
        else:
            parts.append(f"{item['label']}: {item.get('raw', '')}")
    return " | ".join(parts)


def should_use_frete_peso(rule, info):
    ton_rate = rule.get("ton_rate", 0.0) or 0.0
    modo = norm_text(rule.get("modo_calculo", ""))
    frete_peso_xml, _ = component_value(info, "FRETE PESO")
    if "FRETE" in modo and "PESO" in modo:
        return True
    if ("PESO" in modo or "TON" in modo or "KG" in modo) and ton_rate > 0:
        return True
    return ton_rate > 0 and frete_peso_xml > 0


def component_values_by_keywords(info, keywords):
    total = 0.0
    found = []
    kws = [norm_text(k) for k in keywords if str(k or "").strip()]
    for comp in info.get("componentes", []) or []:
        nome = norm_text(comp.get("nome", ""))
        if all(k in nome for k in kws):
            val = parse_number_br(comp.get("valor", ""))
            total += val
            found.append((comp.get("nome", ""), val))
    return total, found


def comparison_value_from_xml(info, mode="FRETE_VALOR"):
    """Valor do XML que será comparado com o cálculo.

    Não usa mais o valor total do CT-e por padrão, porque o total inclui GRIS,
    pedágio e outras taxas. Para validação da regra principal, usamos o
    componente principal do XML.
    """
    mode_norm = norm_text(mode)
    total_xml = parse_number_br(info.get("valor", ""))

    if "PESO" in mode_norm:
        val, found = component_values_by_keywords(info, ["FRETE", "PESO"])
        if found:
            return val, "FRETE PESO", False, found, total_xml
        return total_xml, "VALOR TOTAL DO SERVIÇO (fallback)", True, [], total_xml

    val, found = component_values_by_keywords(info, ["FRETE", "VALOR"])
    if found:
        return val, "FRETE VALOR", False, found, total_xml

    # Alguns XMLs podem trazer só FRETE PESO. Nesse caso, comparar com o componente
    # de frete ainda é melhor do que comparar com o total do CT-e.
    val, found = component_values_by_keywords(info, ["FRETE", "PESO"])
    if found:
        return val, "FRETE PESO (fallback)", False, found, total_xml

    return total_xml, "VALOR TOTAL DO SERVIÇO (fallback)", True, [], total_xml


def format_component_list(found):
    if not found:
        return "-"
    return ", ".join(f"{n or '-'} R$ {money(v)}" for n, v in found)

def validation_report_text(info):
    result = info.get("validacao") or {}
    lines = []
    lines.append("=" * 72)
    lines.append(f"Arquivo XML: {info.get('arquivo', '-')}")
    lines.append(f"CT-e parceiro: {info.get('numero', '-')}/{info.get('serie', '-')}")
    lines.append(f"Parceiro XML: {info.get('emitente', '-')}")
    lines.append(f"Destinatário XML: {info.get('destinatario', '-')}")
    lines.append(f"Valor XML: R$ {money(info.get('valor', ''))}")
    lines.append(f"NF lida: {result.get('nf', '') or get_nf_from_info(info) or '-'}")
    ignored_nfs = list(result.get("nfs_nao_encontradas") or [])
    ignored_nfs.extend(f"{nf} (INCOMPATÍVEL)" for nf in (result.get("nfs_incompativeis") or []))
    if ignored_nfs:
        lines.append(f"NFs não encontradas/ignoradas: {', '.join(ignored_nfs)}")
    if result.get("validacao_parcial"):
        lines.append("Validação parcial: SIM")
    lines.append("")
    if not result:
        lines.append("Status: AINDA NÃO VALIDADO")
        lines.append("Execute 'Validar valores' para gerar o diagnóstico.")
        return "\n".join(lines)
    lines.append(f"Status: {result.get('status', '-')}")
    if info.get("revisao_manual") or info.get("observacao_manual"):
        lines.append(f"Revisão manual: {info.get('revisao_manual', '-') or '-'}")
        if info.get("revisao_data"):
            lines.append(f"Data revisão: {info.get('revisao_data')}")
        if info.get("observacao_manual"):
            lines.append(f"Observação manual: {info.get('observacao_manual')}")
    lines.append(f"Parceiro ID: {result.get('partner_id', '-') or '-'}")
    if result.get("status") == "PARCEIRO SEM CADASTRO":
        emit = info.get("emit", {}) or {}
        lines.append("Cálculo percentual: NÃO EXECUTADO")
        lines.append("Motivo: parceiro emitente não encontrado no cadastro/tabela de parceiros.")
        lines.append(f"CNPJ XML: {emit.get('cnpjcpf', '-') or '-'}")
        lines.append("Ação: cadastre este parceiro na aba PARCEIROS/REGRAS_PERCENTUAL ou use 'Calc. manual %' para conferir este caso.")
        lines.append("Dica: se o parceiro tiver 2 CNPJs, coloque os dois no cadastro. A Beta 1.1.19 aceita CNPJ; CNPJ2; CNPJ3 ou vários CNPJs na mesma célula separados por ponto-e-vírgula.")
    lines.append(f"Tipo cobrança: {result.get('tipo_cobranca', '-') or '-'}")
    if result.get("regra_extra"):
        lines.append(f"Regra extra: {result.get('regra_extra')}")
    lines.append(f"Frete base: R$ {money(result.get('base_frete', '')) if result.get('base_frete') is not None else '-'}")
    if result.get("base_calculo"):
        lines.append(f"Base de cálculo: {result.get('base_calculo')}")
    if result.get("modo_calculo"):
        lines.append(f"Modo de cálculo: {result.get('modo_calculo')}")
    if result.get("peso_base_kg") is not None:
        lines.append(f"Peso usado: {money(result.get('peso_base_kg'))} kg")
    if result.get("peso_xml_fonte"):
        lines.append(f"Fonte do peso usado: {result.get('peso_xml_fonte')}")
    if result.get("peso_xml_todos"):
        lines.append(f"Pesos encontrados no XML: {result.get('peso_xml_todos')}")
    if result.get("regra_peso_especial"):
        lines.append(f"Regra especial por peso: {result.get('regra_peso_especial')}")
        if result.get("limite_peso_especial_kg") is not None:
            lines.append(f"Limite da regra especial: acima de {money(result.get('limite_peso_especial_kg'))} kg")
        if result.get("percentual_original_regra") is not None:
            lines.append(f"Percentual normal original: {fmt_percent(result.get('percentual_original_regra')) or '-'}")
    if result.get("peso_reverso_kg") is not None:
        lines.append(f"Peso reverso pelo FRETE PESO: {money(result.get('peso_reverso_kg'))} kg")
    if result.get("dif_peso_kg") is not None:
        lines.append(f"Diferença de peso: {money(result.get('dif_peso_kg'))} kg")
    if result.get("auditoria_peso_status"):
        lines.append(f"Auditoria do peso: {result.get('auditoria_peso_status')} - {result.get('auditoria_peso_obs')}")
    if result.get("tonelagem_taxa") is not None:
        lines.append(f"Tonelagem tabela: R$ {money(result.get('tonelagem_taxa'))}/ton")
    if result.get("taxa_kg") is not None:
        lines.append(f"Base visual do peso: R$ {money(result.get('taxa_kg'))}/kg")
    if result.get("frete_peso_calculado") is not None:
        lines.append(f"Frete peso calculado: R$ {money(result.get('frete_peso_calculado'))}")
    if result.get("adicionais_xml") is not None:
        lines.append(f"Adicionais XML informativos: R$ {money(result.get('adicionais_xml'))}")
    if result.get("valor_comparado") is not None:
        lines.append(f"Valor comparado do XML: R$ {money(result.get('valor_comparado'))}")
        lines.append(f"Componente comparado: {result.get('componente_comparado') or '-'}")
    lines.append(f"Percentual: {fmt_percent(result.get('percentual', '')) or '-'}")
    lines.append(f"Frete mínimo: R$ {money(result.get('frete_minimo', '')) if result.get('frete_minimo') is not None else '-'}")
    lines.append(f"Esperado: R$ {money(result.get('esperado', '')) if result.get('esperado') is not None else '-'}")
    lines.append(f"Diferença: R$ {money(result.get('diferenca', '')) if result.get('diferenca') is not None else '-'}")
    lines.append(f"Tolerância: R$ {money(result.get('tolerancia', '')) if result.get('tolerancia') is not None else '-'}")
    if result.get("detalhe"):
        lines.append(f"Detalhe curto: {result.get('detalhe')}")
    lines.append("")
    lines.append("DIAGNÓSTICO PASSO A PASSO")
    lines.append("-" * 72)
    trace = result.get("trace") or []
    if trace:
        for step in trace:
            lines.append(f"• {step}")
    else:
        lines.append("• Sem diagnóstico detalhado disponível para este item.")
    candidates = result.get("base_candidates_summary") or []
    if candidates:
        lines.append("")
        lines.append("OCORRÊNCIAS ENCONTRADAS NA BASE")
        lines.append("-" * 72)
        for idx, cand in enumerate(candidates, start=1):
            lines.append(f"{idx}. {cand}")
    return "\n".join(lines)


def status_nf_fora_base_periodo():
    return "NF FORA DA BASE / PERÍODO"


def diagnostico_nf_fora_base_periodo(nfs=None):
    base = "A NF não foi localizada na base carregada. Isso normalmente acontece quando a base Rodovitor foi extraída por período e o XML pertence a outro intervalo."
    if nfs:
        return base + " NF(s): " + ", ".join(str(x) for x in nfs)
    return base


def summarize_base_statuses(statuses):
    if not statuses:
        return "NF NÃO ENCONTRADA"
    unique = []
    for s in statuses:
        if s not in unique:
            unique.append(s)
    if any(s == "NF NÃO ENCONTRADA" for s in unique):
        return "NF NÃO ENCONTRADA"
    if any(s == "ORIGINAL NÃO ENCONTRADO" for s in unique):
        return "ORIGINAL NÃO ENCONTRADO"
    if any(s == "NF AMBÍGUA" for s in unique):
        return "NF AMBÍGUA"
    if any(s == "BASE OK - DESEMPATADA" for s in unique):
        return "BASE OK - DESEMPATADA"
    return unique[0]


def base_rows_have_same_route(rows):
    if not rows:
        return True
    first = rows[0]
    keys = ("origem_cidade", "origem_uf", "destino_cidade", "destino_uf")
    return all(all((r.get(k, "") == first.get(k, "")) for k in keys) for r in rows[1:])


def detect_partner_manual_extra(pid, info, tables=None):
    """Detecta operação dedicada que não pode ser aprovada como percentual normal."""
    if pid != "MB_SERVICOS_LOG":
        return ""
    text_value = norm_text(" ".join(str(info.get(key, "") or "") for key in ("obs", "produto", "outras_carac")))
    total = parse_number_br(info.get("valor", ""))
    known_values = (350.0, 500.0, 600.0, 700.0, 900.0, 1200.0)
    if ("MANIFESTO" in text_value or "PLACA" in text_value or "PALETE" in text_value) and any(abs(total - value) <= 0.01 for value in known_values):
        return "VEICULO_DEDICADO"
    return ""


def rule_pedagio_expected(rule, info):
    active = bool(rule.get("pedagio_ativo"))
    value = rule.get("valor_pedagio", 0.0) or rule.get("pedagio_valor", 0.0) or 0.0
    if not active or value <= 0:
        return 0.0, ""
    kind = norm_text(rule.get("tipo_pedagio", ""))
    fraction = rule.get("fracao_pedagio_kg", 0.0) or rule.get("pedagio_fracao_kg", 0.0) or 0.0
    # O tipo explícito por CT-e prevalece sobre qualquer fração padrão
    # enriquecida pelo controle compacto.
    if "CTE" in kind or "CONHECIMENTO" in kind or "EMISSAO" in kind:
        return value, "1 CT-e"
    if "KG" in kind or fraction > 0:
        charged, charged_items = component_value(info, "PEDAGIO", "PEDÁGIO")
        if charged <= 0:
            return 0.0, "pedágio opcional não cobrado no XML"
        weight, source = peso_base_kg_from_info(info)
        if weight <= 0:
            return 0.0, "PEDAGIO SEM PESO"
        fraction = fraction or 100.0
        units = int((weight - 1e-9) // fraction) + 1
        return units * value, f"{units} fração(ões) de {fraction:g} kg ({source})"
    return value, "1 CT-e"


def validate_rodotec_components_fallback(info, pid, tables, base_row=None, tolerance=1.0):
    if pid != "W_S_TRANSPORTES" or not tables:
        return None
    freight_component, freight_found = component_value(info, "FRETE PESO")
    weight, weight_source = peso_base_kg_from_info(info)
    if freight_component <= 0 or weight <= 0:
        return None
    candidates = []
    for region in tables.get("regions", []) or []:
        if region.get("partner_id") != pid:
            continue
        ton_rate = region.get("ton_rate", 0.0) or 0.0
        if ton_rate <= 0:
            continue
        expected_freight = weight / 1000.0 * ton_rate
        delta = abs(freight_component - expected_freight)
        candidates.append((delta, region, expected_freight))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    delta, template, expected_freight = candidates[0]
    if delta > max(float(tolerance or 0), 0.05):
        return None
    gris_actual, gris_found = component_value(info, "GRIS")
    toll_actual, toll_found = component_value(info, "PEDAGIO", "PEDÁGIO")
    merchandise = parse_number_br(info.get("valor_carga", "")) or (base_row or {}).get("valor_mercadoria", 0.0) or 0.0
    gris_percent = template.get("percentual_gris", 0.0) or template.get("gris_percentual", 0.0) or 0.0
    gris_expected = merchandise * gris_percent if gris_actual > 0 and gris_percent > 0 else 0.0
    toll_expected = 0.0
    toll_detail = ""
    if toll_actual > 0:
        toll_expected, toll_detail = rule_pedagio_expected(template, info)
    expected = expected_freight + gris_expected + toll_expected
    actual = parse_number_br(info.get("valor", ""))
    diff = actual - expected
    return {
        "status": "OK RODOTEC COMPONENTES" if abs(diff) <= tolerance else ("DIVERGENTE RODOTEC +" if diff > 0 else "DIVERGENTE RODOTEC -"),
        "esperado": expected,
        "diferenca": diff,
        "valor_comparado": actual,
        "componente_comparado": "FRETE PESO + GRIS + PEDÁGIO",
        "base_calculo": "COMPONENTES RODOTEC",
        "modo_calculo": "KG_TON_COMPONENTES",
        "peso_base_kg": weight,
        "peso_xml_fonte": weight_source,
        "tonelagem_taxa": template.get("ton_rate", 0.0),
        "frete_peso_xml": freight_component,
        "frete_peso_calculado": expected_freight,
        "adicionais_xml": gris_actual + toll_actual,
        "tolerancia": tolerance,
        "detalhe": f"fallback Rodotec por componentes; região modelo {template.get('regiao', '-')}",
        "trace_extra": [
            f"Fallback Rodotec: FRETE PESO R$ {money(freight_component)} conferido por {money(weight)} kg × R$ {money(template.get('ton_rate', 0.0) / 1000.0)}/kg = R$ {money(expected_freight)}.",
            f"GRIS esperado R$ {money(gris_expected)}; GRIS XML R$ {money(gris_actual)}.",
            f"Pedágio esperado R$ {money(toll_expected)} ({toll_detail or 'não cobrado'}); pedágio XML R$ {money(toll_actual)}.",
        ],
    }


def validate_cte_value(info, base_data, tables):
    nfs = get_nfs_from_info(info)
    nf = nfs[0] if nfs else ""
    result = {
        "nf": ", ".join(nfs) if nfs else nf,
        "base_frete": None,
        "percentual": None,
        "frete_minimo": None,
        "esperado": None,
        "diferenca": None,
        "tolerancia": None,
        "status": "PENDENTE",
        "detalhe": "",
        "partner_id": "",
        "tipo_cobranca": "",
        "regra_extra": "",
        "base_calculo": "",
        "modo_calculo": "",
        "peso_base_kg": None,
        "peso_xml_fonte": "",
        "peso_xml_todos": "",
        "regra_peso_especial": "",
        "limite_peso_especial_kg": None,
        "percentual_original_regra": None,
        "peso_reverso_kg": None,
        "dif_peso_kg": None,
        "auditoria_peso_status": "",
        "auditoria_peso_obs": "",
        "tonelagem_taxa": None,
        "frete_peso_xml": None,
        "frete_peso_calculado": None,
        "taxa_kg": None,
        "adicionais_xml": None,
        "valor_total_xml": None,
        "valor_comparado": None,
        "componente_comparado": "",
        "comparacao_fallback_total": False,
        "nfs_nao_encontradas": [],
        "nfs_incompativeis": [],
        "nfs_ignoradas": [],
        "validacao_com_nf_valida": False,
        "validacao_parcial": False,
        "trace": [],
        "base_candidates_summary": [],
    }
    trace = result["trace"]
    trace.append("Iniciando validação do XML.")
    if info.get("tipo") != "CT-e":
        result["status"] = "NÃO É CT-e"
        trace.append(f"Tipo identificado: {info.get('tipo', '-')}. Este item não será validado como CT-e.")
        return result
    trace.append(f"CT-e parceiro lido: número {info.get('numero', '-')}, série {info.get('serie', '-')}, valor R$ {money(info.get('valor', ''))}.")
    charge_type = detect_partner_charge_type(info)
    original_charge_type = charge_type
    if charge_type == "SUBSTITUICAO":
        trace.append("Tipo SUBSTITUIÇÃO identificado. Configuração atual: usar regra normal da cidade/tabela para conferir o valor, sem bloquear como EXTRA REVISAR.")
        charge_type = "NORMAL"
    result["tipo_cobranca"] = original_charge_type
    trace.append(f"Tipo de cobrança identificado pelo XML: {original_charge_type}.")
    if not nfs:
        result["status"] = "NF NÃO LIDA"
        trace.append("Nenhuma NF foi encontrada nos documentos originários do XML.")
        return result
    if len(nfs) == 1:
        trace.append(f"NF originária identificada no XML: {nf}.")
    else:
        trace.append(f"Múltiplas NFs originárias identificadas no XML: {', '.join(nfs)}.")
        trace.append("O programa irá somar os fretes base das NFs quando todas apontarem para a mesma rota. Se as rotas forem diferentes, exigirá revisão manual.")
    if not base_data:
        result["status"] = "BASE NÃO CARREGADA"
        trace.append("A base Rodovitor ainda não foi carregada.")
        return result

    early_pid = identify_partner(info, tables) if tables else None
    policy = xml_validation_partner_policy(early_pid)
    actual_xml_value = parse_number_br(info.get("valor", ""))

    base_rows = []
    statuses = []
    all_candidates = []
    missing_nfs = []
    blocked_nfs = []
    incompatible_nfs = []
    for one_nf in nfs:
        base_row, base_status, candidates = find_base_by_nf(
            base_data,
            one_nf,
            info,
            preferred_type=("COMPLEMENTAR" if original_charge_type == "COMPLEMENTAR" and policy.get("aceitar_complementar_exato_base") else ""),
            actual_value=actual_xml_value,
            tolerance=(tables.get("tolerance", 1.0) if tables else 1.0),
            allow_substitute=bool(policy.get("aceitar_substituto_com_vinculo_forte")),
            require_compatibility=(len(nfs) > 1),
        )
        statuses.append(base_status)
        all_candidates.extend(candidates)
        trace.append(f"Busca na base Rodovitor para NF {one_nf}: {len(candidates)} ocorrência(s) encontrada(s).")
        if candidates:
            normal_count = sum(1 for c in candidates if c.get("tipo_base") == "NORMAL")
            comp_count = sum(1 for c in candidates if c.get("tipo_base") == "COMPLEMENTAR")
            other_count = max(len(candidates) - normal_count - comp_count, 0)
            trace.append(f"NF {one_nf}: {normal_count} normal(is), {comp_count} complementar(es), {other_count} outra(s).")
        if not base_row:
            if base_status == "NF NÃO ENCONTRADA":
                missing_nfs.append(one_nf)
                trace.append(f"Nenhuma linha da base carregada/período atual possui a NF {one_nf}. Esta NF será tratada como fora da base/período, ou como NF acessória se houver outra NF válida no mesmo XML.")
                continue
            if base_status == "NF INCOMPATÍVEL":
                incompatible_nfs.append(one_nf)
                blocked_nfs.append((one_nf, base_status, len(candidates)))
                trace.append(f"A NF {one_nf} existe na base, mas o CNPJ/destinatário/rota não são compatíveis com este XML. A ocorrência foi descartada para evitar falsa múltipla rota ou falso OK.")
                continue
            blocked_nfs.append((one_nf, base_status, len(candidates)))
            if base_status == "ORIGINAL NÃO ENCONTRADO":
                trace.append(f"A NF {one_nf} existe na base, mas não foi encontrado CT-e NORMAL/ORIGINAL para usar como base de cálculo.")
            else:
                trace.append(f"A NF {one_nf} não pôde ser usada na base. Status: {base_status}.")
            continue
        trace.append(f"Linha base escolhida para NF {one_nf}: {candidate_summary(base_row)}.")
        base_rows.append(base_row)

    result["base_candidates_summary"] = [candidate_summary(c) for c in all_candidates[:30]]
    result["nfs_nao_encontradas"] = missing_nfs
    result["nfs_incompativeis"] = incompatible_nfs
    ignored_nfs = list(dict.fromkeys(
        list(missing_nfs)
        + list(incompatible_nfs)
        + [one_nf for one_nf, _status, _qtd in blocked_nfs if one_nf not in incompatible_nfs]
    ))
    result["nfs_ignoradas"] = ignored_nfs
    # Uma NF válida é suficiente para validar o CT-e quando o vínculo e o cálculo
    # são confiáveis. NFs extras ausentes/incompatíveis ficam somente no log.
    # Revisão é reservada para: nenhuma NF válida, NF ambígua ou conflito real
    # entre duas NFs válidas (rotas diferentes).
    result["validacao_com_nf_valida"] = bool(base_rows and ignored_nfs)
    result["validacao_parcial"] = False if base_rows else bool(ignored_nfs)

    if blocked_nfs and not base_rows:
        one_nf, base_status, qtd = blocked_nfs[0]
        result["status"] = base_status
        result["detalhe"] = f"NF {one_nf}: {qtd} ocorrência(s)" if qtd else f"NF {one_nf} não pôde ser usada na base Rodovitor"
        return result

    if not base_rows:
        result["status"] = status_nf_fora_base_periodo()
        result["detalhe"] = "Nenhuma NF do XML foi localizada na base carregada/período atual"
        trace.append(diagnostico_nf_fora_base_periodo(nfs))
        trace.append("O cálculo automático foi bloqueado porque não há linha de base para cruzar com o XML.")
        return result

    if missing_nfs:
        trace.append(f"NF(s) acessória(s) não localizada(s) e ignorada(s): {', '.join(missing_nfs)}.")
        trace.append("Como existe ao menos uma NF válida com vínculo confiável, isso não transforma o CT-e em validação parcial nem exige revisão por si só.")
    if blocked_nfs:
        ignored_detail = ", ".join(f"{one_nf} ({base_status})" for one_nf, base_status, _qtd in blocked_nfs)
        trace.append(f"NF(s) descartada(s) por falta de vínculo utilizável: {ignored_detail}.")
        trace.append("O cálculo seguirá somente com as NFs válidas. As descartadas serão registradas no log como NFs ignoradas.")

    usable_statuses = [s for s in statuses if s not in ("NF NÃO ENCONTRADA", "NF INCOMPATÍVEL")]
    base_status = summarize_base_statuses(usable_statuses or statuses)
    if len(base_rows) > 1 and not base_rows_have_same_route(base_rows):
        result["status"] = "MÚLTIPLAS ROTAS"
        result["base_frete"] = sum((r.get("valor_frete_planilha", 0.0) or r.get("valor_frete", 0.0)) for r in base_rows)
        result["detalhe"] = "NFs do XML apontam para rotas diferentes na base"
        trace.append("As NFs do mesmo XML foram localizadas, mas apontam para origem/destino diferentes na base. O cálculo automático foi bloqueado para evitar comparação errada.")
        return result

    result["base_frete"] = sum((r.get("valor_frete_planilha", 0.0) or r.get("valor_frete", 0.0)) for r in base_rows)
    base_row = base_rows[0]
    if result.get("validacao_parcial"):
        trace.append(f"Frete base será calculado com {len(base_rows)} NF(s) válida(s) encontrada(s) na base, de {len(nfs)} NF(s) lida(s) no XML.")
    fontes = sorted(set(r.get("fonte_frete", "PLANILHA") for r in base_rows))
    fonte_labels = {"PLANILHA": "REGISTRO SSW", "ORIGEM": "CTRC/CT-e ORIGEM"}
    detalhe_frete = f"{base_status}; base SSW Web; frete base: {'+'.join(fonte_labels.get(f, f) for f in fontes)}"
    if len(base_rows) > 1:
        trace.append(f"Frete base total somado das {len(base_rows)} NF(s): R$ {money(result['base_frete'])}.")
    if base_status == "NF AMBÍGUA":
        trace.append("Ao menos uma NF possui mais de um CT-e NORMAL e o desempate não foi conclusivo. O programa calcula com a melhor linha encontrada, mas mantém status para revisão.")
    elif base_status == "BASE OK - DESEMPATADA":
        trace.append("Ao menos uma NF tinha mais de um CT-e NORMAL, mas o sistema conseguiu desempatar usando CNPJ/cidade/UF/valor.")
    if any(r.get("fonte_frete") == "ORIGEM" for r in base_rows):
        trace.append("Uma ou mais linhas usaram Valor do Frete do CTRC Origem porque o frete da linha estava zerado/baixo ou era subcontratação.")

    pid = early_pid or (identify_partner(info, tables) if tables else None)
    result["partner_id"] = pid or ""
    if not tables:
        result["status"] = "TABELAS NÃO CARREGADAS"
        trace.append("A planilha de tabelas/cadastro dos parceiros ainda não foi carregada.")
        return result
    if not pid:
        result["status"] = "PARCEIRO SEM CADASTRO"
        result["detalhe"] = detalhe_frete
        emit = info.get("emit", {}) or {}
        trace.append(f"Não foi encontrado cadastro para o parceiro emitente. Nome XML: {info.get('emitente', '-')}; CNPJ XML: {emit.get('cnpjcpf', '-') }.")
        return result
    partner_name = (tables.get("partners", {}).get(pid, {}) or {}).get("name", "")
    trace.append(f"Parceiro identificado: {pid} - {partner_name or 'sem nome no cadastro'}.")
    if charge_type == "NORMAL":
        manual_charge = detect_partner_manual_extra(pid, info, tables)
        if manual_charge:
            charge_type = manual_charge
            original_charge_type = manual_charge
            result["tipo_cobranca"] = manual_charge
            trace.append(f"Operação especial identificada antes da tabela normal: {manual_charge}.")

    if charge_type == "ANULACAO":
        trace.append("O XML foi identificado como CT-e de ANULAÇÃO.")
        trace.append("O programa vai mostrar o cálculo normal/tabela apenas para conferência da anulação, sem bloquear como EXTRA REVISAR.")

    if original_charge_type == "COMPLEMENTAR" and policy.get("complementar_herda_regra_normal"):
        complementary_rows = [r for r in base_rows if r.get("tipo_base") == "COMPLEMENTAR"]
        if complementary_rows:
            expected = sum((r.get("valor_frete_planilha", 0.0) or r.get("valor_frete", 0.0)) for r in complementary_rows)
            actual = parse_number_br(info.get("valor", ""))
            tolerance = tables.get("tolerance", 1.0)
            diff = actual - expected
            result.update({
                "base_frete": expected,
                "base_calculo": "COMPLEMENTAR_EXATO_BASE",
                "modo_calculo": "COMPLEMENTAR_BASE",
                "valor_total_xml": actual,
                "valor_comparado": actual,
                "componente_comparado": "VALOR TOTAL XML",
                "esperado": expected,
                "diferenca": diff,
                "tolerancia": tolerance,
                "detalhe": f"{detalhe_frete}; complementar exato localizado na base por NF + valor",
            })
            trace.append("Política MB aplicada: CT-e complementar localizado exatamente na base por NF + valor + vínculo do XML.")
            trace.append(f"Valor complementar na base: R$ {money(expected)}. Valor XML: R$ {money(actual)}. Diferença: R$ {money(diff)}.")
            result["status"] = "OK COMPLEMENTAR" if abs(diff) <= tolerance else ("DIVERGENTE COMPLEMENTAR +" if diff > 0 else "DIVERGENTE COMPLEMENTAR -")
            return result
        trace.append("Política MB aplicada: não existe complementar exato na base; a cobrança complementar herdará a regra percentual normal da rota.")
        charge_type = "NORMAL"

    if charge_type != "NORMAL" and charge_type != "ANULACAO":
        trace.append(f"Como o XML parece ser {charge_type}, o programa procurou regra específica na aba REGRAS_EXTRAS antes de aplicar a tabela normal.")
        extra_rule = choose_extra_rule(pid, charge_type, tables, base_row)
        if not extra_rule:
            result["status"] = "EXTRA REVISAR"
            result["detalhe"] = f"{detalhe_frete}; cobrança {charge_type} sem regra específica cadastrada"
            trace.append("Nenhuma regra específica foi encontrada na aba REGRAS_EXTRAS para este tipo de cobrança. Bloqueado para revisão manual para evitar falso OK.")
            return result
        calc_base, calc_sources = sum_base_for_rule(base_rows, extra_rule.get("base_calculo", "ORIGINAL"))
        result["base_frete"] = calc_base
        result["base_calculo"] = normalize_base_calculo(extra_rule.get("base_calculo", "ORIGINAL"))
        expected = calculate_extra_expected(result["base_frete"], extra_rule)
        actual = parse_number_br(info.get("valor", ""))
        diff = actual - expected
        result["percentual"] = extra_rule.get("percent", 0.0) or 0.0
        result["frete_minimo"] = extra_rule.get("minimum", 0.0) or 0.0
        result["esperado"] = expected
        result["diferenca"] = diff
        result["regra_extra"] = extra_rule.get("tipo_extra", "") or charge_type
        result["detalhe"] = f"{detalhe_frete}; regra extra: {extra_rule.get('tipo_extra', charge_type)}"
        tolerance = tables.get("tolerance", 1.0)
        result["tolerancia"] = tolerance
        trace.append(f"Regra extra aplicada: {extra_rule.get('tipo_extra', charge_type)}; fonte {extra_rule.get('source', 'REGRAS_EXTRAS')}; base de cálculo {result.get('base_calculo', '-')}; fonte efetiva {'+'.join(calc_sources)}.")
        trace.append(f"Parâmetros da regra extra: percentual {fmt_percent(result['percentual']) or '-'}; valor fixo R$ {money(extra_rule.get('valor_fixo', 0.0))}; mínimo R$ {money(result['frete_minimo'])}.")
        review_status = norm_text(extra_rule.get("status_revisao", ""))
        manual_review = ("MANUAL" in review_status or review_status == "PENDENTE" or ("REVIS" in review_status and review_status != "REVISAR_OK"))
        if manual_review or expected <= 0:
            result["status"] = "EXTRA REVISAR"
            trace.append("A cobrança extra foi corretamente separada do frete normal e exige conferência manual; nenhuma aprovação automática foi realizada.")
            return result
        trace.append(f"Valor esperado pela regra extra: R$ {money(expected)}. Valor XML: R$ {money(actual)}. Diferença: R$ {money(diff)}. Tolerância: R$ {money(tolerance)}.")
        if abs(diff) <= tolerance:
            result["status"] = "OK EXTRA"
            trace.append("Diferença dentro da tolerância. Validação de cobrança extra OK.")
        elif actual > expected:
            result["status"] = "DIVERGENTE EXTRA +"
            trace.append("Valor do XML está acima do esperado pela regra extra.")
        else:
            result["status"] = "DIVERGENTE EXTRA -"
            trace.append("Valor do XML está abaixo do esperado pela regra extra.")
        return result

    rule = choose_partner_rule(pid, base_row, tables)
    if rule and rule.get("source") == "REGIOES_FALLBACK_INTERIOR_AP":
        trace.append(f"Regra regional MB aplicada: destino {base_row.get('destino_cidade', '-')}/{base_row.get('destino_uf', '-')} classificado como interior do Amapá. Percentual e mínimo vieram da região MB INTERIORES-AP cadastrada.")
    if not rule:
        fallback = validate_rodotec_components_fallback(info, pid, tables, base_row, tables.get("tolerance", 1.0))
        if fallback:
            result.update({key: value for key, value in fallback.items() if key != "trace_extra"})
            result["detalhe"] = f"{detalhe_frete}; {fallback.get('detalhe', '')}"
            trace.extend(fallback.get("trace_extra", []))
            return result
        result["status"] = "REGRA NÃO ENCONTRADA"
        result["detalhe"] = detalhe_frete
        trace.append("Parceiro existe no cadastro, mas nenhuma regra bateu com origem/destino/região da base.")
        trace.append(f"Origem base: {base_row.get('origem_cidade', '-')}/{base_row.get('origem_uf', '-')}; destino base: {base_row.get('destino_cidade', '-')}/{base_row.get('destino_uf', '-')}.")
        reg_count = sum(1 for reg in tables.get("regions", []) if reg.get("partner_id") == pid)
        trace.append(f"Regiões cadastradas para o parceiro {pid}: {reg_count}. Se a cidade existir na aba REGIOES, o programa deve aplicar a regra por cidade.")
        return result
    peso_rule_kg, peso_rule_source = peso_base_kg_from_info(info)
    special_rule = choose_weight_special_rule(pid, base_row, tables, peso_rule_kg)
    if special_rule:
        original_percent = rule.get("percent", 0.0) or 0.0
        result["regra_peso_especial"] = "SIM"
        result["limite_peso_especial_kg"] = special_rule.get("peso_min_kg")
        result["percentual_original_regra"] = original_percent
        result["peso_base_kg"] = peso_rule_kg
        result["peso_xml_fonte"] = peso_rule_source
        result["peso_xml_todos"] = format_peso_xml_debug(info)
        trace.append(f"Regra especial por peso encontrada: peso {money(peso_rule_kg)} kg acima de {money(special_rule.get('peso_min_kg') or 0)} kg.")
        trace.append(f"Percentual original da regra normal seria {fmt_percent(original_percent) or '-'}; percentual especial aplicado será {fmt_percent(special_rule.get('percent', 0.0)) or '-'}; base {special_rule.get('base_calculo', '-')}; mínimo R$ {money(special_rule.get('minimum', 0.0))}.")
        if special_rule.get("observacao"):
            trace.append(f"Observação da regra especial: {special_rule.get('observacao')}.")
        rule = special_rule

    percent = rule.get("percent", 0.0)
    minimum = rule.get("minimum", 0.0)
    if percent <= 0 and minimum <= 0:
        result["status"] = "REGRA SEM VALOR"
        result["detalhe"] = detalhe_frete
        trace.append("A regra encontrada não possui percentual nem frete mínimo. O cálculo foi bloqueado para evitar falso OK com valor esperado zero.")
        trace.append(f"Regra encontrada: origem {rule.get('origem_cidade') or '*'} / {rule.get('origem_uf') or '*'} → destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
        return result

    if should_use_frete_peso(rule, info):
        ton_rate = rule.get("ton_rate", 0.0) or 0.0
        peso_kg, peso_source = peso_base_kg_from_info(info)
        frete_peso_xml, frete_peso_found = component_value(info, "FRETE PESO")
        adicionais_xml, adicionais_found = non_frete_peso_components_value(info)
        actual, comp_label, fallback_total, comp_found, total_xml = comparison_value_from_xml(info, "FRETE_PESO")
        tolerance = tables.get("tolerance", 1.0)

        result["modo_calculo"] = "FRETE_PESO"
        result["base_calculo"] = "FRETE_PESO"
        result["peso_base_kg"] = peso_kg
        result["peso_xml_fonte"] = peso_source
        result["peso_xml_todos"] = format_peso_xml_debug(info)
        result["tonelagem_taxa"] = ton_rate
        result["taxa_kg"] = ton_rate / 1000.0 if ton_rate else None
        result["frete_peso_xml"] = frete_peso_xml
        result["adicionais_xml"] = adicionais_xml
        result["valor_total_xml"] = total_xml
        result["valor_comparado"] = actual
        result["componente_comparado"] = comp_label
        result["comparacao_fallback_total"] = fallback_total
        result["percentual"] = None
        result["frete_minimo"] = minimum
        result["tolerancia"] = tolerance

        if ton_rate <= 0 or peso_kg <= 0:
            result["status"] = "REGRA FRETE PESO SEM DADOS"
            result["detalhe"] = f"{detalhe_frete}; regra: {rule.get('source', 'REGIOES')} {rule.get('regiao', '')}; falta tonelagem ou peso"
            trace.append("A regra indica cálculo por FRETE PESO, mas faltou tonelagem R$/Ton ou peso base no XML.")
            trace.append(f"Peso base lido: {money(peso_kg)} kg; tonelagem: R$ {money(ton_rate)}/ton.")
            return result

        frete_peso_calc = (peso_kg / 1000.0) * ton_rate
        frete_peso_esperado = max(frete_peso_calc, minimum)
        minimum_applied = bool(minimum and frete_peso_esperado == minimum and minimum > frete_peso_calc)
        expected = frete_peso_esperado
        diff = actual - expected

        taxa_kg = ton_rate / 1000.0 if ton_rate else 0.0
        peso_reverso = None
        dif_peso = None
        audit_status = ""
        audit_obs = ""
        if minimum_applied:
            audit_status = "FRETE MÍNIMO"
            audit_obs = "Frete mínimo aplicado; o valor cobrado não permite conferir o peso real por cálculo reverso."
        elif fallback_total:
            audit_status = "SEM COMPONENTE FRETE PESO"
            audit_obs = "O XML não trouxe componente FRETE PESO claro; foi usado fallback do valor total."
        elif taxa_kg > 0 and actual > 0:
            peso_reverso = actual / taxa_kg
            dif_peso = peso_kg - peso_reverso
            if abs(dif_peso) <= 0.05:
                audit_status = "PESO OK"
                audit_obs = "Peso do XML bate com o cálculo reverso do componente FRETE PESO."
            else:
                audit_status = "CONFERIR PESO"
                audit_obs = "Peso usado no XML não bate com o peso reverso calculado pelo FRETE PESO."
        else:
            audit_status = "SEM AUDITORIA"
            audit_obs = "Faltou taxa por kg ou valor comparado para auditar o peso."

        result["frete_peso_calculado"] = frete_peso_esperado
        result["peso_reverso_kg"] = peso_reverso
        result["dif_peso_kg"] = dif_peso
        result["auditoria_peso_status"] = audit_status
        result["auditoria_peso_obs"] = audit_obs
        result["esperado"] = expected
        result["diferenca"] = diff
        result["base_frete"] = result.get("base_frete")
        min_label = "; frete mínimo aplicado" if minimum_applied else ""
        result["detalhe"] = f"{detalhe_frete}; cálculo FRETE PESO; {rule.get('source', 'REGIOES')} {rule.get('regiao', '')}{min_label}".strip()

        trace.append(f"Regra aplicada: destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
        trace.append(f"Modo de cálculo detectado: FRETE PESO por kg/tonelagem.")
        trace.append(f"Peso usado: {money(peso_kg)} kg ({peso_source or 'sem fonte'}). Tonelagem da tabela: R$ {money(ton_rate)} por tonelada.")
        trace.append(f"Base visual do peso: R$ {money(ton_rate / 1000.0)} por kg ({money(ton_rate)} ÷ 1000).")
        trace.append(f"Cálculo frete peso: {money(peso_kg)} kg × R$ {money(ton_rate / 1000.0)}/kg = R$ {money(frete_peso_calc)}.")
        if result.get("peso_xml_todos"):
            trace.append(f"Pesos encontrados no XML: {result.get('peso_xml_todos')}.")
        if result.get("peso_reverso_kg") is not None:
            trace.append(f"Auditoria de peso: peso reverso = R$ {money(actual)} ÷ R$ {money(ton_rate / 1000.0)}/kg = {money(result.get('peso_reverso_kg'))} kg; diferença = {money(result.get('dif_peso_kg'))} kg; status {result.get('auditoria_peso_status')}.")
        else:
            trace.append(f"Auditoria de peso: {result.get('auditoria_peso_status') or '-'} - {result.get('auditoria_peso_obs') or '-'}")
        if frete_peso_found:
            trace.append("Componente FRETE PESO no XML: " + ", ".join(f"{n or '-'} R$ {money(v)}" for n, v in frete_peso_found))
        if minimum_applied:
            trace.append(f"Frete mínimo aplicado ao FRETE PESO porque R$ {money(minimum)} é maior que R$ {money(frete_peso_calc)}.")
        if adicionais_found:
            trace.append("Componentes adicionais do XML encontrados, mas NÃO entram nesta comparação principal: " + ", ".join(f"{n or '-'} R$ {money(v)}" for n, v in adicionais_found) + f" | Total adicionais informativo: R$ {money(adicionais_xml)}.")
        else:
            trace.append("Nenhum componente adicional ao FRETE PESO foi encontrado.")
        trace.append(f"Componente comparado do XML: {comp_label} = R$ {money(actual)}.")
        if fallback_total:
            trace.append("Atenção: componente principal não encontrado; o programa usou o VALOR TOTAL DO SERVIÇO como fallback.")
        trace.append(f"Valor esperado para comparação: R$ {money(expected)}. Diferença: R$ {money(diff)}. Tolerância: R$ {money(tolerance)}.")

        partial_suffix = ""
        min_suffix = " FRETE MÍNIMO" if minimum_applied else ""
        anul_suffix = " ANULAÇÃO" if charge_type == "ANULACAO" else ""
        if "PENDENTE" in rule.get("status_revisao", ""):
            result["status"] = "REGRA PENDENTE" + partial_suffix + anul_suffix
            trace.append("A regra usada está marcada como PENDENTE/REVISAR na planilha de tabelas.")
        elif base_status == "NF AMBÍGUA":
            result["status"] = "NF AMBÍGUA" + partial_suffix + anul_suffix
            trace.append("Mesmo com cálculo feito, a NF segue ambígua.")
        elif abs(diff) <= tolerance:
            result["status"] = ("OK FRETE PESO" + min_suffix + partial_suffix + anul_suffix).strip()
            if result.get("nfs_ignoradas"):
                trace.append("Diferença dentro da tolerância. Validação OK por FRETE PESO usando a(s) NF(s) válida(s); NFs sem vínculo confiável foram apenas ignoradas e registradas no log.")
            else:
                trace.append("Diferença dentro da tolerância. Validação OK por FRETE PESO.")
        elif actual > expected:
            result["status"] = ("DIVERGENTE FRETE PESO +" + min_suffix + partial_suffix + anul_suffix).strip()
            trace.append("Valor do XML está acima do esperado pelo cálculo de FRETE PESO.")
        else:
            result["status"] = ("DIVERGENTE FRETE PESO -" + min_suffix + partial_suffix + anul_suffix).strip()
            trace.append("Valor do XML está abaixo do esperado pelo cálculo de FRETE PESO.")
        if charge_type == "ANULACAO":
            trace.append("Observação: por ser ANULAÇÃO, este cálculo é exibido para entendimento/conferência do documento de anulação.")
        return result


    calc_base, calc_sources = sum_base_for_rule(base_rows, rule.get("base_calculo", "ORIGINAL"))
    result["base_frete"] = calc_base
    result["base_calculo"] = normalize_base_calculo(rule.get("base_calculo", "ORIGINAL"))
    if rule.get("modo_calculo"):
        result["modo_calculo"] = rule.get("modo_calculo")
    expected_percent = result["base_frete"] * percent
    expected_base = max(expected_percent, minimum)
    toll_rule_expected, toll_detail = rule_pedagio_expected(rule, info)
    actual, comp_label, fallback_total, comp_found, total_xml = comparison_value_from_xml(info, "FRETE_VALOR")
    toll_xml_separate, toll_xml_items = component_value(info, "PEDAGIO", "PEDÁGIO")
    toll_expected = toll_rule_expected
    if toll_xml_separate > 0 and not fallback_total:
        # FRETE VALOR é comparado isoladamente; um PEDÁGIO em componente separado
        # não pode ser somado de novo ao valor esperado do frete.
        toll_expected = 0.0
    expected = expected_base + toll_expected
    diff = actual - expected
    minimum_applied = bool(minimum and expected_base == minimum and minimum > expected_percent)
    result["valor_total_xml"] = total_xml
    result["valor_comparado"] = actual
    result["componente_comparado"] = comp_label
    result["comparacao_fallback_total"] = fallback_total
    result["percentual"] = percent
    result["frete_minimo"] = minimum
    result["esperado"] = expected
    result["pedagio_esperado"] = toll_expected
    result["pedagio_regra"] = toll_rule_expected
    result["pedagio_xml_separado"] = toll_xml_separate
    result["pedagio_detalhe"] = toll_detail
    result["diferenca"] = diff
    min_label = "; frete mínimo aplicado" if minimum_applied else ""
    result["detalhe"] = f"{detalhe_frete}; base cálculo: {result['base_calculo']}; regra: {rule.get('source', 'REGRAS_PERCENTUAL')} {rule.get('regiao', '')}{min_label}".strip()
    tolerance = tables.get("tolerance", 1.0)
    result["tolerancia"] = tolerance
    trace.append(f"Regra aplicada: origem {rule.get('origem_cidade') or '*'} / {rule.get('origem_uf') or '*'} → destino {rule.get('destino_cidade') or '*'} / {rule.get('destino_uf') or '*'}; região {rule.get('regiao') or '-'}; fonte {rule.get('source', '-')}.")
    trace.append(f"Percentual da regra: {fmt_percent(percent) or '-'}; frete mínimo: R$ {money(minimum)}; base de cálculo: {result['base_calculo']}; fonte efetiva {'+'.join(calc_sources)}.")
    if result["base_calculo"] == "SEM_ICMS":
        trace.append("Este parceiro/regra está configurado para calcular sobre o Valor do Frete sem ICMS da base Rodovitor.")
    trace.append(f"Cálculo percentual: R$ {money(result['base_frete'])} × {fmt_percent(percent)} = R$ {money(expected_percent)}.")
    if toll_xml_separate > 0 and toll_rule_expected > 0 and toll_expected == 0:
        trace.append(f"Pedágio separado no XML auditado: R$ {money(toll_xml_separate)}. Ele não foi somado ao FRETE VALOR esperado para evitar dupla cobrança ({toll_detail}).")
    elif toll_expected > 0:
        trace.append(f"Pedágio da regra acrescentado ao FRETE VALOR esperado: R$ {money(toll_expected)} ({toll_detail}).")
    if minimum_applied:
        trace.append(f"Frete mínimo aplicado porque R$ {money(minimum)} é maior que o cálculo percentual.")
    else:
        trace.append("Frete mínimo não superou o cálculo percentual.")
    if comp_found:
        trace.append(f"Componente comparado do XML: {comp_label} = R$ {money(actual)} ({format_component_list(comp_found)}).")
    else:
        trace.append(f"Componente comparado do XML: {comp_label} = R$ {money(actual)}.")
    if fallback_total:
        trace.append("Atenção: FRETE VALOR/FRETE PESO não foi encontrado nos componentes; o programa usou o VALOR TOTAL DO SERVIÇO como fallback.")
    trace.append(f"Valor esperado para comparação: R$ {money(expected)}. Diferença: R$ {money(diff)}. Tolerância: R$ {money(tolerance)}.")

    partial_suffix = ""
    anul_suffix = " ANULAÇÃO" if charge_type == "ANULACAO" else ""
    if "PENDENTE" in rule.get("status_revisao", ""):
        result["status"] = "REGRA PENDENTE" + partial_suffix + anul_suffix
        trace.append("A regra usada está marcada como PENDENTE/REVISAR na planilha de tabelas, então o resultado precisa de conferência manual.")
    elif base_status == "NF AMBÍGUA":
        result["status"] = "NF AMBÍGUA" + partial_suffix + anul_suffix
        trace.append("Mesmo com cálculo feito, a NF segue ambígua porque há mais de um CT-e normal na base.")
    elif abs(diff) <= tolerance:
        result["status"] = (("OK FRETE MÍNIMO" if minimum_applied else "OK") + partial_suffix + anul_suffix).strip()
        if result.get("nfs_ignoradas"):
            trace.append("Diferença dentro da tolerância. Validação OK usando a(s) NF(s) válida(s); NFs sem vínculo confiável foram apenas ignoradas e registradas no log.")
        elif minimum_applied:
            trace.append("Diferença dentro da tolerância. Validação OK com frete mínimo aplicado.")
        else:
            trace.append("Diferença dentro da tolerância. Validação OK.")
    elif actual > expected:
        result["status"] = (("DIVERGENTE FRETE MÍNIMO +" if minimum_applied else "DIVERGENTE +") + partial_suffix + anul_suffix).strip()
        if minimum_applied:
            trace.append("Valor do XML está acima do frete mínimo esperado. Conferir se há ICMS, taxa ou regra especial não cadastrada.")
        else:
            trace.append("Valor do XML está acima do esperado. Possível cobrança maior, complementar ou extra não cadastrado.")
    else:
        result["status"] = (("DIVERGENTE FRETE MÍNIMO -" if minimum_applied else "DIVERGENTE -") + partial_suffix + anul_suffix).strip()
        if minimum_applied:
            trace.append("Valor do XML está abaixo do frete mínimo esperado. Conferir tabela/regra/parceiro.")
        else:
            trace.append("Valor do XML está abaixo do esperado. Conferir tabela/regra/parceiro.")
    if charge_type == "ANULACAO":
        trace.append("Observação: por ser ANULAÇÃO, este cálculo é exibido para entendimento/conferência do documento de anulação.")
    return result


EXPORTED_FUNCTIONS = ('identify_partner', 'detect_partner_charge_type', 'extra_matches_charge_type', 'extra_condition_matches', 'choose_extra_rule', 'calculate_extra_expected', 'get_nfs_from_info', 'get_nf_from_info', 'is_generic_destination', 'rule_matches_location', 'choose_partner_rule', 'candidate_summary', 'special_weight_city_match', 'choose_weight_special_rule', 'normalize_base_calculo', 'base_value_for_rule', 'sum_base_for_rule', 'component_value', 'total_components_value', 'non_frete_peso_components_value', 'peso_base_kg_from_info', 'peso_xml_debug_from_info', 'format_peso_xml_debug', 'should_use_frete_peso', 'component_values_by_keywords', 'comparison_value_from_xml', 'format_component_list', 'validation_report_text', 'status_nf_fora_base_periodo', 'diagnostico_nf_fora_base_periodo', 'summarize_base_statuses', 'base_rows_have_same_route', 'detect_partner_manual_extra', 'rule_pedagio_expected', 'validate_rodotec_components_fallback', 'validate_cte_value')
EXTRACTION_VERSION = "2.7.0-rc17"


def install_commercial_validation_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    installed = install_rebound_functions(globals(), target_globals, EXPORTED_FUNCTIONS)
    state = {
        "version": EXTRACTION_VERSION,
        "module": __name__,
        "functions": list(installed),
        "active": True,
        "legacy_orchestrator": "validate_cte_value",
    }
    target_globals["CENTRAL_CTE_COMMERCIAL_VALIDATION_COMPAT_STATE"] = state
    return state


__all__ = [
    "install_commercial_validation_compat",
    "EXPORTED_FUNCTIONS",
]
