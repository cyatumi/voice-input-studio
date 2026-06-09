"""Snippet / address selection popup (triggered by voice keyword)."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout,
)


class ChoiceDialog(QDialog):
    """Generic list-picker. Items: [{'label': str, 'content': str, 'meta': any?}, ...]"""

    def __init__(self, title: str, items: list[dict]) -> None:
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.setWindowTitle(title)
        self.resize(420, 460)
        self.selected: dict | None = None

        v = QVBoxLayout(self)
        v.addWidget(QLabel(title))
        self._list = QListWidget()
        for it in items:
            label = it.get("label", "")
            preview = it.get("content", "")
            display = QListWidgetItem(f"{label}\n  {preview[:80]}")
            display.setData(Qt.UserRole, it)
            self._list.addItem(display)
        self._list.itemDoubleClicked.connect(self._accept_item)
        v.addWidget(self._list, 1)

        h = QHBoxLayout()
        ok = QPushButton("選択")
        ok.clicked.connect(self._accept_selected)
        cancel = QPushButton("閉じる")
        cancel.clicked.connect(self.reject)
        h.addStretch(1)
        h.addWidget(cancel)
        h.addWidget(ok)
        v.addLayout(h)

    def _accept_item(self, item: QListWidgetItem) -> None:
        self.selected = item.data(Qt.UserRole)
        self.accept()

    def _accept_selected(self) -> None:
        it = self._list.currentItem()
        if it:
            self.selected = it.data(Qt.UserRole)
            self.accept()


def pick_snippet(snippets: list[dict]) -> str | None:
    if not snippets:
        return None
    dlg = ChoiceDialog("定型文を選択", snippets)
    if dlg.exec() == QDialog.Accepted and dlg.selected:
        return dlg.selected.get("content", "")
    return None


def pick_address_field(addresses: dict[str, dict]) -> str | None:
    if not addresses:
        return None
    items = [{"label": key, "content": info.get("name", "")} for key, info in addresses.items()]
    dlg = ChoiceDialog("住所を選択 → 詳細", items)
    if dlg.exec() != QDialog.Accepted or not dlg.selected:
        return None
    key = dlg.selected["label"]
    info = addresses[key]
    field_items = [
        {"label": "郵便番号", "content": info.get("zip", "")},
        {"label": "名前", "content": info.get("name", "")},
        {"label": "フリガナ", "content": info.get("name_kana", "")},
        {"label": "住所全体", "content": info.get("address",
            info.get("pref", "") + info.get("city", "") + info.get("street", ""))},
        {"label": "都道府県", "content": info.get("pref", "")},
        {"label": "市区町村", "content": info.get("city", "")},
        {"label": "番地・建物", "content": info.get("street", "")},
        {"label": "電話番号", "content": info.get("tel", "")},
    ]
    dlg2 = ChoiceDialog(f"{key} の詳細", field_items)
    if dlg2.exec() == QDialog.Accepted and dlg2.selected:
        return dlg2.selected.get("content", "")
    return None
