"""Testes do store de snapshots de monitoramento.

Cobre: salvar, obter, listar, remover snapshots.
Testa persistencia em disco via variavel de ambiente JURIDICO_SNAPSHOT_DIR.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any


def _reset_store_module() -> Any:
    """Reimporta o modulo store para limpar o estado global _snapshots."""
    modulo = "mcp_juridico_brasil.monitoramento.store"
    if modulo in sys.modules:
        del sys.modules[modulo]
    return importlib.import_module(modulo)


def test_salvar_e_obter_snapshot() -> None:
    """Snapshot salvo deve ser recuperado corretamente."""
    store = _reset_store_module()

    dados: dict[str, Any] = {"numero_processo": "00012345", "tribunal": "TJSP", "status": "ativo"}
    resultado = store.salvar_snapshot("00012345", "TJSP", dados)

    assert resultado["numero_processo"] == "00012345"
    assert resultado["tribunal"] == "TJSP"
    assert "capturado_em" in resultado
    assert resultado["dados"] == dados

    recuperado = store.obter_snapshot("00012345")
    assert recuperado is not None
    assert recuperado["dados"] == dados


def test_obter_snapshot_inexistente_retorna_none() -> None:
    """Snapshot de processo nao monitorado deve retornar None."""
    store = _reset_store_module()
    assert store.obter_snapshot("99999999") is None


def test_listar_processos_monitorados() -> None:
    """Apos salvar 3 processos, lista deve conter todos os 3."""
    store = _reset_store_module()

    for i in range(1, 4):
        store.salvar_snapshot(f"proc_{i:05d}", "TJSP", {"id": i})

    lista = store.listar_processos_monitorados()
    assert "proc_00001" in lista
    assert "proc_00002" in lista
    assert "proc_00003" in lista
    assert store.total_snapshots() >= 3


def test_remover_snapshot_existente() -> None:
    """Remover snapshot existente deve retornar True e sumir da lista."""
    store = _reset_store_module()

    store.salvar_snapshot("remover_este", "TJRJ", {"x": 1})
    assert store.obter_snapshot("remover_este") is not None

    removido = store.remover_snapshot("remover_este")
    assert removido is True
    assert store.obter_snapshot("remover_este") is None
    assert "remover_este" not in store.listar_processos_monitorados()


def test_remover_snapshot_inexistente_retorna_false() -> None:
    """Remover snapshot inexistente deve retornar False sem lancar erro."""
    store = _reset_store_module()
    assert store.remover_snapshot("nao_existe_nunca") is False


def test_salvar_sobrescreve_snapshot_anterior() -> None:
    """Salvar novo snapshot para mesmo processo deve sobrescrever o anterior."""
    store = _reset_store_module()

    store.salvar_snapshot("mesmo_proc", "TJSP", {"versao": 1})
    store.salvar_snapshot("mesmo_proc", "TJSP", {"versao": 2})

    snap = store.obter_snapshot("mesmo_proc")
    assert snap is not None
    assert snap["dados"]["versao"] == 2


def test_persistencia_em_disco(tmp_path: Path, monkeypatch: Any) -> None:
    """Snapshot deve ser persistido em arquivo JSON no JURIDICO_SNAPSHOT_DIR."""
    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", str(tmp_path))
    store = _reset_store_module()

    dados = {"numero": "disco_01", "tribunal": "TJMG"}
    store.salvar_snapshot("disco_01", "TJMG", dados)

    # Deve existir arquivo JSON no diretorio
    arquivos = list(tmp_path.glob("snapshot_*.json"))
    assert len(arquivos) >= 1

    # Conteudo do arquivo deve ser JSON valido com o snapshot
    conteudo = json.loads(arquivos[0].read_text(encoding="utf-8"))
    assert conteudo["numero_processo"] == "disco_01"
    assert conteudo["dados"]["tribunal"] == "TJMG"


def test_carga_do_disco_quando_nao_em_memoria(tmp_path: Path, monkeypatch: Any) -> None:
    """Obter snapshot deve tentar carregar do disco se nao estiver em memoria."""
    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", str(tmp_path))
    store = _reset_store_module()

    # Salva via store (persiste em disco)
    store.salvar_snapshot("do_disco", "TJPA", {"fonte": "disco"})

    # Simula reinicializacao reimportando o modulo (reseta _snapshots automaticamente)
    # Sem acesso ao atributo privado _snapshots - o proprio _reset_store_module
    # recria o modulo com estado limpo, simulando restart do servidor.
    store = _reset_store_module()
    monkeypatch.setenv("JURIDICO_SNAPSHOT_DIR", str(tmp_path))  # reaplica env no novo modulo

    # Mesmo apos reset, obter_snapshot deve recuperar do disco
    assert store.obter_snapshot("do_disco") is not None


def test_total_snapshots_consistente() -> None:
    """total_snapshots deve refletir quantidade em memoria."""
    store = _reset_store_module()

    inicial = store.total_snapshots()
    store.salvar_snapshot("t1", "TJSP", {})
    store.salvar_snapshot("t2", "TJRJ", {})
    assert store.total_snapshots() == inicial + 2

    store.remover_snapshot("t1")
    assert store.total_snapshots() == inicial + 1
