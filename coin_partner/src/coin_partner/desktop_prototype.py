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
        self.setWindowTitle("코인 파트너 프로토타입")
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

        brand = QLabel("코인 파트너")
        brand.setObjectName("brandLabel")
        caption = QLabel("너무 복잡하지 않게, 개인도 바로 이해할 수 있는 자동매매 화면 예시")
        caption.setWordWrap(True)
        caption.setObjectName("sideCaption")

        self.sidebar.setObjectName("navList")
        self.sidebar.setSpacing(8)
        for item_text in ["홈", "설정"]:
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
        profile_layout.addWidget(self._pill("예시 프로필"))
        profile_layout.addWidget(self._value_label(self.snapshot.profile_name))
        profile_layout.addWidget(self._muted_label("크몽 소개 이미지나 상담용 캡처에 맞춘 간단한 형태"))

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
        self.stack.addWidget(self._wrap_page(self._build_settings_page()))
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
        actions.addWidget(self._action_button("미리보기", "primaryButton"))
        actions.addWidget(self._action_button("전략 테스트", "secondaryButton"))

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
        lower_grid.addWidget(self._positions_card(), 1, 0)
        lower_grid.addWidget(self._activity_card(), 1, 1)
        layout.addLayout(lower_grid)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)

        template_box = self._card_box("전략 선택")
        template_layout = template_box.layout()
        assert isinstance(template_layout, QVBoxLayout)
        template_layout.addWidget(self._template_card("눌림목 매수", "이동평균 근처 눌림 후 회복 시 진입", True))
        template_layout.addWidget(self._template_card("돌파 매수", "고점 돌파와 거래량 증가가 같이 나올 때 진입", False))
        template_layout.addWidget(self._template_card("RSI 반등", "과매도 이후 짧은 반등을 노리는 방식", False))
        template_layout.addStretch(1)

        editor_box = self._card_box("매수 기준")
        editor_layout = editor_box.layout()
        assert isinstance(editor_layout, QVBoxLayout)
        for field in self.snapshot.strategy_fields:
            editor_layout.addWidget(self._strategy_control(field))

        risk_box = self._card_box("자금 / 리스크")
        risk_layout = risk_box.layout()
        assert isinstance(risk_layout, QVBoxLayout)
        for field in self.snapshot.risk_fields:
            risk_layout.addWidget(self._strategy_control(field))

        options_box = self._card_box("운영 설정")
        options_layout = options_box.layout()
        assert isinstance(options_layout, QVBoxLayout)
        for line in [
            ("거래소", "Bybit 우선, 다른 거래소도 맞춤 연동 가능"),
            ("거래 코인", "BTC / ETH / XRP"),
            ("기준 봉", "5분봉"),
            ("실행 주기", "30초마다 점검"),
            ("거래 시간", "오전 9시 ~ 새벽 2시"),
        ]:
            options_layout.addWidget(self._summary_row(line[0], line[1]))
        for text, enabled in [
            ("손절 후 자동 대기 시간 적용", True),
            ("같은 코인 재진입 제한", True),
            ("실거래 전 모의매매 먼저 확인", True),
            ("사용자가 직접 거래소 API 키 입력", True),
        ]:
            checkbox = QCheckBox(text)
            checkbox.setChecked(enabled)
        for exchange in self.snapshot.exchanges:
            options_layout.addWidget(self._exchange_card(exchange.name, exchange.note, exchange.badge))
        options_layout.addStretch(1)

        layout.addWidget(template_box, 0, 0)
        layout.addWidget(editor_box, 0, 1)
        layout.addWidget(risk_box, 1, 0)
        layout.addWidget(options_box, 1, 1)
        return page

    def _activity_card(self) -> QWidget:
        box = self._card_box("최근 알림")
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
        return box

    def _market_pulse_card(self) -> QWidget:
        box = self._card_box("시장 흐름")
        layout = box.layout()
        assert isinstance(layout, QVBoxLayout)
        layout.addWidget(self._muted_label("실시간 차트 대신, 이런 식으로 분위기를 보여주는 예시 그래프"))
        layout.addWidget(PulseChart(self.snapshot.market_pulse))
        return box

    def _signals_card(self) -> QWidget:
        box = self._card_box("진입 대기")
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
        box = self._card_box("보유 종목 예시")
        layout = box.layout()
        assert isinstance(layout, QVBoxLayout)
        table = QTableWidget(len(self.snapshot.positions), 6)
        table.setHorizontalHeaderLabels(["코인", "전략", "진입가", "현재가", "수익률", "보유"])
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
            layout.addWidget(self._pill("선택됨"))
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

    def _summary_row(self, label: str, value: str) -> QWidget:
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self._muted_label(label))
        layout.addWidget(self._value_label(value), stretch=1)
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
                background: #f1eadf;
                color: #17302c;
            }
            #sidePanel {
                background: #e8dece;
            }
            #contentPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #fbf7f1, stop:1 #f3ecdf);
            }
            #brandLabel {
                color: #183933;
                font-size: 28px;
                font-weight: 800;
            }
            #sideCaption {
                color: #5f6f69;
                font-size: 13px;
            }
            #profileBox, #heroPanel, #metricCard, #templateCard, #templateCardActive,
            #exchangeCard, #timelineRow, #signalRow {
                border: 1px solid #d8c9b6;
                border-radius: 18px;
                background: rgba(255, 251, 244, 0.95);
            }
            #templateCardActive {
                border: 2px solid #e45d34;
                background: #fff4ea;
            }
            #heroPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #fff7eb, stop:1 #f6dfcf);
                border: 1px solid #e1cdbb;
            }
            #heroTitle {
                color: #183933;
                font-size: 32px;
                font-weight: 800;
            }
            #heroSubtitle {
                color: #5d6f69;
                font-size: 14px;
            }
            #navList {
                background: transparent;
                border: none;
                outline: none;
                color: #183933;
                font-size: 14px;
                font-weight: 700;
            }
            #navList::item {
                border-radius: 14px;
                padding: 14px 14px;
                background: rgba(255, 255, 255, 0.55);
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
                border: 1px solid #d8c9b6;
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
                background: rgba(255, 255, 255, 0.75);
                color: #183933;
                border: 1px solid #d7c8b5;
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
