# training/core/brain_interface.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

class BrainInterface(ABC):
    id: str
    name: str
    category: str
    version: str
    enabled: bool = True

    @abstractmethod
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        """0..1 (ou maior), relevância do cérebro no contexto"""

    @abstractmethod
    def generate(self, context: Dict[str, Any], size: int, n: int) -> List[List[int]]:
        """gera N candidatos"""

    @abstractmethod
    def score_game(self, jogo: List[int], context: Dict[str, Any]) -> float:
        """score interno (comparativo)"""

    @abstractmethod
    def learn(self, concurso_n: int, jogo: List[int], resultado_n1: List[int], pontos: int, context: Dict[str, Any]) -> None:
        """aprendizado incremental N->N+1"""

    @abstractmethod
    def save_state(self) -> None:
        """salva estado no banco"""

    @abstractmethod
    def load_state(self) -> None:
        """carrega estado do banco"""

    @abstractmethod
    def report(self) -> Dict[str, Any]:
        """relatório interno para auditoria"""
