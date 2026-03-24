from __future__ import annotations

import sys

from coin_partner.prototype_data import PrototypeSnapshot, StrategyField, build_prototype_snapshot


try:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDoubleSpinBox,
        QFrame,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QStackedWidget,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
except ImportError:  # pragma: no cover - runtime dependency path
    QApplication = None


class PulseChart(QWidget):
    def __init__(self, points: list[float]) -> None:
        super().__init__()
        self.points = points
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        if not self.points:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(10, 12, -10, -18)

        background_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        background_gradient.setColorAt(0.0, QColor("#14332f"))
        background_gradient.setColorAt(1.0, QColor("#0d221f"))
        painter.fillRect(rect, background_gradient)

        minimum = min(self.points)
        maximum = max(self.points)
        spread = maximum - minimum or 1.0
        step_x = rect.width() / max(len(self.points) - 1, 1)

        line_path = QPainterPath()
        area_path = QPainterPath()
        plotted: list[QPointF] = []
        for index, point in enumerate(self.points):
            x = rect.left() + index * step_x
            normalized = (point - minimum) / spread
            y = rect.bottom() - normalized * rect.height()
            plotted.append(QPointF(x, y))

        line_path.moveTo(plotted[0])
        for point in plotted[1:]:
            line_path.lineTo(point)

        area_path.addPath(line_path)
        area_path.lineTo(rect.right(), rect.bottom())
        area_path.lineTo(rect.left(), rect.bottom())
        area_path.closeSubpath()

        area_gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        area_gradient.setColorAt(0.0, QColor(228, 93, 52, 130))
        area_gradient.setColorAt(1.0, QColor(228, 93, 52, 10))
        painter.fillPath(area_path, area_gradient)

        grid_pen = QPen(QColor("#335750"))
        grid_pen.setStyle(Qt.DotLine)
        for offset in range(1, 4):
            y = rect.top() + rect.height() * offset / 4
            painter.setPen(grid_pen)
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        line_pen = QPen(QColor("#ff8e62"))
        line_pen.setWidth(3)
        painter.setPen(line_pen)
        painter.drawPath(line_path)

        accent_pen = QPen(QColor("#f7f2e8"))
        accent_pen.setWidth(6)
        painter.setPen(accent_pen)
        painter.drawPoint(plotted[-1])


