from __future__ import annotations

"""Caminhos, abertura segura, logs e informação complementar extraídos do núcleo legado."""

from typing import Any, MutableMapping

from .function_rebinder import install_rebound_functions

CENTRAL_CTE_COMPLEMENTARY_INFO_KEY = "informacao_complementar_impressao"

CENTRAL_CTE_COMPLEMENTARY_INFO_META_KEY = "informacao_complementar_impressao_meta"

CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS = 600

_CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE = None

_CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME = None

ASSET_B64 = {
    "LOGO_RODOVITOR": "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",
    "TRUCK_ROUTE": "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",
    "ICON_ADD": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAAg0lEQVR4nO3XwQmAMBAAQSM+Lc4SLM0SLM5/fCtoIHgrBzsFhOUI5FJqrUNG498BvQynGU4znDZFHTwv2+WBOPa1fHl+2okbTjOcZjjNcJrhNMNppfXLv295pLeNMu3EDac173gvf0APDKcZTjOcZjjNcFra8LAlK1raiRtOM5yWNvwEFnQYTynSzIQAAAAASUVORK5CYII=",
    "ICON_FOLDER": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAAnElEQVR4nO3XsQ2AIBRFUTGWDucIjuYIDmePrbEAPwkXX/JOT3LzRYWUc54UzaMDWjmc5nCaw2kOpy3RBet2hH+117mn6Joa2YnLhoe3ylNpC7RsqQjZiafasbb35EpKT1R24rLhoZezx/f47evWlJ24w2kOpzmc5nCaw2kOp8mGh461I29Db7ITlw2vXpb/SnbiDqc5nOZwmsNpN2BsG1QxOYbCAAAAAElFTkSuQmCC",
    "ICON_EYE": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAA2ElEQVR4nO2XQQ6DMAwEk6pHHtcn9Gk8oY/jnp4qRSgktmM2pOycg3dAYJuYUgoz8hgtYIXiaCiOhuJoKI6G4mgojubpWWx5rc1Vc/u8o0dW7FlrJaItrDdiEvcQ3qO9AbV4TVoS3nv9D5V4KbQU5n2uhFh8H3IUYHmi0to5IvG8cK1ob1eR5oQg6OPSDxF9TjWAvHqwR/1pJ+c9xM8YPNb6TXHpe4c+9999vCZ1+clZC9OEDtlVJOFWTt8Oc6bbx4+Y5g9oJPeYnFeC4mgojobiaCiOhuJovs8rpif1TxqlAAAAAElFTkSuQmCC",
    "ICON_CODE": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAABK0lEQVR4nO2YTQ7CQAiFHePSw3kEj+YRPJz7cVXTTEbg8RiaJrw1ha+En9LWe7+cUdejAbwq8GwVeLYKPFsFnq3bSuf3x+u3lj/vZ4v0HZLxPeAK+5lo8A3CCoPa/xMFPgbXYFB7SW7wWdB9Hc/qe1bnXngXuAYtKQoeBmegJXsUnm5O75hjxyMEPmaFDT4+j2TdDB4xeyPjmMDRukY2prfeVfCIZtTkgRfBM6AlvxK8CD46WwXtiQdlfHWDIvGgjGvOGKFlqTZnBrynl0zjEIFHjwfvADAvoNWNicaBVj6zomdiPiHCLqCs5zbB4BHNGrHYXBln4KO2cWN+7Euw1pfzNj1V4+zlw0yqsAsIvTlTLyANZpX9TFSNH6nT/vQs8GwVeLYKPFunBf8CWZLPTtSqBaYAAAAASUVORK5CYII=",
    "ICON_TRASH": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAArUlEQVR4nO2YwQ2AIBAExViBb4qg/yoswjct4IvEl3jHZckmO18SnawbOUittY2RfbWAF4mjkTgaiaOROJoj4iE1F/P2e95XmnknbeISR5Os06Gnz3+x9J42cVpxc1U6kZXx/BppEw/ZgDyJzX6x0MRrLu1LaLRugbYqEkcjcTQSRyNxNBJHQyseMh12RlPi7JXEm2X3KrPQVoVW3H3mXA1t4hJHI3E0EkdDK/4A/XkrAMLc7B4AAAAASUVORK5CYII=",
    "ICON_BROOM": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAABJUlEQVR4nO2ZSw6DMAxEJ1V37d3KEbhZOQKHY++uUCMUiknsMZXypCwICL1YyYRPEhH8I7dogVq6OJsuzqaLa3kOk0n+UsVXaQv5xNqA9mSXeUw196NU3FoaCFycLdIAQbxU7VZpwFncKkFKuIl7zOscF3FvacBBnCENkFLFWhowFvdKkBJm4kxpwEjcM/b2aBZnLcYtTeJR0kCDeKQ0YJwqLGmgUpydICVOi0ckSIlT4tHzOqfq1S0fQIQ0AEBEVO3xesuvY3ZTV/wSVc4wSxU2d81FpWqvfVHVr96AlnlMyzymqOo375yrPH0A2kTRpAgzacyfVVjVp3+esOIwVY4EtudZKaOKQ+A7DUr9tko61OLPYZIr7JgrtO/j1vR/QGy6OJsPdwWZEc2zhp8AAAAASUVORK5CYII=",
    "ICON_PRINT": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAAx0lEQVR4nO2XvQ2FMAwGCaJkOEZgtDfCG44+tClAxHawOclXE3T68A8ptdaJyBwtoCXFvUlxb1Lcm0V6YN1+rw3+47+X3mexiWPFxaXSIvm0d2hLD5t4inuDFTc155sz/Qls4qXnBhSR7NOoxSaOFRc354hteYekJE1TZQTIlW9pemyNp7gGS6OHN2cr7zJVRm5TTfLYGv/ELV/zTmziWPGu39or2s+raS7reWziWPEhCyjihoRNHCuunirRYBNPcW9S3Bus+AnzIjpGKKH5fAAAAABJRU5ErkJggg==",
    "ICON_PRINT_CHECK": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAA90lEQVR4nO2ZSQ7DIAxFoeoyh+sRcrQeIYfLnqwsIRIGE/CA/LZR0ePzHRTVhxCcRj7cAr2YODUmTo2JU2Pi1HxzD7bff9iVeh67H7UWkBWfxZtA4gDWq0pMz1GPrNoT5FWJaQkkF8DaVZl97D2sk/iMdGFN7JCXXNQmLla8dvLF4RxxVc8abPbEnzbWsllWcRDMiZZOnD1xoLaJFDHiKbX5YhVP5TCDXL3yOa77lrdZMXEK6d5XroiOg/x57L51IyLEncMnf+t4aWAwi/f+rhXWL6A3MySmKljUipNXZVTfUeKSvj3VVkWtuLe/C4kxcWpMnBq14hed2lpZ2VOeWgAAAABJRU5ErkJggg==",
    "ICON_DOC": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAAl0lEQVR4nO2ZMQqAMBAEjVj6OJ/g03yCj7OPlWAjeolZWZypDQyXY4qYcs6dI/3XAqUgrgZxNbbiQ/TAOC3N+rmtc3r6re3EbcXDq3ImcrVXlK6e7cQRV4O4mqqqHJSWoaZK/574Gz2PYjtxxNVQFTVURQ3iaqiKGqqiBnE1VEWNbVWqxFu+3N5huyq24on/nGIQV4O4mh1lNCh6wRmfQAAAAABJRU5ErkJggg==",
    "ICON_SELECT": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAA7ElEQVR4nO2ZMQ7CMAxFE8TI4TgCR+MIHI49TJWiqCXut/1TS35Llwyvxv12S22tlYjcVgugpDibFGeT4mxSnM1devDxfNNG7PfzqrMzYSseVlzcKj2Sn/IsZ1sxbMVTHEGTVMvEN2lUfon4KIvIX6LHkZSii4/VRaOVKm65NtDE96Q1g8xEHKmkdvqqxSWxZtXXPSpxSax5rcMq8b3K9aLWfd2jbpWZ/OwsisnDKZG3XoXN4tBjR/+HaY4fyXvclPkA2iTHqzUuk9NbupSLbIcI0Msy8xvLEWErHla85p9XZFKcTYqzSXE2YcV/MIdcVuFfSesAAAAASUVORK5CYII=",
    "ICON_MONEY": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAACoklEQVR4nO3YT4geNRjH8c92qxj0IuhFRFhkoXhQPIm6xIMgqFil4llYe+hZVJC5KCXgQRApIq2IoOLJSw9V0IsEV6Es2mqhoEXUIv6pBaHVqMi+Hmaq02Ff3Xd2O6UwX3iZ5MmT5JcnycPMOzeZTFyKbLvYAvoyCh+aUfjQjMKHZhQ+NKPwoRmFD832aQ2hijtwfJ2mCX7DSXyIfSXlz/5volDFozhTUl7qqfU8+kR8DldiB3ZjNVTx3gs011SmRnwd9peU94QqXoWH8Lp6EZfhRbzb7RCqeB8ew624AdtCFU/gCN7BwZLy6T7CZ45CSflsSflNfNAyL4YqXtMR/RwOYRcWMK9e6I14GK82v15sZvu+69TnzxWa+/FUUz2NJXyOj9SRvwcv4ae+k89yVLpc3yqfKin/2KovqaMLH5eUV0IV1zApKZ9UX+z3NzH37MJbZ/yuljl13H5vle8OVVxGwNlZ55vG3LSP5f9Ih22+x96S8sudvotN3/mO/59YxQreKikf6aEZm09R2/FX11hS/hLPruN/Oe7Ak/g0VLG7UxtmFuH71RG8CYcb27U4EKq4q+tcUt6rPuuv4espYz4dqnjbDBr+YaaIl5TXSsrH8Qj+aDXtC1UM6/ivlJSXS8oLOIov1Dvxa+Myh3jBhbcEfev8HHwdHt1A11Ml5WfwRst2dR8Nm0mHL2CPfxf/eKjigZLyWqjibjyAt/EJvjnXKVRxAbe3xjmsB70vZ0n5BA62TIt4sClfgZ3q14JjOIObcSe+wi2N36HOGBtms1nl+U79ieb5Cu5vnqv4WX2eJ/gB72EZO0vKvf68nJrHt5pQxWP45WK+1vZlbSsHG1L4lm7tYEdlq7lkvzlH4UMzCh+aUfjQjMKHZhQ+NKPwofkbbx22ln4FiHUAAAAASUVORK5CYII=",
    "APP_ICON": "iVBORw0KGgoAAAANSUhEUgAAAC4AAAAuCAYAAABXuSs3AAAAyElEQVR4nO2XvQ2FMAwGCWICaoZg/yneEK9mhdCmABHbweYkX03Q6cM/pNRaJyJztICWFPcmxb1JcW8W6YFj218b/Ov/V3qfxSaOFReXSovk096hLT1s4inuDVbc1JxvzvQnsImXnhtQRLJPoxabOFZc3JwjtuUdkpI0TZURIFe+pemxNZ7iGiyNHt6crbzLVBm5TTXJY2v8E7d8zTuxiWPFu35rr2g/r6a5rOexiWPFhyygiBsSNnGsuHqqRINNPMW9SXFvsOInA2A7fJUeMC8AAAAASUVORK5CYII=",
}

