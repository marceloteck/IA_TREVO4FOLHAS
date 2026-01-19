from collections import Counter
from training.core.brain_interface import BrainInterface
import random

class StatFreqGlobalBrain(BrainInterface):

    def __init__(self):
        self.freq = Counter()

    def learn(self, concurso, jogo, pontos, resultado_real):
        for d in resultado_real:
            self.freq[d] += 1

    def generate(self, tamanho=15):
        universo = list(range(1, 26))
        scores = [(d, self.freq[d]) for d in universo]
        scores.sort(key=lambda x: x[1], reverse=True)

        base = [d for d, _ in scores[:18]]
        return sorted(random.sample(base, tamanho))

    def score_game(self, jogo):
        return sum(self.freq[d] for d in jogo)

    def evaluate_context(self, contexto):
        return 1.0

    def save_state(self):
        return dict(self.freq)

    def load_state(self, state):
        self.freq = Counter(state)

    def report(self):
        return {"top_frequentes": self.freq.most_common(10)}
