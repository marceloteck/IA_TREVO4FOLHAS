from __future__ import annotations

import random
from typing import Dict, List

import numpy as np
from sklearn.neural_network import MLPClassifier

from training.meta.bandit_fallback import ContextualThompsonBandit
from training.meta.context_features import FEATURE_NAMES
from training.meta.model_store import ModelStore


EXP_LEVELS = ["baixo", "medio", "alto"]
EXP_RATE_BY_LEVEL = {"baixo": 0.2, "medio": 0.5, "alto": 0.8}


class MetaController:
    def __init__(self, config: dict, model_store: ModelStore | None = None) -> None:
        self.config = dict(config)
        self.model_store = model_store or ModelStore()
        self.bandit = ContextualThompsonBandit()

        self.arm_model = self._new_model()
        self.recipe_model = self._new_model()
        self.explore_model = self._new_model()

        self.arm_classes: np.ndarray | None = None
        self.recipe_classes: np.ndarray | None = None
        self.explore_classes = np.array(EXP_LEVELS)
        self.is_trained = False

        self._train_buffer: List[dict] = []
        self._last_decision: dict | None = None

        self._load_checkpoint()

    def _new_model(self) -> MLPClassifier:
        hidden_units = int(self.config.get("hidden_units", 32))
        lr = float(self.config.get("learning_rate", 0.001))
        return MLPClassifier(
            hidden_layer_sizes=(hidden_units, hidden_units),
            activation="relu",
            solver="adam",
            learning_rate_init=lr,
            max_iter=2,
            batch_size=int(self.config.get("batch_size", 32)),
            random_state=42,
            warm_start=False,
        )

    def _load_checkpoint(self) -> None:
        state = self.model_store.load()
        if not state:
            return
        self.arm_model = state.get("arm_model", self.arm_model)
        self.recipe_model = state.get("recipe_model", self.recipe_model)
        self.explore_model = state.get("explore_model", self.explore_model)
        self.bandit = ContextualThompsonBandit.from_state(state.get("bandit"))
        self.arm_classes = state.get("arm_classes")
        self.recipe_classes = state.get("recipe_classes")
        self.is_trained = bool(state.get("is_trained", False))

    def _save_checkpoint(self) -> None:
        self.model_store.save(
            {
                "arm_model": self.arm_model,
                "recipe_model": self.recipe_model,
                "explore_model": self.explore_model,
                "bandit": self.bandit.to_state(),
                "arm_classes": self.arm_classes,
                "recipe_classes": self.recipe_classes,
                "is_trained": self.is_trained,
            }
        )

    def _feature_vector(self, features: Dict[str, float]) -> np.ndarray:
        return np.array([[float(features.get(name, 0.0)) for name in FEATURE_NAMES]], dtype=np.float32)

    def _confidence(self, probs: np.ndarray) -> float:
        return float(np.max(probs)) if probs.size else 0.0

    def _context_key(self, features: Dict[str, float]) -> str:
        return f"regime:{int(round(float(features.get('regime_id', 0.5)) * 4))}"

    def decide(
        self,
        features: Dict[str, float],
        arms: List[str],
        recipes: List[str],
        default_arm: str,
        default_recipe: str,
        regime_unstable: bool = False,
        **kwargs,
    ) -> Dict[str, object]:
        x = self._feature_vector(features)
        threshold = float(self.config.get("confidence_threshold", 0.55))
        fallback_enabled = bool(self.config.get("fallback_enabled", True))

        if self.arm_classes is None:
            self.arm_classes = np.array(sorted(set(arms or [default_arm])))
        if self.recipe_classes is None:
            self.recipe_classes = np.array(sorted(set(recipes or [default_recipe])))

        fallback_used = 0
        arm_choice = default_arm
        recipe_choice = default_recipe
        explore_level = "medio"
        confidence = 0.0

        can_predict = self.is_trained and len(self.arm_classes) > 1 and len(self.recipe_classes) > 1
        if can_predict:
            arm_probs_all = self.arm_model.predict_proba(x)[0]
            recipe_probs_all = self.recipe_model.predict_proba(x)[0]
            exp_probs = self.explore_model.predict_proba(x)[0]

            arm_prob_map = {cls: arm_probs_all[i] for i, cls in enumerate(self.arm_model.classes_) if cls in set(arms)}
            recipe_prob_map = {cls: recipe_probs_all[i] for i, cls in enumerate(self.recipe_model.classes_) if cls in set(recipes)}
            if arm_prob_map:
                arm_choice = max(arm_prob_map, key=arm_prob_map.get)
            if recipe_prob_map:
                recipe_choice = max(recipe_prob_map, key=recipe_prob_map.get)
            explore_level = EXP_LEVELS[int(np.argmax(exp_probs))]

            confidence = float(
                np.mean(
                    [
                        max(arm_prob_map.values()) if arm_prob_map else 0.0,
                        max(recipe_prob_map.values()) if recipe_prob_map else 0.0,
                        self._confidence(exp_probs),
                    ]
                )
            )

        if not can_predict or confidence < threshold or regime_unstable:
            if fallback_enabled:
                fallback_used = 1
                context_key = self._context_key(features)
                arm_choice = self.bandit.choose(context_key, arms) or default_arm
                recipe_choice = self.bandit.choose(context_key, recipes) or default_recipe
                explore_level = self.bandit.choose(context_key, EXP_LEVELS) or "medio"
                confidence = min(confidence, 0.5)

        decision = {
            "arm": arm_choice,
            "recipe": recipe_choice,
            "explore_level": explore_level,
            "exploration_rate": float(EXP_RATE_BY_LEVEL.get(explore_level, 0.5)),
            "confidence": float(confidence),
            "fallback_used": int(fallback_used),
        }
        self._last_decision = decision
        return decision

    def train_step(
        self,
        features: Dict[str, float],
        decision: Dict[str, object],
        reward: float,
        regime_unstable: bool = False,
        **kwargs,
    ) -> None:
        y_arm = str(decision.get("arm", ""))
        y_recipe = str(decision.get("recipe", ""))
        y_exp = str(decision.get("explore_level", "medio"))
        self._train_buffer.append({"x": self._feature_vector(features)[0], "arm": y_arm, "recipe": y_recipe, "exp": y_exp})

        context_key = self._context_key(features)
        self.bandit.update(context_key, y_arm, float(reward))
        self.bandit.update(context_key, y_recipe, float(reward))
        self.bandit.update(context_key, y_exp, float(reward))

        train_every = max(1, int(self.config.get("train_every_steps", 10)))
        if len(self._train_buffer) < train_every:
            return

        batch = self._train_buffer[-int(self.config.get("batch_size", 32)) :]
        x = np.array([item["x"] for item in batch], dtype=np.float32)
        y_arm_arr = np.array([item["arm"] for item in batch])
        y_recipe_arr = np.array([item["recipe"] for item in batch])
        y_exp_arr = np.array([item["exp"] for item in batch])

        self.arm_classes = np.array(sorted(set((self.arm_classes.tolist() if self.arm_classes is not None else []) + y_arm_arr.tolist())))
        self.recipe_classes = np.array(sorted(set((self.recipe_classes.tolist() if self.recipe_classes is not None else []) + y_recipe_arr.tolist())))

        try:
            self.arm_model.partial_fit(x, y_arm_arr, classes=self.arm_classes)
            self.recipe_model.partial_fit(x, y_recipe_arr, classes=self.recipe_classes)
            self.explore_model.partial_fit(x, y_exp_arr, classes=self.explore_classes)
            self.is_trained = True
        except Exception:
            # fallback robusto: não interrompe o backtest
            pass

        if not regime_unstable:
            self._save_checkpoint()


    def get_state(self) -> dict:
        return {
            "model_path": str(self.model_store.path),
            "model_version": 1,
            "confidence_threshold": float(self.config.get("confidence_threshold", 0.55)),
            "bandit": self.bandit.to_state(),
            "is_trained": bool(self.is_trained),
        }

    def set_state(self, state: dict) -> None:
        bandit_state = state.get("bandit")
        if bandit_state:
            self.bandit = ContextualThompsonBandit.from_state(bandit_state)
        cp = self.model_store.load_state()
        if cp:
            self.arm_model = cp.get("arm_model", self.arm_model)
            self.recipe_model = cp.get("recipe_model", self.recipe_model)
            self.explore_model = cp.get("explore_model", self.explore_model)
            self.arm_classes = cp.get("arm_classes")
            self.recipe_classes = cp.get("recipe_classes")
            self.is_trained = bool(cp.get("is_trained", self.is_trained))