class PrototypeWindow(QMainWindow):
    def __init__(self, snapshot: PrototypeSnapshot) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.stack = QStackedWidget()
        self.sidebar = QListWidget()
        self.setWindowTitle("Coin Partner Studio Prototype")
        self.resize(1480, 920)
        self._configure_fonts()
        self._build_ui()
        self._apply_styles()

    def _configure_fonts(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setFont(QFont("Avenir Next", 11))

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), stretch=1)

        self.setCentralWidget(root)

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidePanel")
        panel.setFixedWidth(270)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 24, 22, 24)
        layout.setSpacing(18)

        brand = QLabel("Coin Partner\nStudio")
        brand.setObjectName("brandLabel")
        caption = QLabel("Sales prototype for a desktop auto-trading product.")
        caption.setWordWrap(True)
        caption.setObjectName("sideCaption")

        self.sidebar.setObjectName("navList")
        self.sidebar.setSpacing(8)
        for item_text in [
            "Control Room",
            "Strategy Studio",
            "Risk Desk",
            "Exchange Vault",
            "Activity Tape",
        ]:
            item = QListWidgetItem(item_text)
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self.stack.setCurrentIndex)

        profile_box = QFrame()
        profile_box.setObjectName("profileBox")
        profile_layout = QVBoxLayout(profile_box)
        profile_layout.setContentsMargins(14, 14, 14, 14)
        profile_layout.setSpacing(6)
        profile_layout.addWidget(self._pill("Prototype Profile"))
        profile_layout.addWidget(self._value_label(self.snapshot.profile_name))
        profile_layout.addWidget(self._muted_label("Prepared for screenshots, feature pitches, and client demos"))

        layout.addWidget(brand)
        layout.addWidget(caption)
        layout.addWidget(self.sidebar)
        layout.addWidget(profile_box)
        return panel

    def _build_content(self) -> QWidget:
        container = QFrame()
        container.setObjectName("contentPanel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(26, 20, 26, 20)
        layout.setSpacing(18)

        layout.addWidget(self._build_header())

        self.stack.addWidget(self._wrap_page(self._build_dashboard_page()))
        self.stack.addWidget(self._wrap_page(self._build_strategy_page()))
        self.stack.addWidget(self._wrap_page(self._build_risk_page()))
        self.stack.addWidget(self._wrap_page(self._build_exchange_page()))
        self.stack.addWidget(self._wrap_page(self._build_activity_page()))
        layout.addWidget(self.stack, stretch=1)
        return container

    def _build_header(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("heroPanel")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(16)

        text_column = QVBoxLayout()
        text_column.setSpacing(8)
        title = QLabel(self.snapshot.title)
        title.setObjectName("heroTitle")
        subtitle = QLabel(self.snapshot.subtitle)
        subtitle.setWordWrap(True)
        subtitle.setObjectName("heroSubtitle")
        text_column.addWidget(self._pill(self.snapshot.mode_badge))
        text_column.addWidget(title)
        text_column.addWidget(subtitle)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._action_button("Start Preview", "primaryButton"))
        actions.addWidget(self._action_button("Run Backtest", "secondaryButton"))
        actions.addWidget(self._action_button("Export Report", "secondaryButton"))

        layout.addLayout(text_column, stretch=1)
        layout.addLayout(actions)
        return frame

    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(18)

        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(14)
        metrics_grid.setVerticalSpacing(14)
        for index, metric in enumerate(self.snapshot.metrics):
            metrics_grid.addWidget(self._metric_card(metric.label, metric.value, metric.detail), index // 2, index % 2)
        layout.addLayout(metrics_grid)

        lower_grid = QGridLayout()
        lower_grid.setHorizontalSpacing(14)
        lower_grid.setVerticalSpacing(14)
        lower_grid.addWidget(self._market_pulse_card(), 0, 0)
        lower_grid.addWidget(self._signals_card(), 0, 1)
        lower_grid.addWidget(self._positions_card(), 1, 0, 1, 2)
        layout.addLayout(lower_grid)
        return page

    def _build_strategy_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)

        template_box = self._card_box("Template Stack")
        template_layout = template_box.layout()
        assert isinstance(template_layout, QVBoxLayout)
        template_layout.addWidget(self._template_card("Pullback Hunter", "EMA reclaim + volume confirmation", True))
        template_layout.addWidget(self._template_card("Breakout Engine", "Level sweep + close above range", False))
        template_layout.addWidget(self._template_card("RSI Snapback", "Short-term exhaustion mean reversion", False))
        template_layout.addStretch(1)

        editor_box = self._card_box("Parameter Grid")
        editor_layout = editor_box.layout()
        assert isinstance(editor_layout, QVBoxLayout)
        for field in self.snapshot.strategy_fields:
            editor_layout.addWidget(self._strategy_control(field))

        toggles_box = self._card_box("Condition Switches")
        toggles_layout = toggles_box.layout()
        assert isinstance(toggles_layout, QVBoxLayout)
        for text, enabled in [
            ("Use higher timeframe trend filter", True),
            ("Require volume expansion on entry", True),
            ("Block overheated 10m momentum", True),
            ("Allow one-bar re-entry after take profit", False),
        ]:
            checkbox = QCheckBox(text)
            checkbox.setChecked(enabled)
            toggles_layout.addWidget(checkbox)
        toggles_layout.addStretch(1)

        layout.addWidget(template_box, 0, 0, 2, 1)
        layout.addWidget(editor_box, 0, 1)
        layout.addWidget(toggles_box, 1, 1)
        return page

    def _build_risk_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)

        risk_editor = self._card_box("Risk Rails")
        risk_layout = risk_editor.layout()
        assert isinstance(risk_layout, QVBoxLayout)
        for field in self.snapshot.risk_fields:
            risk_layout.addWidget(self._strategy_control(field))

        checklist = self._card_box("Safety Gates")
        checklist_layout = checklist.layout()
        assert isinstance(checklist_layout, QVBoxLayout)
        for text in [
            "Paper mode must run successfully before live mode unlocks",
            "Double confirmation required for first live order",
            "Exchange minimum order size validation enabled",
            "Daily stop disables new entries across all markets",
            "Position import required after manual live orders",
        ]:
            checkbox = QCheckBox(text)
            checkbox.setChecked(True)
            checklist_layout.addWidget(checkbox)
        checklist_layout.addStretch(1)

        summary = self._card_box("Risk Story")
        summary_layout = summary.layout()
        assert isinstance(summary_layout, QVBoxLayout)
        for line in [
            "Designed to sell a disciplined product, not a black-box money promise.",
            "Each profile exposes enough knobs for clients without opening free-form scripting.",
            "The UI keeps capital, cooldowns, and stops visible at all times.",
        ]:
            summary_layout.addWidget(self._muted_label(line))
        summary_layout.addStretch(1)

        layout.addWidget(risk_editor, 0, 0, 2, 1)
        layout.addWidget(checklist, 0, 1)
        layout.addWidget(summary, 1, 1)
        return page

    def _build_exchange_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)

        connectors = self._card_box("Connector Options")
        connectors_layout = connectors.layout()
        assert isinstance(connectors_layout, QVBoxLayout)
        for exchange in self.snapshot.exchanges:
            connectors_layout.addWidget(self._exchange_card(exchange.name, exchange.note, exchange.badge))

        secrets = self._card_box("Secret Handling")
        secrets_layout = secrets.layout()
        assert isinstance(secrets_layout, QVBoxLayout)
        for line in [
            "API keys should live in OS keychain storage, not in a plain-text TOML file.",
            "Connection test should verify read-only scope first, then trading scope.",
            "The production app can hide unsupported exchanges per customer package.",
        ]:
            secrets_layout.addWidget(self._muted_label(line))
        secrets_layout.addStretch(1)

        package_box = self._card_box("Sales Package Framing")
        package_layout = package_box.layout()
        assert isinstance(package_layout, QVBoxLayout)
        for line in [
            "Basic: single strategy template + profile save/load",
            "Advanced: custom risk rails + multiple market watchlists",
            "Premium: exchange-specific adapter and onboarding support",
        ]:
            package_layout.addWidget(self._value_label(line))
        package_layout.addStretch(1)

        layout.addWidget(connectors, 0, 0)
        layout.addWidget(secrets, 0, 1)
        layout.addWidget(package_box, 1, 0, 1, 2)
        return page

    def _build_activity_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        box = self._card_box("Recent Activity")
        box_layout = box.layout()
        assert isinstance(box_layout, QVBoxLayout)
        for item in self.snapshot.activities:
            row = QFrame()
            row.setObjectName("timelineRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setSpacing(12)
            time_label = QLabel(item.time_text)
            time_label.setObjectName("timelineTime")
            content = QVBoxLayout()
            content.setSpacing(4)
            content.addWidget(self._value_label(item.title))
            content.addWidget(self._muted_label(item.detail))
            row_layout.addWidget(time_label)
            row_layout.addLayout(content, stretch=1)
            box_layout.addWidget(row)
        box_layout.addStretch(1)
        layout.addWidget(box)
        return page

    def _market_pulse_card(self) -> QWidget:
        box = self._card_box("Market Pulse")
        layout = box.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.addWidget(self._muted_label("Mock momentum curve for the sales prototype dashboard"))
        layout.addWidget(PulseChart(self.snapshot.market_pulse))
        return box

    def _signals_card(self) -> QWidget:
        box = self._card_box("Signal Radar")
        layout = box.layout()
        assert isinstance(layout, QVBoxLayout)
        for signal in self.snapshot.signals:
            row = QFrame()
            row.setObjectName("signalRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(12, 12, 12, 12)
            row_layout.setSpacing(8)
            row_layout.addWidget(self._value_label("{0} · {1}".format(signal.market, signal.timeframe)))
            row_layout.addWidget(self._muted_label(signal.status))
            progress = QProgressBar()
            progress.setRange(0, 100)
            progress.setValue(signal.progress_percent)
            progress.setFormat(signal.progress_text)
            row_layout.addWidget(progress)
            layout.addWidget(row)
        return box

    def _positions_card(self) -> QWidget:
        box = self._card_box("Open Position Preview")
        layout = box.layout()
        assert isinstance(layout, QVBoxLayout)
        table = QTableWidget(len(self.snapshot.positions), 6)
        table.setHorizontalHeaderLabels(["Market", "Strategy", "Entry", "Mark", "PnL", "Hold"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        for row_index, row in enumerate(self.snapshot.positions):
            values = [row.market, row.strategy, row.entry_price, row.mark_price, row.pnl, row.hold_time]
            for column_index, value in enumerate(values):
                table.setItem(row_index, column_index, QTableWidgetItem(value))
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setDefaultSectionSize(140)
        layout.addWidget(table)
        return box

    def _metric_card(self, label: str, value: str, detail: str) -> QWidget:
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        layout.addWidget(self._pill(label))
        number = QLabel(value)
        number.setObjectName("metricValue")
        layout.addWidget(number)
        layout.addWidget(self._muted_label(detail))
        return card

    def _template_card(self, title: str, description: str, active: bool) -> QWidget:
        card = QFrame()
        card.setObjectName("templateCardActive" if active else "templateCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(6)
        layout.addWidget(self._value_label(title))
        layout.addWidget(self._muted_label(description))
        if active:
            layout.addWidget(self._pill("Selected"))
        return card

    def _strategy_control(self, field: StrategyField) -> QWidget:
        row = QFrame()
        row.setObjectName("controlRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._value_label(field.label), stretch=1)

        if field.decimals == 0:
            spin = QSpinBox()
            spin.setRange(int(field.minimum), int(field.maximum))
            spin.setValue(int(field.value))
            if field.suffix:
                spin.setSuffix(field.suffix)
            widget = spin
        else:
            spin = QDoubleSpinBox()
            spin.setDecimals(field.decimals)
            spin.setRange(field.minimum, field.maximum)
            spin.setValue(field.value)
            if field.suffix:
                spin.setSuffix(field.suffix)
            widget = spin

        widget.setButtonSymbols(QSpinBox.NoButtons)
        widget.setAlignment(Qt.AlignRight)
        layout.addWidget(widget)
        return row

    def _exchange_card(self, title: str, note: str, badge: str) -> QWidget:
        card = QFrame()
        card.setObjectName("exchangeCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addWidget(self._pill(badge))
        layout.addWidget(self._value_label(title))
        layout.addWidget(self._muted_label(note))
        return card

    def _card_box(self, title: str) -> QGroupBox:
        box = QGroupBox(title)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 16)
        layout.setSpacing(12)
        return box

    def _wrap_page(self, page: QWidget) -> QWidget:
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setWidget(page)
        return scroller

    def _action_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        return button

    def _pill(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("pillLabel")
        return label

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("valueLabel")
        return label

    def _muted_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName("mutedLabel")
        return label

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #e9e1d2;
                color: #17302c;
            }
            #sidePanel {
                background: #102723;
            }
            #contentPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f7f1e6, stop:1 #efe7db);
            }
            #brandLabel {
                color: #f6efe4;
                font-size: 29px;
                font-weight: 800;
                line-height: 1.1em;
            }
            #sideCaption {
                color: #9db1aa;
                font-size: 13px;
            }
            #profileBox, #heroPanel, #metricCard, #templateCard, #templateCardActive,
            #exchangeCard, #timelineRow, #signalRow {
                border: 1px solid #cfbfaa;
                border-radius: 18px;
                background: rgba(255, 251, 244, 0.92);
            }
            #templateCardActive {
                border: 2px solid #e45d34;
                background: #fff4ea;
            }
            #heroPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #102a26, stop:1 #214841);
                border: none;
            }
            #heroTitle {
                color: #f7f1e6;
                font-size: 34px;
                font-weight: 800;
            }
            #heroSubtitle {
                color: #cfdbd4;
                font-size: 14px;
            }
            #navList {
                background: transparent;
                border: none;
                outline: none;
                color: #d5e1db;
                font-size: 14px;
            }
            #navList::item {
                border-radius: 14px;
                padding: 14px 14px;
                background: rgba(255, 255, 255, 0.04);
                margin-bottom: 6px;
            }
            #navList::item:selected {
                background: #e45d34;
                color: #fff8f1;
            }
            #pillLabel {
                background: #efe0c7;
                color: #875d32;
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }
            #valueLabel {
                color: #14302b;
                font-size: 15px;
                font-weight: 700;
            }
            #mutedLabel {
                color: #5f726c;
                font-size: 13px;
            }
            #metricValue {
                color: #14302b;
                font-size: 28px;
                font-weight: 800;
            }
            #timelineTime {
                min-width: 54px;
                color: #e45d34;
                font-size: 18px;
                font-weight: 800;
            }
            QGroupBox {
                font-size: 15px;
                font-weight: 800;
                color: #14302b;
                border: 1px solid #cfbfaa;
                border-radius: 18px;
                margin-top: 10px;
                background: rgba(255, 252, 247, 0.88);
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
            }
            QPushButton {
                min-height: 40px;
                border-radius: 12px;
                padding: 0 16px;
                font-size: 13px;
                font-weight: 800;
            }
            #primaryButton {
                background: #e45d34;
                color: #fff9f1;
                border: none;
            }
            #secondaryButton {
                background: transparent;
                color: #f6efe4;
                border: 1px solid #6d8d84;
            }
            QProgressBar {
                height: 24px;
                border-radius: 12px;
                background: #eee4d6;
                border: 1px solid #d5c6b2;
                text-align: center;
                color: #17302c;
                font-weight: 700;
            }
            QProgressBar::chunk {
                border-radius: 12px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e45d34, stop:1 #f59a61);
            }
            QTableWidget {
                background: transparent;
                border: 1px solid #d5c6b2;
                border-radius: 14px;
                gridline-color: #e5d8c7;
                alternate-background-color: #faf3e8;
                selection-background-color: transparent;
            }
            QHeaderView::section {
                background: #efe5d8;
                color: #6d5b46;
                border: none;
                border-bottom: 1px solid #d5c6b2;
                padding: 8px;
                font-weight: 800;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QCheckBox {
                spacing: 10px;
                color: #17302c;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 5px;
                border: 1px solid #b8a793;
                background: #fff7ee;
            }
            QCheckBox::indicator:checked {
                background: #e45d34;
                border: 1px solid #e45d34;
            }
            QSpinBox, QDoubleSpinBox {
                min-height: 36px;
                min-width: 150px;
                border-radius: 10px;
                padding: 0 12px;
                background: #fff9f1;
                border: 1px solid #d3c3af;
                color: #17302c;
                font-weight: 700;
            }
            """
        )


def main() -> int:
    if QApplication is None:
        raise SystemExit("PySide6 is required. Run `pip install -e .` first.")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = PrototypeWindow(build_prototype_snapshot())
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
