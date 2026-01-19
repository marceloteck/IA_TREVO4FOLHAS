from training.core.brain_interface import BrainInterface
import random

class StatAtrasoBrain(BrainInterface):

    def __init__(self):
        self.ultimo = {d: 0 for d in range(1, 26)}
        self.contador = 0

    def learn(self, concurso, jogo, pontos, resultado_real):
        self.contador += 1
        for d in range(1, 26):
            if d in resultado_real:
                self.ultimo[d] = self.contador

    def generate(self, tamanho=15):
        atrasos = {d: self.contador - self.ultimo[d] for d in self.ultimo}
        base = sorted(atrasos, key=atrasos.get, reverse=True)[:18]
        return sorted(random.sample(base, tamanho))

    def score_game(self, jogo):
        return sum(self.contador - self.ultimo[d] for d in jogo)

    def evaluate_context(self, contexto):
        return 0.9

    def save_state(self):
        return {
            "ultimo": self.ultimo,
            "contador": self.contador
        }

    def load_state(self, state):
        self.ultimo = state["ultimo"]
        self.contador = state["contador"]

    def report(self):
        return {"mais_atrasadas": sorted(self.ultimo, key=self.ultimo.get)[:5]}
