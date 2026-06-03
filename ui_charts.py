"""Biểu đồ phân bố điểm (matplotlib) nhúng vào PyQt6."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

_BIN_ORDER = [
    "Xuất sắc\n(≥8.5)",
    "Giỏi\n(7.0–8.4)",
    "Khá\n(5.5–6.9)",
    "TB\n(4.0–5.4)",
    "Yếu\n(<4.0)",
]
_BIN_COLORS = ["#047857", "#1d4ed8", "#c2410c", "#be185d", "#b91c1c"]


def classify_dtb_bins(dtb_values):
    bins = {k: 0 for k in _BIN_ORDER}
    for dtb in dtb_values:
        try:
            g = float(dtb)
        except (TypeError, ValueError):
            continue
        if g >= 8.5:
            bins["Xuất sắc\n(≥8.5)"] += 1
        elif g >= 7.0:
            bins["Giỏi\n(7.0–8.4)"] += 1
        elif g >= 5.5:
            bins["Khá\n(5.5–6.9)"] += 1
        elif g >= 4.0:
            bins["TB\n(4.0–5.4)"] += 1
        else:
            bins["Yếu\n(<4.0)"] += 1
    return bins


class GradeChartHost(QWidget):
    """Ô chứa biểu đồ; cập nhật bằng set_distribution(dtb_list)."""

    def __init__(self, title="Phân bố điểm trung bình", parent=None):
        super().__init__(parent)
        self._title = title
        self.setMinimumHeight(160)
        self.setMaximumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 4, 0, 4)
        self._placeholder = QLabel("Cài matplotlib để xem biểu đồ: pip install matplotlib")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self._placeholder)
        self._canvas = None

    def set_distribution(self, dtb_values):
        bins = classify_dtb_bins(dtb_values or [])
        labels = _BIN_ORDER
        counts = [bins[k] for k in labels]
        total = sum(counts)
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
        except ImportError:
            if self._placeholder:
                self._placeholder.setText(
                    "Chưa cài matplotlib — chạy: pip install matplotlib"
                )
                self._placeholder.show()
            return

        if self._canvas is not None:
            self._layout.removeWidget(self._canvas)
            self._canvas.deleteLater()
            self._canvas = None
        if self._placeholder is not None:
            self._placeholder.hide()

        fig = Figure(figsize=(6.2, 2.4), dpi=100)
        fig.patch.set_facecolor("#f8fafc")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#ffffff")
        colors = _BIN_COLORS
        bars = ax.bar(range(len(labels)), counts, color=colors, edgecolor="#e2e8f0", linewidth=0.8)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylabel("Số bản ghi điểm", fontsize=9)
        ax.set_title(self._title, fontsize=10, fontweight="bold", color="#0f172a")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if total > 0:
            for bar, c in zip(bars, counts):
                if c <= 0:
                    continue
                pct = round(c * 100 / total)
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height(),
                    f"{c}\n({pct}%)",
                    ha="center",
                    va="bottom",
                    fontsize=7,
                )
        else:
            ax.text(0.5, 0.5, "Chưa có dữ liệu", ha="center", va="center", transform=ax.transAxes)
        fig.tight_layout()
        self._canvas = FigureCanvasQTAgg(fig)
        self._layout.addWidget(self._canvas)
