from collections import Counter, deque
from training.core.brain_interface import BrainInterface
import random

class StatFreqRecenteBrain(BrainInterface):

    def __init__(self, janela=20):
        self.janela = janela
        self.buffer = deque(maxlen=janela)
        self.freq = Counter()

    def learn(self, concurso, jogo, pontos, resultado_real):
        if len(self.buffer) == self.janela:
            removido = self.buffer.popleft()
            for d in removido:
                self.freq[d] -= 1

        self.buffer.append(resultado_real)
        for d in resultado_real:
            self.freq[d] += 1

    def generate(self, tamanho=15):
        scores = [(d, self.freq[d]) for d in range(1, 26)]
        scores.sort(key=lambda x: x[1], reverse=True)
        base = [d for d, _ in scores[:18]]
        return sorted(random.sample(base, tamanho))

    def score_game(self, jogo):
        return sum(self.freq[d] for d in jogo)

    def evaluate_context(self, contexto):
        return 1.2

    def save_state(self):
        return {
            "buffer": list(self.buffer),
            "freq": dict(self.freq)
        }

    def load_state(self, state):
        self.buffer = deque(state["buffer"], maxlen=self.janela)
        self.freq = Counter(state["freq"])

    def report(self):
        return {"janela": self.janela}
