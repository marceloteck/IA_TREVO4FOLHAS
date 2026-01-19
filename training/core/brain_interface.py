# training/core/brain_interface.py

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BrainInterface(ABC):
    """
    ✅ CONTRATO OFICIAL DE UM CÉREBRO

    BrainHub usa isso para:
    - generate(context) -> List[List[int]]
    - evaluate_context(context) -> float (relevância)
    - score_game(jogo, context) -> float (score interno do cérebro)
    - learn(concurso_n, jogo, resultado_n1, pontos, context) -> None
    - save_state() -> dict JSON-serializável
    - load_state(state: dict) -> None
    """

    # Identidade (obrigatório)
    id: str = "brain_undefined"
    name: str = "Undefined Brain"
    category: str = "generic"  # estatistico, estrutural, temporal, exploratorio, elite
    version: str = "v1"

    def __init__(self, db):
        self.db = db
        self.enabled: bool = True

    # -----------------------------
    # Relevância por contexto
    # -----------------------------
    @abstractmethod
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        """Quanto esse cérebro é útil neste concurso (0 = ignore)."""

    # -----------------------------
    # Geração
    # -----------------------------
    @abstractmethod
    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        """
        Deve retornar uma LISTA de jogos.
        O BrainHub injeta no context:
        - tamanho: 15 ou 18
        - n: quantidade de candidatos desejados
        """

    # -----------------------------
    # Score interno
    # -----------------------------
    @abstractmethod
    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        """Score interno comparativo (não precisa ser absoluto)."""

    # -----------------------------
    # Aprendizado N -> N+1
    # -----------------------------
    @abstractmethod
    def learn(
        self,
        concurso_n: int,
        jogo: List[int],
        resultado_n1: List[int],
        pontos: int,
        context: Dict[str, Any],
    ) -> None:
        """Atualiza memória interna com base no resultado real (N+1)."""

    # -----------------------------
    # Persistência (o BrainHub salva no DB)
    # -----------------------------
    @abstractmethod
    def save_state(self) -> Dict[str, Any]:
        """Retorna um dict JSON-serializável."""

    @abstractmethod
    def load_state(self, state: Optional[Dict[str, Any]] = None) -> None:
        """Recebe dict do BrainHub e reconstrói estado."""
