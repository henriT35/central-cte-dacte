from __future__ import annotations

"""Ambiente mínimo para executar a interface e os fallbacks históricos.

As importações e constantes que antes ficavam na fachada ``central_cte_core``
agora vivem aqui. A fachada passa a declarar somente a composição, sem carregar
módulos pesados ou manter detalhes de Tkinter, XML, ZIP e sistema operacional.
"""

import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
import traceback
import unicodedata
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any, MutableMapping
from zipfile import ZipFile


def _build_headless_tk() -> tuple[Any, Any, Any, Any, Any]:
    class _DummyWidget:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def __getattr__(self, name: str) -> Any:
            def _noop(*args: Any, **kwargs: Any) -> Any:
                return None

            return _noop

        def __setitem__(self, key: Any, value: Any) -> None:
            return None

        def __getitem__(self, key: Any) -> Any:
            return None

    class _DummyVar:
        def __init__(self, value: Any = None, *args: Any, **kwargs: Any) -> None:
            self._value = value

        def get(self) -> Any:
            return self._value

        def set(self, value: Any) -> None:
            self._value = value

    class _DummyModule:
        Tk = _DummyWidget
        Frame = _DummyWidget
        Label = _DummyWidget
        Button = _DummyWidget
        Canvas = _DummyWidget
        Entry = _DummyWidget
        Text = _DummyWidget
        Scrollbar = _DummyWidget
        Menu = _DummyWidget
        Toplevel = _DummyWidget
        StringVar = _DummyVar
        BooleanVar = _DummyVar
        IntVar = _DummyVar
        DoubleVar = _DummyVar
        END = "end"
        BOTH = "both"
        LEFT = "left"
        RIGHT = "right"
        TOP = "top"
        BOTTOM = "bottom"
        X = "x"
        Y = "y"
        YES = True
        NO = False
        NSEW = "nsew"
        EW = "ew"
        NS = "ns"
        W = "w"
        E = "e"
        N = "n"
        S = "s"
        CENTER = "center"
        HORIZONTAL = "horizontal"
        VERTICAL = "vertical"
        NORMAL = "normal"
        DISABLED = "disabled"
        WORD = "word"

        def __getattr__(self, name: str) -> Any:
            return _DummyWidget

    class _DummyDialog:
        def __getattr__(self, name: str) -> Any:
            def _noop(*args: Any, **kwargs: Any) -> Any:
                return "" if name.startswith("ask") else None

            return _noop

    class _DummyMessageBox:
        def showinfo(self, *args: Any, **kwargs: Any) -> None:
            return None

        def showwarning(self, *args: Any, **kwargs: Any) -> None:
            return None

        def showerror(self, *args: Any, **kwargs: Any) -> None:
            return None

        def askyesno(self, *args: Any, **kwargs: Any) -> bool:
            return False

    dummy_module = _DummyModule()
    return dummy_module, dummy_module, _DummyDialog(), _DummyMessageBox(), _DummyDialog()


try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk

    TK_BACKEND = "tkinter"
except Exception:
    tk, ttk, filedialog, messagebox, simpledialog = _build_headless_tk()
    TK_BACKEND = "headless_dummy"


APP_TITLE = "Central CT-e / DACTE"
from central_cte_modular.version import APP_VERSION
SUPPORTED_DIRECT_PRINT = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".txt",
    ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff",
}

BLUE = "#0b4f9f"
BLUE_DARK = "#073d7d"
BLUE_LIGHT = "#eaf4ff"
LINE = "#dbe6f3"
TEXT = "#17233c"
MUTED = "#5c6b82"
RED = "#ed1b2f"
GREEN = "#087a3d"
BG = "#f6f9fd"

ENVIRONMENT_VERSION = "2.7.0"

_ENVIRONMENT_SYMBOLS = {
    "os": os,
    "sys": sys,
    "shutil": shutil,
    "json": json,
    "base64": base64,
    "traceback": traceback,
    "re": re,
    "unicodedata": unicodedata,
    "ZipFile": ZipFile,
    "time": time,
    "tempfile": tempfile,
    "webbrowser": webbrowser,
    "tk": tk,
    "ttk": ttk,
    "filedialog": filedialog,
    "messagebox": messagebox,
    "simpledialog": simpledialog,
    "Path": Path,
    "ET": ET,
    "escape": escape,
    "datetime": datetime,
    "timedelta": timedelta,
    "APP_TITLE": APP_TITLE,
    "APP_VERSION": APP_VERSION,
    "SUPPORTED_DIRECT_PRINT": SUPPORTED_DIRECT_PRINT,
    "BLUE": BLUE,
    "BLUE_DARK": BLUE_DARK,
    "BLUE_LIGHT": BLUE_LIGHT,
    "LINE": LINE,
    "TEXT": TEXT,
    "MUTED": MUTED,
    "RED": RED,
    "GREEN": GREEN,
    "BG": BG,
}


def install_runtime_environment_compat(target_globals: MutableMapping[str, Any]) -> dict[str, Any]:
    installed: list[str] = []
    for name, value in _ENVIRONMENT_SYMBOLS.items():
        if isinstance(value, set):
            value = set(value)
        target_globals[name] = value
        installed.append(name)

    state = {
        "version": ENVIRONMENT_VERSION,
        "module": __name__,
        "active": True,
        "symbols": installed,
        "symbol_count": len(installed),
        "tk_backend": TK_BACKEND,
        "facade_heavy_imports": 0,
        "facade_constants": 0,
    }
    target_globals["CENTRAL_CTE_RUNTIME_ENVIRONMENT_COMPAT_STATE"] = state
    return state


__all__ = [
    "ENVIRONMENT_VERSION",
    "install_runtime_environment_compat",
]
