import os
from dataclasses import replace

from typing import Optional

from PyQt5 import uic
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QToolBar,
    QWidget,
    QAction,
    QPushButton,
    QLineEdit,
    QDialog,
    QVBoxLayout,
    QSizePolicy,
    QDialogButtonBox, QListWidget, QMenu, QActionGroup, QLabel, QFrame, QInputDialog
)
from qgis.gui import QgsExtentWidget
from qgis.core import QgsApplication, QgsGeometry, QgsProject
from qgis.utils import iface

from .controller import Controller
from .models import FilterModel, DataRole
from .filters import Predicate, FilterManager


class ExtentDialog(QDialog):
    def __init__(self, controller: Controller, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.controller = controller
        self.setObjectName("mExtentDialog")
        self.setWindowTitle(self.tr("Set rectangular filter geometry"))
        self.setupUi()
        self.extentWidget.setOriginalExtent(iface.mapCanvas().extent(), QgsProject.instance().crs())
        self.extentWidget.setMapCanvas(iface.mapCanvas())

    def setupUi(self):
        self.resize(700, 80)
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setSizePolicy(sizePolicy)
        self.verticalLayout = QVBoxLayout(self)
        self.extentWidget = QgsExtentWidget(self)
        self.verticalLayout.addWidget(self.extentWidget)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel | QDialogButtonBox.Ok)
        self.verticalLayout.addWidget(self.buttonBox)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def getExtent(self):
        return self.extentWidget.outputExtent()

    def getCrs(self):
        return self.extentWidget.outputCrs()

    def accept(self) -> None:
        if self.extentWidget.isValid():
            self.controller.currentFilter.wkt = QgsGeometry.fromRect(self.getExtent()).asWkt()
            self.controller.currentFilter.srsid = self.getCrs().srsid()
            self.controller.refreshFilter()
        super().accept()


FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'ui', 'named_filters_dialog.ui'))