def resource_path(relative_path):
    """Resolve recursos no executável e em qualquer layout da distribuição.

    As funções de compatibilidade podem ser religadas ao namespace do motor
    principal. Por isso ``__file__`` nem sempre aponta para este módulo. A busca
    percorre os ancestrais do arquivo ativo e o diretório corrente até encontrar
    o recurso solicitado.
    """
    relative = Path(relative_path)
    candidates = []
    try:
        candidates.append(Path(sys._MEIPASS))  # type: ignore[name-defined]
    except Exception:
        pass
    try:
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    try:
        active_file = Path(__file__).resolve()
        candidates.extend(active_file.parents)
    except Exception:
        pass
    try:
        cwd = Path.cwd().resolve()
        candidates.extend((cwd, *cwd.parents))
    except Exception:
        pass
    seen = set()
    for base_path in candidates:
        key = str(base_path)
        if key in seen:
            continue
        seen.add(key)
        candidate = base_path / relative
        if candidate.exists():
            return candidate
    fallback = candidates[0] if candidates else Path.cwd()
    return fallback / relative

def app_runtime_dir():
    """Pasta onde ficam bases, tabelas, relatórios e arquivos de trabalho."""
    try:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
    except Exception:
        pass
    return Path(__file__).resolve().parent

def safe_open_folder(path):
    path = Path(path)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.as_uri())
    except Exception:
        webbrowser.open(str(path))

