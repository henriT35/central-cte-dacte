"""Núcleo modular do Central CT-e / DACTE.

Na versão 2.7.0, os serviços e objetos internos passam a viver em um
registro explícito. O motor legado recebe somente as funções operacionais e os
aliases mínimos necessários durante a retirada gradual do monólito.
"""
from .bootstrap.app_bootstrap import (
    FOUNDATION_VERSION,
    FoundationState,
    install_foundation,
    install_runtime,
)
from .bootstrap.runtime_registry import RuntimeRegistry

__all__ = [
    "FOUNDATION_VERSION",
    "FoundationState",
    "RuntimeRegistry",
    "install_foundation",
    "install_runtime",
]