class ManageFiltersDialog(QDialog, FORM_CLASS):
    lineEditActiveFilter: QLineEdit
    listViewNamedFilters: QListWidget
    buttonName: QPushButton
    buttonApply: QPushButton
    buttonDelete: QPushButton
    buttonClose: QPushButton

    def __init__(self, controller, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.controller = controller
        self.setupUi(self)
        self.lineEditActiveFilter.setText(self.controller.currentFilter.name)
        self.lineEditActiveFilter.setReadOnly(True)
        self.setupConnections()
        self.setModel()

    def setupConnections(self):
        self.buttonName.clicked.connect(self.onNameClicked)
        self.buttonApply.clicked.connect(self.onApplyClicked)
        self.buttonDelete.clicked.connect(self.onDeleteClicked)

    def setModel(self):
        self.filterModel = FilterModel()
        self.listViewNamedFilters.setModel(self.filterModel)
        self.listViewNamedFilters.selectionModel().selectionChanged.connect(self.onSelectionChanged)
        self.onSelectionChanged()

    def onSelectionChanged(self):
        hasSelection = self.listViewNamedFilters.selectionModel().hasSelection()
        self.buttonApply.setEnabled(hasSelection)
        self.buttonDelete.setEnabled(hasSelection)

    def onApplyClicked(self):
        selectedIndex = self.listViewNamedFilters.selectedIndexes()[0]
        filterDefinition = self.filterModel.data(index=selectedIndex, role=DataRole)
        filterDefinitionCopy = replace(filterDefinition)
        self.lineEditActiveFilter.setText(filterDefinitionCopy.name)
        self.controller.currentFilter = filterDefinitionCopy
        self.controller.refreshFilter()

    def onDeleteClicked(self):
        selectedIndex = self.listViewNamedFilters.selectedIndexes()[0]
        filterDefinition = self.filterModel.data(index=selectedIndex, role=DataRole)
        FilterManager().deleteFilterDefinition(filterDefinition)
        self.setModel()
        self.controller.refreshFilter()

    def onNameClicked(self):
        currentText = self.lineEditActiveFilter.text()
        text, ok = QInputDialog.getText(self, self.tr('Change Name'), self.tr('New Name:'), echo=QLineEdit.Normal, text=currentText)
        if not ok:
            return
        self.lineEditActiveFilter.setText(text)
        self.controller.currentFilter.name = text
        self.controller.refreshFilter()


class PredicateButton(QPushButton):
    predicateChanged = pyqtSignal(Predicate)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.setObjectName('mPredicateSelectAction')
        self.setToolTip(self.tr('Geometric predicate'))
        self.setIcon(QgsApplication.getThemeIcon('/mActionOptions.svg'))
        self.menu = QMenu(parent=parent)
        self.predicateActionGroup = QActionGroup(self)
        self.predicateActionGroup.setExclusive(True)
        for predicate in Predicate:
            action = QAction(self.menu)
            action.setCheckable(True)
            if predicate == Predicate.INTERSECTS:
                action.setChecked(True)
            action.setText(predicate.name)
            action.predicate = predicate
            action.triggered.connect(self.onPredicateChanged)
            self.predicateActionGroup.addAction(action)
        self.menu.addActions(self.predicateActionGroup.actions())
        self.setMenu(self.menu)
        self.setFlat(True)

    def onPredicateChanged(self):
        self.predicateChanged.emit(self.getPredicate())

    def getPredicate(self) -> Predicate:
        currentAction = self.predicateActionGroup.checkedAction()
        if currentAction:
            return currentAction.predicate


class FilterToolbar(QToolBar):

    def __init__(self, controller: Controller, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.controller = controller
        self.setWindowTitle(self.tr('Filter Toolbar'))
        self.setObjectName('mFilterToolbar')
        self.setupUi()
        self.setupConnections()
        self.onToggled(False)
        self.controller.refreshFilter()

    def setupUi(self):
        self.layout().setSpacing(5)
        self.toggleFilterAction = QAction(self)
        icon = QIcon()
        pixmapOn = QPixmap(os.path.join(os.path.dirname(__file__), "icons", "filter_on.png"))
        pixmapOff = QPixmap(os.path.join(os.path.dirname(__file__), "icons", "filter_off.png"))
        icon.addPixmap(pixmapOn, QIcon.Normal, QIcon.On)
        icon.addPixmap(pixmapOff, QIcon.Normal, QIcon.Off)
        self.toggleFilterAction.setIcon(icon)
        self.toggleFilterAction.setCheckable(True)
        self.addAction(self.toggleFilterAction)

        self.labelFilterName = QLabel(self)
        self.labelFilterName.setFrameShape(QFrame.Panel)
        self.labelFilterName.setFrameShadow(QFrame.Sunken)
        self.labelFilterName.setMinimumWidth(150)
        self.addWidget(self.labelFilterName)

        self.toggleVisibilityAction = QAction(self)
        visibilityIcon = QIcon()
        pixmapOn = QgsApplication.getThemeIcon("/mActionShowAllLayers.svg").pixmap(self.iconSize())
        pixmapOff = QgsApplication.getThemeIcon("/mActionHideAllLayers.svg").pixmap(self.iconSize())
        visibilityIcon.addPixmap(pixmapOn, QIcon.Normal, QIcon.On)
        visibilityIcon.addPixmap(pixmapOff, QIcon.Normal, QIcon.Off)
        self.toggleVisibilityAction.setIcon(visibilityIcon)
        self.toggleVisibilityAction.setCheckable(True)
        self.toggleVisibilityAction.setToolTip(self.tr('Show filter geometry'))
        self.addAction(self.toggleVisibilityAction)

        self.filterFromExtentAction = QAction(self)
        self.filterFromExtentAction.setIcon(QgsApplication.getThemeIcon('/mActionAddBasicRectangle.svg'))
        self.filterFromExtentAction.setToolTip(self.tr('Rectangular filter'))
        self.addAction(self.filterFromExtentAction)

        self.filterFromSelectionAction = QAction(self)
        self.filterFromSelectionAction.setIcon(QgsApplication.getThemeIcon('/mActionAddPolygon.svg'))
        self.filterFromSelectionAction.setToolTip(self.tr('Filter from selected features'))
        self.addAction(self.filterFromSelectionAction)

        self.predicateAction = PredicateButton(self)
        self.addWidget(self.predicateAction)

        self.saveCurrentFilterAction = QAction(self)
        self.saveCurrentFilterAction.setIcon(QgsApplication.getThemeIcon('/mActionFileSave.svg'))
        self.saveCurrentFilterAction.setToolTip(self.tr('Save current filter'))
        self.addAction(self.saveCurrentFilterAction)

        self.manageFiltersAction = QAction(self)
        self.manageFiltersAction.setIcon(QgsApplication.getThemeIcon('/mActionFileOpen.svg'))
        self.manageFiltersAction.setToolTip(self.tr('Manage filters'))
        self.addAction(self.manageFiltersAction)

    def setupConnections(self):
        self.toggleFilterAction.toggled.connect(self.onToggled)
        self.filterFromExtentAction.triggered.connect(self.setFilterFromExtent)
        self.manageFiltersAction.triggered.connect(self.manageFilters)
        self.saveCurrentFilterAction.triggered.connect(self.controller.saveCurrentFilter)
        self.predicateAction.predicateChanged.connect(self.controller.setFilterPredicate)
        self.filterFromSelectionAction.triggered.connect(self.controller.setFilterFromSelection)
        self.controller.nameChanged.connect(self.changeDisplayedName)

    def onToggled(self, checked: bool):
        self.controller.onToggled(checked)
        if checked:
            tooltip = self.tr('Deactivate filter')
        else:
            tooltip = self.tr('Activate filter')
        self.toggleFilterAction.setToolTip(tooltip)

    def changeDisplayedName(self, text: str, isSaved: bool):
        self.labelFilterName.setText(text)
        font = self.labelFilterName.font()
        font.setItalic(not isSaved)
        self.labelFilterName.setFont(font)

    def setFilterFromExtent(self):
        dlg = ExtentDialog(self.controller, parent=self)
        dlg.show()

    def manageFilters(self):
        dlg = ManageFiltersDialog(self.controller, parent=self)
        dlg.exec()