def safe_open_file(path):
    path = Path(path)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.as_uri())
    except Exception:
        webbrowser.open(str(path))

def ensure_work_folders():
    base = app_runtime_dir()
    folders = {
        "raiz": base,
        "bases": base / "bases",
        "tabelas": base / "tabelas",
        "xmls": base / "xmls",
        "relatorios": base / "relatorios",
        "logs": base / "logs",
        "sessoes": base / "sessoes",
        "cache": base / "cache",
        "saida_html": base / "saida_html",
    }
    for key, folder in folders.items():
        if key != "raiz":
            folder.mkdir(parents=True, exist_ok=True)

    origem_modelo = resource_path("modelos/cadastro_tabelas_parceiros_v1.xlsx")
    destino_modelo = folders["tabelas"] / "cadastro_tabelas_parceiros.xlsx"
    if origem_modelo.exists() and not destino_modelo.exists():
        try:
            shutil.copy2(origem_modelo, destino_modelo)
        except Exception:
            pass
    return folders

def _central_cte_is_cte_info(info):
    try:
        value = norm_text((info or {}).get("tipo", "")) if "norm_text" in globals() else str((info or {}).get("tipo", "")).upper()
        return value.replace("-", "").replace(" ", "") in {"CTE", "CT"}
    except Exception:
        return False

