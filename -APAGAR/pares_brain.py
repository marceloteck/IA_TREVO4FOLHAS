from collections import Counter
from itertools import combinations
from training.core.brain_interface import BrainInterface
import random

class StatParesBrain(BrainInterface):

    def __init__(self):
        self.pares = Counter()

    def learn(self, concurso, jogo, pontos, resultado_real):
        for a, b in combinations(resultado_real, 2):
            self.pares[(a, b)] += 1

    def generate(self, tamanho=15):
        dezenas = Counter()
        for (a, b), v in self.pares.items():
            dezenas[a] += v
            dezenas[b] += v

        base = [d for d, _ in dezenas.most_common(18)]
        return sorted(random.sample(base, tamanho))

    def score_game(self, jogo):
        score = 0
        for a, b in combinations(jogo, 2):
            score += self.pares.get((a, b), 0)
        return score

    def evaluate_context(self, contexto):
        return 1.1

    def save_state(self):
        return dict(self.pares)

    def load_state(self, state):
        self.pares = Counter(state)

    def report(self):
        return {"top_pares": self.pares.most_common(5)}
