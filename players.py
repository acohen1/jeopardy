"""
players.py — Player management and scoring.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Player:
    name: str
    score: int = 0

    def add_score(self, delta: int):
        self.score += delta

    def reset(self):
        self.score = 0


class PlayerManager:
    def __init__(self):
        self._players: list[Player] = []

    # ------------------------------------------------------------------ #
    #  CRUD                                                                 #
    # ------------------------------------------------------------------ #
    def add_player(self, name: str) -> Player:
        name = name.strip()
        if not name:
            raise ValueError("Player name cannot be empty.")
        if any(p.name == name for p in self._players):
            raise ValueError(f"Player '{name}' already exists.")
        p = Player(name=name)
        self._players.append(p)
        return p

    def remove_player(self, name: str):
        self._players = [p for p in self._players if p.name != name]

    def rename_player(self, old_name: str, new_name: str):
        new_name = new_name.strip()
        if not new_name:
            raise ValueError("Player name cannot be empty.")
        for p in self._players:
            if p.name == old_name:
                p.name = new_name
                return
        raise KeyError(f"Player '{old_name}' not found.")

    @property
    def players(self) -> list[Player]:
        return list(self._players)

    # ------------------------------------------------------------------ #
    #  Scoring                                                              #
    # ------------------------------------------------------------------ #
    def award(self, name: str, delta: int):
        for p in self._players:
            if p.name == name:
                p.add_score(delta)
                return
        raise KeyError(f"Player '{name}' not found.")

    def reset_scores(self):
        for p in self._players:
            p.reset()

    # ------------------------------------------------------------------ #
    #  Serialization (embedded in board saves)                             #
    # ------------------------------------------------------------------ #
    def to_list(self) -> list[dict]:
        return [{"name": p.name, "score": p.score} for p in self._players]

    def from_list(self, data: list[dict]):
        self._players = [Player(name=d["name"], score=d.get("score", 0)) for d in data]