def _central_cte_clean_complementary_information(text, limit=True):
    value = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in value.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    value = "\n".join(lines).strip()
    if limit:
        value = value[:CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS]
    return value

def _central_cte_complementary_store_path():
    folder = app_runtime_dir() / "sessoes"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "informacoes_complementares_cte.json"

def _central_cte_info_identity(info):
    info = info or {}
    chave = re.sub(r"\D", "", str(info.get("chave") or info.get("chave_acesso") or ""))
    if len(chave) == 44:
        return f"chave:{chave}"

    emit = info.get("emit") or {}
    cnpj = re.sub(
        r"\D",
        "",
        str(
            info.get("emitente_cnpj")
            or info.get("cnpj_emitente")
            or emit.get("CNPJ")
            or emit.get("cnpj")
            or ""
        ),
    )
    numero = str(info.get("numero") or info.get("nCT") or "").strip()
    serie = str(info.get("serie") or info.get("serie_cte") or "").strip()
    if numero or serie or cnpj:
        return f"cte:{cnpj}:{serie}:{numero}"

    arquivo = str(info.get("arquivo") or info.get("path") or "").strip()
    if arquivo:
        return f"arquivo:{Path(arquivo).name.lower()}"
    return ""

def _central_cte_load_complementary_store(force=False):
    global _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE, _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME
    path = _central_cte_complementary_store_path()
    try:
        mtime = path.stat().st_mtime_ns if path.exists() else None
        if not force and _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE is not None and mtime == _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME:
            return _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        else:
            raw = {}
    except Exception:
        raw = {}
        mtime = None
    raw.setdefault("versao", 1)
    raw.setdefault("itens", {})
    if not isinstance(raw.get("itens"), dict):
        raw["itens"] = {}
    _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE = raw
    _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME = mtime
    return raw

