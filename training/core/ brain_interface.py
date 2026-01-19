# training/core/brain_interface.py

from typing import List, Dict, Any
from abc import ABC, abstractmethod


class BrainInterface(ABC):
    """
    🧠 CONTRATO OFICIAL DE UM CÉREBRO
    --------------------------------
    Todo cérebro do sistema DEVE herdar desta classe.
    Nenhuma exceção.
    """

    # ==================================================
    # 🔹 IDENTIDADE DO CÉREBRO
    # ==================================================

    id: str = "undefined"
    name: str = "Undefined Brain"
    category: str = "generic"  # estatistico, estrutural, temporal, exploratorio, elite

    def __init__(self, db):
        """
        db: conexão ou wrapper de banco de dados
        """
        self.db = db
        self.enabled = True
        self.load_state()

    # ==================================================
    # 🎯 GERAÇÃO
    # ==================================================
    @abstractmethod
    def generate(self, context: Dict[str, Any]) -> List[List[int]]:
        """
        Gera uma lista de jogos candidatos.
        Ex:
        [
            [1,2,3,...],
            [4,7,9,...]
        ]
        """
        raise NotImplementedError("generate() não implementado")

    # ==================================================
    # 🧪 AVALIAÇÃO DE CONTEXTO
    # ==================================================
    @abstractmethod
    def evaluate_context(self, context: Dict[str, Any]) -> float:
        """
        Retorna um score (0–1) indicando
        o quanto este cérebro é relevante
        para o contexto atual.
        """
        raise NotImplementedError("evaluate_context() não implementado")

    # ==================================================
    # 🎓 APRENDIZADO N → N+1
    # ==================================================
    @abstractmethod
    def learn(
        self,
        concurso: int,
        jogo: List[int],
        resultado_real: List[int],
        pontos: int
    ):
        """
        Aprendizado incremental após cada concurso.
        """
        raise NotImplementedError("learn() não implementado")

    # ==================================================
    # 📊 SCORE INTERNO
    # ==================================================
    @abstractmethod
    def score_game(self, jogo: List[int]) -> float:
        """
        Retorna score interno do cérebro para um jogo.
        Usado pelo BrainHub para votação.
        """
        raise NotImplementedError("score_game() não implementado")

    # ==================================================
    # 💾 PERSISTÊNCIA
    # ==================================================
    @abstractmethod
    def save_state(self):
        """
        Persiste memória interna no banco.
        """
        raise NotImplementedError("save_state() não implementado")

    @abstractmethod
    def load_state(self):
        """
        Carrega memória interna do banco.
        """
        raise NotImplementedError("load_state() não implementado")

    # ==================================================
    # 📈 RELATÓRIO
    # ==================================================
    @abstractmethod
    def report(self) -> Dict[str, Any]:
        """
        Retorna métricas internas:
        - uso
        - performance
        - aprendizados
        """
        raise NotImplementedError("report() não implementado")

    # ==================================================
    # 🔒 CONTROLE
    # ==================================================
    def enable(self):
        self.enabled = True

    def disable(self):
        self.enabled = False
