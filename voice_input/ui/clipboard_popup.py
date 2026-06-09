"""Multi-tab quick-pick popup: clipboard history | snippets | addresses.

Opened by hotkey (Ctrl+Shift+F8) or by voice command:
  "定型文"        → opens with the Snippets tab active
  "住所自動入力"   → opens with the Addresses tab active

Clicking any row (or pressing Enter) pastes that text into the focused window.
"""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QTabWidget,
    QVBoxLayout, QWidget,
)

from ..core.clipboard_history import HistoryStore


class _TabPage(QWidget):
    """One tab: search-filter box + item list."""

    def __init__(self, placeholder: str = "絞り込み…") -> None:
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 6, 4, 0)
        v.setSpacing(4)
        self._filter = QLineEdit()
        self._filter.setPlaceholderText(placeholder)
        v.addWidget(self._filter)
        self._list = QListWidget()
        self._list.setSpacing(1)
        v.addWidget(self._list, 1)

    @property
    def filter_edit(self) -> QLineEdit:
        return self._filter

    @property
    def list_widget(self) -> QListWidget:
        return self._list


class ClipboardHistoryPopup(QDialog):
    """Tabbed popup with three tabs: clipboard history, snippets, addresses."""

    TAB_CLIPBOARD = 0
    TAB_SNIPPETS  = 1
    TAB_ADDRESSES = 2

    def __init__(
        self,
        store: HistoryStore,
        on_pick: Callable[[str], None],
        snippets: list[dict] | None = None,
        addresses: dict[str, dict] | None = None,
        initial_tab: int = TAB_CLIPBOARD,
    ) -> None:
        super().__init__(None, Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("クリップボード / 定型文 / 住所")
        self.resize(560, 540)

        self._store    = store
        self._on_pick  = on_pick
        self._snippets = snippets  or []
        self._addresses = addresses or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)

        # ── Tabs ──────────────────────────────────────────────────────────
        self._tabs = QTabWidget()

        # Tab 0: clipboard history
        self._clip_page = _TabPage(
            "絞り込み… (Enter で貼付 · Del で削除 · Ctrl+P でピン留め)"
        )
        self._tabs.addTab(self._clip_page, "📋 クリップボード")

        # Tab 1: snippets
        self._snip_page = _TabPage("絞り込み…")
        self._tabs.addTab(self._snip_page, "📝 定型文")

        # Tab 2: addresses
        self._addr_page = _TabPage("絞り込み…")
        self._tabs.addTab(self._addr_page, "🏠 住所")

        root.addWidget(self._tabs, 1)

        # ── Bottom buttons ────────────────────────────────────────────────
        h = QHBoxLayout()
        self._clear_btn = QPushButton("履歴クリア (ピン以外)")
        self._clear_btn.clicked.connect(self._clear)
        self._clear_all_btn = QPushButton("全て削除")
        self._clear_all_btn.clicked.connect(self._clear_all)
        h.addWidget(self._clear_btn)
        h.addWidget(self._clear_all_btn)
        h.addStretch(1)
        cancel_btn = QPushButton("閉じる (Esc)")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("貼付 (Enter)")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._activate_current)
        h.addWidget(cancel_btn)
        h.addWidget(ok_btn)
        root.addLayout(h)

        # ── Connections ───────────────────────────────────────────────────
        self._clip_page.filter_edit.textChanged.connect(self._refresh_clipboard)
        self._snip_page.filter_edit.textChanged.connect(self._refresh_snippets)
        self._addr_page.filter_edit.textChanged.connect(self._refresh_addresses)
        self._clip_page.list_widget.itemClicked.connect(self._activate_current)
        self._snip_page.list_widget.itemClicked.connect(self._activate_current)
        self._addr_page.list_widget.itemClicked.connect(self._activate_current)
        self._tabs.currentChanged.connect(self._on_tab_changed)

        # ── Initial population ────────────────────────────────────────────
        self._refresh_clipboard()
        self._refresh_snippets()
        self._refresh_addresses()

        self._tabs.setCurrentIndex(initial_tab)
        self._update_bottom_buttons(initial_tab)

        # ── Position near cursor ──────────────────────────────────────────
        cp  = self.cursor().pos()
        geo = QApplication.primaryScreen().availableGeometry()
        x = min(max(cp.x() - 280, geo.left()), geo.right()  - self.width())
        y = min(max(cp.y() - 100, geo.top()),  geo.bottom() - self.height())
        self.move(x, y)

        QTimer.singleShot(0, self._focus_current_filter)

    # ── helpers ───────────────────────────────────────────────────────────

    def _current_page(self) -> _TabPage:
        return [self._clip_page, self._snip_page, self._addr_page][self._tabs.currentIndex()]

    def _focus_current_filter(self) -> None:
        self._current_page().filter_edit.setFocus()

    def _on_tab_changed(self, idx: int) -> None:
        self._update_bottom_buttons(idx)
        QTimer.singleShot(0, self._focus_current_filter)

    def _update_bottom_buttons(self, idx: int) -> None:
        """Show clear buttons only on the clipboard tab."""
        visible = (idx == self.TAB_CLIPBOARD)
        self._clear_btn.setVisible(visible)
        self._clear_all_btn.setVisible(visible)

    # ── refresh ───────────────────────────────────────────────────────────

    def _refresh_clipboard(self) -> None:
        query = self._clip_page.filter_edit.text().strip().lower()
        entries = self._store.all()
        entries.sort(key=lambda e: (not e.pinned,))
        lst = self._clip_page.list_widget
        lst.clear()
        for e in entries:
            if query and query not in e.text.lower():
                continue
            pin = "📌 " if e.pinned else ""
            item = QListWidgetItem(f"{pin}{e.preview(width=100)}    [{e.timestamp[11:16]}]")
            item.setData(Qt.ItemDataRole.UserRole, e.text)
            item.setToolTip(e.text[:1000])
            lst.addItem(item)
        if lst.count():
            lst.setCurrentRow(0)

    def _refresh_snippets(self) -> None:
        query = self._snip_page.filter_edit.text().strip().lower()
        lst = self._snip_page.list_widget
        lst.clear()
        for s in self._snippets:
            name    = s.get("label", s.get("name", ""))
            content = s.get("content", "")
            if query and query not in name.lower() and query not in content.lower():
                continue
            preview = content[:80].replace("\n", " ")
            item = QListWidgetItem(f"{name}\n  {preview}")
            item.setData(Qt.ItemDataRole.UserRole, content)
            item.setToolTip(content[:1000])
            lst.addItem(item)
        if lst.count():
            lst.setCurrentRow(0)

    def _refresh_addresses(self) -> None:
        """Flat list: every non-empty field of every address entry."""
        query = self._addr_page.filter_edit.text().strip().lower()
        lst = self._addr_page.list_widget
        lst.clear()
        for key, info in self._addresses.items():
            full_addr = info.get("address") or (
                info.get("pref", "") + info.get("city", "") + info.get("street", "")
            )
            fields = [
                ("名前",       info.get("name",       "")),
                ("フリガナ",    info.get("name_kana",  "")),
                ("郵便番号",    info.get("zip",        "")),
                ("住所",       full_addr),
                ("都道府県",    info.get("pref",       "")),
                ("市区町村",    info.get("city",       "")),
                ("番地・建物",   info.get("street",    "")),
                ("電話番号",    info.get("tel",        "")),
            ]
            for field_label, value in fields:
                if not value:
                    continue
                tag = f"[{key}] {field_label}"
                if query and query not in tag.lower() and query not in value.lower():
                    continue
                item = QListWidgetItem(f"{tag}\n  {value[:80]}")
                item.setData(Qt.ItemDataRole.UserRole, value)
                item.setToolTip(value)
                lst.addItem(item)
        if lst.count():
            lst.setCurrentRow(0)

    # ── actions ───────────────────────────────────────────────────────────

    def _activate_current(self) -> None:
        item = self._current_page().list_widget.currentItem()
        if item is None:
            return
        text = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        QTimer.singleShot(120, lambda: self._on_pick(text))

    def _clear(self) -> None:
        self._store.clear(keep_pinned=True)
        self._refresh_clipboard()

    def _clear_all(self) -> None:
        self._store.clear(keep_pinned=False)
        self._refresh_clipboard()

    # ── keyboard ──────────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key  = event.key()
        mods = event.modifiers()
        tab  = self._tabs.currentIndex()
        page = self._current_page()

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._activate_current()
            return
        if key == Qt.Key.Key_Escape:
            self.reject()
            return
        if key == Qt.Key.Key_Delete and tab == self.TAB_CLIPBOARD:
            item = page.list_widget.currentItem()
            if item:
                self._store.remove(item.data(Qt.ItemDataRole.UserRole))
                self._refresh_clipboard()
            return
        if key == Qt.Key.Key_P and (mods & Qt.KeyboardModifier.ControlModifier) and tab == self.TAB_CLIPBOARD:
            item = page.list_widget.currentItem()
            if item:
                self._store.toggle_pin(item.data(Qt.ItemDataRole.UserRole))
                self._refresh_clipboard()
            return
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                   Qt.Key.Key_PageDown, Qt.Key.Key_PageUp):
            page.list_widget.keyPressEvent(event)
            return
        super().keyPressEvent(event)
