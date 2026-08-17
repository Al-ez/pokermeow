from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)


GAME_OPTIONS = (
    ("No-Limit Texas Hold'em", "nlh", 10),
    ("Pot-Limit Omaha", "plo", 10),
    ("AOF", "aof", 7),
    ("Pot or Fold", "pof", 7),
    ("Pineapple", "pineapple", 10),
    ("Ultra Pineapple", "ultra_pineapple", 7),
    ("Terminator", "terminator", 7),
    ("Allocator", "allocator", 7),
    ("Helicopter", "helicopter", 6),
    ("ESG", "esg", 7),
)


class OrbitalSelectionDialog(QDialog):
    selected = Signal(dict)

    def __init__(self, available_players, default_big_blind=2, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose orbital special game")
        root = QVBoxLayout(self)
        root.addWidget(QLabel("The SG button has been reached. Choose the special hand."))
        self.available_players = max(2, int(available_players))
        form = QFormLayout()
        self.form = form
        self.game = QComboBox()
        for label, key, _cap in GAME_OPTIONS:
            self.game.addItem(label, key)
        self.max_players = QSpinBox()
        self.max_players.setRange(2, self.available_players)
        self.max_players.setValue(self.available_players)
        self.big_blind = QDoubleSpinBox()
        self.big_blind.setRange(0.01, 1_000_000_000)
        self.big_blind.setValue(float(default_big_blind))
        self.ante = QDoubleSpinBox()
        self.ante.setRange(0.01, 1_000_000_000)
        self.ante.setValue(10)
        self.cards = QComboBox()
        for count in (4, 5, 6):
            self.cards.addItem(str(count), count)
        self.boards = QComboBox()
        for count in (1, 2):
            self.boards.addItem(str(count), count)
        self.mode = QComboBox()
        self.mode.addItem("Preflop", "preflop")
        self.mode.addItem("Bomb pot", "bomb_pot")
        self.ante_bb = QSpinBox()
        self.ante_bb.setRange(1, 1_000_000)
        self.ante_bb.setValue(1)
        self.multiplier = QComboBox()
        for value in (10, 15, 20, 25, 30):
            self.multiplier.addItem(str(value), value)
        self.allow_run_twice = QComboBox()
        self.allow_run_twice.addItem("No", False)
        self.allow_run_twice.addItem("Yes", True)
        form.addRow("Game", self.game)
        form.addRow("Player quota", self.max_players)
        form.addRow("Big blind", self.big_blind)
        form.addRow("Ante", self.ante)
        form.addRow("Hole cards", self.cards)
        form.addRow("Boards", self.boards)
        form.addRow("PLO mode", self.mode)
        form.addRow("Ante (in BB)", self.ante_bb)
        form.addRow("AOF multiplier", self.multiplier)
        form.addRow("Allow run twice", self.allow_run_twice)
        root.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        choose = QPushButton("Choose Game")
        choose.setObjectName("primary")
        buttons.addButton(choose, QDialogButtonBox.ButtonRole.AcceptRole)
        choose.clicked.connect(self._submit)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.game.currentIndexChanged.connect(self._game_changed)
        self.mode.currentIndexChanged.connect(self._game_changed)
        self._game_changed()

    def _game_changed(self):
        key = self.game.currentData()
        cap = next(cap for _label, game, cap in GAME_OPTIONS if game == key)
        self.max_players.setMaximum(min(self.available_players, cap))
        self.form.setRowVisible(self.big_blind, key in {"nlh", "plo", "esg"})
        self.form.setRowVisible(self.ante, key not in {"nlh", "plo", "esg"})
        self.form.setRowVisible(self.cards, key in {"plo", "pof"})
        self.form.setRowVisible(self.boards, key == "plo")
        self.form.setRowVisible(self.mode, key == "plo")
        self.form.setRowVisible(
            self.ante_bb,
            key == "plo" and self.mode.currentData() == "bomb_pot",
        )
        self.form.setRowVisible(self.multiplier, key == "aof")
        self.form.setRowVisible(self.allow_run_twice, key == "aof")

    def _submit(self):
        self.selected.emit(
            {
                "game": self.game.currentData(),
                "max_players": self.max_players.value(),
                "big_blind": self.big_blind.value(),
                "ante": self.ante.value(),
                "hole_cards": self.cards.currentData(),
                "boards": self.boards.currentData(),
                "mode": self.mode.currentData(),
                "ante_bb": self.ante_bb.value(),
                "multiplier": self.multiplier.currentData(),
                "allow_run_twice": self.allow_run_twice.currentData(),
            }
        )
        self.accept()


class OrbitalInvitationDialog(QDialog):
    decided = Signal(bool)

    def __init__(self, config, joined, quota, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Orbital special game")
        root = QVBoxLayout(self)
        root.addWidget(QLabel("Special game configuration"))
        details = "\n".join(
            f"{key.replace('_', ' ').title()}: {value}"
            for key, value in config.items()
            if key != "max_players"
        )
        root.addWidget(QLabel(details))
        self.quota_label = QLabel(f"Players joined: {joined}/{quota}")
        self.quota_label.setObjectName("orbitalQuota")
        root.addWidget(self.quota_label)
        play = QPushButton("Play")
        play.setObjectName("orbitalPlay")
        sit_out = QPushButton("Sit Out")
        sit_out.setObjectName("orbitalSitOut")
        play.clicked.connect(lambda: self._decide(True))
        sit_out.clicked.connect(lambda: self._decide(False))
        root.addWidget(play)
        root.addWidget(sit_out)

    def _decide(self, play):
        self.decided.emit(play)
        self.accept()
