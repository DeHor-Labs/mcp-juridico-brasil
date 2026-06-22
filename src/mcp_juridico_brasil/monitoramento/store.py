"""Store de snapshots de processos monitorados.

Guarda o último snapshot (dados + timestamp) por número de processo.
Persistência em memória por sessão MCP; persistência em arquivo JSON
opcional via JURIDICO_SNAPSHOT_DIR no ambiente.

Decisão de design (Fase 2):
- Store em memória é suficiente para o caso de uso de sessão única
- Arquivo JSON local oferece persistência simples entre reinicializações
- Banco de dados relacional ou Redis fica para Fase 3+ (multi-tenant, escala)

Limitações documentadas:
- Estado em memória se perde ao reiniciar o servidor MCP
- Sem controle de concorrência (apenas asyncio, sem multiprocessing)
- Sem expiração automática de snapshots (ficam indefinidamente na memória)
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_juridico_brasil._core import get_logger

_SNAPSHOT_DIR_ENV = "JURIDICO_SNAPSHOT_DIR"
logger = get_logger(__name__)

# Chave: numero_processo normalizado
# Valor: dicionario com snapshot e metadados
_snapshots: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _snapshot_path(numero: str) -> Path | None:
    """Retorna caminho do arquivo de snapshot se JURIDICO_SNAPSHOT_DIR configurado."""
    snapshot_dir = os.environ.get(_SNAPSHOT_DIR_ENV)
    if not snapshot_dir:
        return None
    base = Path(snapshot_dir)
    base.mkdir(parents=True, exist_ok=True)
    # Substitui caracteres especiais do numero CNJ no nome de arquivo
    nome_seguro = numero.replace("/", "-").replace(".", "-")
    return base / f"snapshot_{nome_seguro}.json"


def _carregar_do_disco(numero: str) -> dict[str, Any] | None:
    """Tenta carregar snapshot do arquivo JSON local."""
    caminho = _snapshot_path(numero)
    if caminho is None or not caminho.exists():
        return None
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        return None


def _salvar_no_disco(numero: str, snapshot: dict[str, Any]) -> None:
    """Persiste snapshot no arquivo JSON local, se configurado."""
    caminho = _snapshot_path(numero)
    if caminho is None:
        return
    try:
        caminho.write_text(
            json.dumps(snapshot, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("snapshot_disco_falha_escrita", numero=numero, erro=str(exc))


def salvar_snapshot(
    numero_processo: str,
    tribunal: str,
    dados: dict[str, Any],
) -> dict[str, Any]:
    """Salva snapshot de um processo monitorado.

    Args:
        numero_processo: Número CNJ normalizado do processo.
        tribunal: Sigla do tribunal.
        dados: Dicionário com dados do processo (saída de buscar_processo_por_numero).

    Returns:
        Snapshot salvo com metadados de timestamp.
    """
    agora = datetime.now(tz=timezone.utc).isoformat()
    snapshot: dict[str, Any] = {
        "numero_processo": numero_processo,
        "tribunal": tribunal,
        "capturado_em": agora,
        "dados": dados,
    }
    with _lock:
        _snapshots[numero_processo] = snapshot
    _salvar_no_disco(numero_processo, snapshot)
    return snapshot


def obter_snapshot(numero_processo: str) -> dict[str, Any] | None:
    """Recupera o último snapshot de um processo.

    Busca primeiro na memória; se não encontrar, tenta o arquivo local.

    Args:
        numero_processo: Número CNJ normalizado do processo.

    Returns:
        Snapshot ou None se não houver.
    """
    with _lock:
        em_memoria = _snapshots.get(numero_processo)
    if em_memoria is not None:
        return em_memoria
    # Tentativa via disco
    do_disco = _carregar_do_disco(numero_processo)
    if do_disco is not None:
        with _lock:
            _snapshots[numero_processo] = do_disco
    return do_disco


def listar_processos_monitorados() -> list[str]:
    """Lista numeros de processos com snapshot em memoria.

    Returns:
        Lista de numeros de processos (strings).
    """
    with _lock:
        return list(_snapshots.keys())


def remover_snapshot(numero_processo: str) -> bool:
    """Remove snapshot de um processo da memória e do disco.

    Args:
        numero_processo: Número CNJ normalizado.

    Returns:
        True se havia snapshot e foi removido; False se não existia.
    """
    with _lock:
        existia = numero_processo in _snapshots
        _snapshots.pop(numero_processo, None)
    caminho = _snapshot_path(numero_processo)
    if caminho and caminho.exists():
        try:
            caminho.unlink()
        except OSError as exc:
            logger.warning("snapshot_disco_falha_remocao", numero=numero_processo, erro=str(exc))
    return existia


def total_snapshots() -> int:
    """Retorna total de snapshots em memoria."""
    with _lock:
        return len(_snapshots)


__all__ = [
    "listar_processos_monitorados",
    "obter_snapshot",
    "remover_snapshot",
    "salvar_snapshot",
    "total_snapshots",
]