def _central_cte_save_complementary_store(store):
    global _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE, _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME
    path = _central_cte_complementary_store_path()
    store = dict(store or {})
    store["versao"] = 1
    store["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
    store.setdefault("itens", {})
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    _CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE = store
    try:
        _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME = path.stat().st_mtime_ns
    except Exception:
        _CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME = None

def get_complementary_print_information(info):
    info = info or {}
    direct = _central_cte_clean_complementary_information(info.get(CENTRAL_CTE_COMPLEMENTARY_INFO_KEY, ""))
    if direct:
        return direct
    identity = _central_cte_info_identity(info)
    if not identity:
        return ""
    try:
        item = (_central_cte_load_complementary_store().get("itens") or {}).get(identity) or {}
        return _central_cte_clean_complementary_information(item.get("texto", ""))
    except Exception:
        return ""

def apply_complementary_print_information(infos, text):
    value = _central_cte_clean_complementary_information(text)
    if not value:
        raise ValueError("Digite a informação complementar antes de aplicar.")
    store = _central_cte_load_complementary_store(force=True)
    items = store.setdefault("itens", {})
    updated_at = datetime.now().isoformat(timespec="seconds")
    count = 0
    for info in list(infos or []):
        if not isinstance(info, dict) or not _central_cte_is_cte_info(info):
            continue
        identity = _central_cte_info_identity(info)
        if not identity:
            continue
        info[CENTRAL_CTE_COMPLEMENTARY_INFO_KEY] = value
        info[CENTRAL_CTE_COMPLEMENTARY_INFO_META_KEY] = {
            "atualizado_em": updated_at,
            "origem": "Central CT-e / DACTE",
            "xml_fiscal_alterado": False,
        }
        items[identity] = {
            "texto": value,
            "atualizado_em": updated_at,
            "numero": str(info.get("numero") or ""),
            "serie": str(info.get("serie") or ""),
            "arquivo": str(info.get("arquivo") or Path(str(info.get("path") or "")).name),
        }
        count += 1
    if count:
        _central_cte_save_complementary_store(store)
    return count

def _central_cte_apply_complementary_information_html(info, html):
    """Insere a informação após o cálculo compacto ou no lugar dele.

    A operação ocorre exclusivamente no HTML de impressão. O XML fiscal não é
    aberto para escrita e não recebe qualquer modificação.
    """
    try:
        html = str(html or "")
        html = re.sub(
            r'\s*<div[^>]*data-central-complementar="1"[^>]*>.*?</div>\s*',
            "\n",
            html,
            flags=re.S | re.I,
        )
        value = get_complementary_print_information(info)
        if not value or not _central_cte_is_cte_info(info):
            return html
        body = escape(value).replace("\n", "<br>")
        block = (
            '<div class="informacao-complementar-cte" data-central-complementar="1" '
            'style="border:1px solid #111;border-top:0;padding:3px 5px;'
            'font-size:7.4px;line-height:1.22;font-family:Arial,sans-serif;'
            'background:#fffdf2;overflow-wrap:anywhere;">'
            f'<b>INFORMAÇÃO COMPLEMENTAR</b><br>{body}</div>'
        )

        compact = re.search(r'<div class="controle-rodotec[^"]*"[^>]*>.*?</div>', html, flags=re.S | re.I)
        if compact:
            return html[:compact.end()] + "\n    " + block + html[compact.end():]

        marker = re.search(
            r'(?P<indent>[ \t]*)<div class="section-title">INFORMAÇÕES RELATIVAS AO IMPOSTO</div>',
            html,
            flags=re.I,
        )
        if marker:
            indent = marker.group("indent") or "    "
            return html[:marker.start()] + indent + block + "\n\n" + html[marker.start():]
        return html + "\n" + block
    except Exception:
        return html

def write_app_log(file_name, text):
    try:
        logs = app_runtime_dir() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with (logs / file_name).open("a", encoding="utf-8") as f:
            f.write(f"[{stamp}] {text}\n")
    except Exception:
        pass

def photo_asset(name):
    path = resource_path(f"assets/{name}.png")
    if path.exists():
        return tk.PhotoImage(file=str(path))
    key = name.upper()
    if key in ASSET_B64:
        return tk.PhotoImage(data=ASSET_B64[key])
    raise FileNotFoundError(name)

def show_startup_error(exc):
    msg = "Erro ao iniciar o programa:\n\n{}\n\nUm arquivo 'erro_inicializacao.txt' foi criado na mesma pasta do programa.".format(exc)
    try:
        log_path = Path(__file__).resolve().parent / 'erro_inicializacao.txt'
        log_path.write_text(traceback.format_exc(), encoding='utf-8')
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, APP_TITLE, 0x10)
        return
    except Exception:
        pass
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_TITLE, msg)
        root.destroy()
    except Exception:
        print(msg)
        print(traceback.format_exc())

EXPORTED_FUNCTIONS = ('resource_path', 'app_runtime_dir', 'safe_open_folder', 'safe_open_file', 'ensure_work_folders', '_central_cte_is_cte_info', '_central_cte_clean_complementary_information', '_central_cte_complementary_store_path', '_central_cte_info_identity', '_central_cte_load_complementary_store', '_central_cte_save_complementary_store', 'get_complementary_print_information', 'apply_complementary_print_information', '_central_cte_apply_complementary_information_html', 'write_app_log', 'photo_asset', 'show_startup_error')
EXPORTED_CONSTANTS = ('CENTRAL_CTE_COMPLEMENTARY_INFO_KEY', 'CENTRAL_CTE_COMPLEMENTARY_INFO_META_KEY', 'CENTRAL_CTE_COMPLEMENTARY_INFO_MAX_CHARS', '_CENTRAL_CTE_COMPLEMENTARY_STORE_CACHE', '_CENTRAL_CTE_COMPLEMENTARY_STORE_MTIME', 'ASSET_B64')
EXTRACTION_VERSION = "2.6.68.8"


def install_runtime_support_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    for name in EXPORTED_CONSTANTS:
        value = globals()[name]
        if isinstance(value, dict):
            value = dict(value)
        elif isinstance(value, list):
            value = list(value)
        target_globals[name] = value
    installed = install_rebound_functions(globals(), target_globals, EXPORTED_FUNCTIONS)
    state = {
        "version": EXTRACTION_VERSION,
        "module": __name__,
        "functions": list(installed),
        "constants": list(EXPORTED_CONSTANTS),
        "active": True,
    }
    target_globals["CENTRAL_CTE_RUNTIME_SUPPORT_COMPAT_STATE"] = state
    return state


__all__ = ["install_runtime_support_compat", "EXPORTED_FUNCTIONS", "EXPORTED_CONSTANTS"]
