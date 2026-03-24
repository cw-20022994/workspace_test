from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from trade_studio.core.models import ProfileConfig
from trade_studio.storage.settings import ProfileRepository


class MainWindow(QMainWindow):
    def __init__(self, repository: ProfileRepository) -> None:
        super().__init__()
        self.repository = repository
        self.profiles = self.repository.load_profiles()
        self.active_profile = self.profiles[0]

        self.setWindowTitle("Trade Studio")
        self.resize(1280, 820)
        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        self.setCentralWidget(self._build_central_widget())
        self._build_actions()

    def _build_actions(self) -> None:
        save_action = QAction("Save Profile", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_profiles)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(save_action)

    def _build_central_widget(self) -> QWidget:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_summary_grid())
        layout.addWidget(self._build_tabs(), stretch=1)
        return root

    def _build_header(self) -> QWidget:
        container = QFrame()
        container.setObjectName("headerPanel")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)

        title_column = QVBoxLayout()
        title = QLabel("Trade Studio")
        title.setObjectName("heroTitle")
        subtitle = QLabel(
            "Desktop trading workspace for exchange-supported automation, profile control, and risk-first execution."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("heroSubtitle")
        title_column.addWidget(title)
        title_column.addWidget(subtitle)

        action_column = QHBoxLayout()
        start_button = QPushButton("Start Paper Session")
        start_button.setObjectName("primaryButton")
        stop_button = QPushButton("Stop")
        stop_button.setObjectName("secondaryButton")
        backtest_button = QPushButton("Run Backtest")
        backtest_button.setObjectName("secondaryButton")
        action_column.addWidget(start_button)
        action_column.addWidget(stop_button)
        action_column.addWidget(backtest_button)

        layout.addLayout(title_column, stretch=1)
        layout.addLayout(action_column)
        return container

    def _build_summary_grid(self) -> QWidget:
        container = QWidget()
        layout = QGridLayout(container)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)

        cards = [
            ("Exchange", self.active_profile.exchange.value.upper()),
            ("Profile", self.active_profile.name),
            ("Markets", ", ".join(self.active_profile.markets)),
            ("Mode", self.active_profile.mode.value.upper()),
        ]
        for index, (label, value) in enumerate(cards):
            row = index // 2
            column = index % 2
            layout.addWidget(self._build_stat_card(label, value), row, column)
        return container

    def _build_tabs(self) -> QWidget:
        tabs = QTabWidget()
        tabs.addTab(self._build_dashboard_tab(), "Dashboard")
        tabs.addTab(self._build_exchange_tab(), "Exchange")
        tabs.addTab(self._build_strategy_tab(), "Strategy")
        tabs.addTab(self._build_risk_tab(), "Risk")
        return tabs

    def _build_dashboard_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(16)
        layout.addWidget(
            self._build_info_box(
                "Execution Watch",
                [
                    "Signal queue, open positions, and session alerts will be rendered here.",
                    "The first implementation target is profile-driven paper trading on Kraken.",
                ],
            )
        )
        layout.addWidget(
            self._build_info_box(
                "Current Profile Snapshot",
                [
                    "Timeframe: {0}".format(self.active_profile.strategy.timeframe),
                    "Poll Interval: {0}s".format(self.active_profile.schedule.poll_interval_seconds),
                    "Entry Size: {0:,.2f} {1}".format(
                        self.active_profile.capital.entry_quote,
                        self.active_profile.base_currency,
                    ),
                ],
            )
        )
        layout.addStretch(1)
        return container

    def _build_exchange_tab(self) -> QWidget:
        return self._build_info_box(
            "Connection Plan",
            [
                "Adapter boundary is in place for Kraken, OKX, and Bybit.",
                "Production key storage should use OS keychain APIs instead of plain files.",
                "OAuth should be preferred where the exchange supports third-party desktop apps.",
            ],
        )

    def _build_strategy_tab(self) -> QWidget:
        profile = self.active_profile
        lines = [
            "Template: {0}".format(profile.strategy.template.value),
            "Indicators: {0}".format(
                ", ".join(sorted(key for key, enabled in profile.strategy.indicators.items() if enabled))
            ),
            "Parameters: {0}".format(
                ", ".join(
                    "{0}={1}".format(key, value) for key, value in sorted(profile.strategy.parameters.items())
                )
            ),
        ]
        return self._build_info_box("Strategy Template", lines)

    def _build_risk_tab(self) -> QWidget:
        profile = self.active_profile
        return self._build_info_box(
            "Risk Envelope",
            [
                "Total Capital: {0:,.2f} {1}".format(profile.capital.total_quote, profile.base_currency),
                "Reserve: {0:,.2f} {1}".format(profile.capital.reserve_quote, profile.base_currency),
                "Stop / Take: {0:.2%} / {1:.2%}".format(
                    profile.risk.stop_loss_pct,
                    profile.risk.take_profit_pct,
                ),
                "Daily Loss Limit: {0:,.2f} {1}".format(
                    profile.risk.daily_loss_limit_quote,
                    profile.base_currency,
                ),
            ],
        )

    def _build_stat_card(self, label: str, value: str) -> QWidget:
        card = QFrame()
        card.setObjectName("statCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)

        label_widget = QLabel(label)
        label_widget.setObjectName("cardLabel")
        value_widget = QLabel(value)
        value_widget.setWordWrap(True)
        value_widget.setObjectName("cardValue")

        layout.addWidget(label_widget)
        layout.addWidget(value_widget)
        return card

    def _build_info_box(self, title: str, lines: list[str]) -> QWidget:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setSpacing(10)

        for line in lines:
            label = QLabel(line)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            layout.addWidget(label)
        return box

    def _save_profiles(self) -> None:
        self.repository.save_profiles(self.profiles)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f3efe6;
                color: #152420;
            }
            QToolBar {
                background: #f3efe6;
                border: none;
                spacing: 12px;
                padding: 0 20px 8px 20px;
            }
            QTabWidget::pane {
                border: 1px solid #d3c7b8;
                background: #fffaf2;
                border-radius: 16px;
                top: -1px;
            }
            QTabBar::tab {
                background: #e9dfcf;
                color: #304740;
                border: 1px solid #d3c7b8;
                padding: 10px 18px;
                margin-right: 6px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QTabBar::tab:selected {
                background: #fffaf2;
                color: #152420;
            }
            QGroupBox {
                font-size: 15px;
                font-weight: 700;
                color: #152420;
                border: 1px solid #d3c7b8;
                border-radius: 14px;
                margin-top: 12px;
                padding: 12px;
                background: #fffdf8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLabel {
                font-size: 14px;
                color: #304740;
            }
            #headerPanel {
                border: 1px solid #d3c7b8;
                border-radius: 20px;
                background: #112b26;
            }
            #heroTitle {
                color: #f7f2e9;
                font-size: 30px;
                font-weight: 800;
            }
            #heroSubtitle {
                color: #cddccf;
                font-size: 14px;
            }
            #statCard {
                border: 1px solid #d3c7b8;
                border-radius: 16px;
                background: #fffaf2;
            }
            #cardLabel {
                color: #81694d;
                font-size: 12px;
                text-transform: uppercase;
                letter-spacing: 0.1em;
            }
            #cardValue {
                color: #152420;
                font-size: 20px;
                font-weight: 700;
            }
            QPushButton {
                min-height: 38px;
                border-radius: 10px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 700;
            }
            #primaryButton {
                background: #e45d34;
                color: #fff7f0;
                border: none;
            }
            #secondaryButton {
                background: transparent;
                color: #f7f2e9;
                border: 1px solid #6f8d83;
            }
            """
        )

