import os
import re
from sys import argv
from configparser import ConfigParser

import yaml
from PyQt6.QtWidgets import (
    QPlainTextEdit,
    QApplication, 
    QMessageBox,
    QPushButton,
    QMainWindow,
    QHBoxLayout,
    QVBoxLayout,
    QFileDialog,
    QTabWidget,
    QTreeView,
    QLineEdit,
    QDialog,
    QWidget,
    QMenu,
)

from PyQt6.QtGui import (
    QSyntaxHighlighter,
    QFileSystemModel,
    QTextCharFormat,
    QTextDocument,
    QKeySequence,
    QKeyEvent,
    QColor,
    QFont,
)

from PyQt6.QtCore import (
    QModelIndex,
    QDir,
    Qt,
    pyqtSlot,
)

def loadSettings():
    configParser = ConfigParser()
    configParser.read(os.path.abspath("settings.ini"))
    return configParser

def loadTheme(configParser: ConfigParser):
    themeName = configParser.get('settings', 'theme')
    themePath = os.path.join(os.path.abspath('themes'), "%s.theme" % themeName)

    try:
        with open(themePath, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        QMessageBox(QMessageBox.Icon.Warning, "Warning", "Could not open theme. %s" % themeName).exec()

def loadSyntax(lang: str):
    langPath = os.path.join(os.path.abspath('languages'), "%s.lang" % lang)

    try:
        with open(langPath, 'r') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        QMessageBox(QMessageBox.Icon.Warning, "Warning", "Could not open syntax file. %s" % langPath).exec()
        return {}

class Window:
    X = 160
    Y = 90
    Width = 1600
    Height = 900
    Title = "Harmony Editor"

class BlockState:
    OutsideComment = -1
    InsideComment = 1

class SyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument, theme: dict, language: str):
        QSyntaxHighlighter.__init__(self, document)
        self.theme = theme['syntax']
        self.language = loadSyntax(language)
    
    def isInsideComment(self):
        return self.previousBlockState() == BlockState.InsideComment
    
    def isOutsideComment(self):
        return self.previousBlockState() == BlockState.OutsideComment

    def getFormat(self, ruleType: str):
        if ruleType not in ('keyword', 'operator', 'brace', 'definition', 'string', 'comment', 'special'):
            raise ValueError("Invalid formatting type")
        
        fmt = QTextCharFormat()
        try:
            fmt.setForeground(QColor(self.theme[ruleType]['colour']))
            fmt.setFontItalic(self.theme[ruleType]['italic'])
        except KeyError as error:
            QMessageBox(QMessageBox.Icon.Critical, "Error", "Invalid format").exec()
            raise error

        return fmt

    def highlightBlock(self, text: str):
        keywordFormat = self.getFormat('keyword')
        operatorFormat = self.getFormat('operator')
        braceFormat = self.getFormat('brace')
        specialFormat = self.getFormat('special')
        definitionFormat = self.getFormat('definition')
        stringFormat = self.getFormat('string')
        commentFormat = self.getFormat('comment')

        try:
            keywordRules = [r'\b%s\b' % kw for kw in self.language['keywords']]
            operatorRules = [r'%s' % o for o in self.language['operators']]
            braceRules = [r'%s' % b for b in self.language['braces']]
            definitionRules = [r'\b%s\b\s*(\w+)' % d for d in self.language['definitions']]
            stringRules = [
                r'"[^"\\]*(\\.[^"\\]*)*"',
                r"'[^'\\]*(\\.[^'\\]*)*'"
            ] # strings tend to be the same regardless of language and they are icky to deal with in yml
            specialRules = [r'%s' % s for s in self.language['specials']]
            commentRule = r'%s[^\n]*' % self.language['comment']

            self.searchAndApplyFormatting(text, keywordRules, keywordFormat)
            self.searchAndApplyFormatting(text, operatorRules, operatorFormat)
            self.searchAndApplyFormatting(text, braceRules, braceFormat)
            self.searchAndApplyFormatting(text, specialRules, specialFormat)
            self.searchAndApplyFormatting(text, definitionRules, definitionFormat, 1)
            self.searchAndApplyFormatting(text, stringRules, stringFormat)

            for match in re.finditer(commentRule, text):
                self.setFormat(match.start(), match.end() - match.start(), commentFormat)

        except KeyError:
            QMessageBox(QMessageBox.Icon.Critical, "Error", "Invalid format").exec()
            return
    
    def searchAndApplyFormatting(self, text: str, rules: list[str], format: QTextCharFormat, index: int = 0):
        for rule in rules:
            for match in re.finditer(rule, text):
                self.setFormat(match.start(index), match.end(index) - match.start(index), format)

class TextBox(QPlainTextEdit):
    def __init__(self, theme: dict, language: str):
        QPlainTextEdit.__init__(self)
        self.syntaxHighlighter = SyntaxHighlighter(self.document(), theme, language)
        self.theme = theme

        self.build()
    
    def build(self):
        fontName = self.theme['font']
        self.setFont(QFont(fontName, 16))
        self.configureStyling()

    def configureStyling(self):
        self.setStyleSheet(f"""
            background: {self.theme['editor']['textbox']['background']}
        """)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key == Qt.Key.Key_Tab.value:
            self.insertPlainText('    ')
            return
        return super().keyPressEvent(e)

class Tab(QWidget):
    def __init__(self, theme: dict, filePath: str):
        QWidget.__init__(self)
        self.theme = theme
        self.filePath = filePath
        language = self.filePath.split('.')[1]
        self.body = TextBox(theme, language)

        self.build()

    def build(self):
        self.loadFile()
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.body)
    
    def loadFile(self):
        try:
            with open(self.filePath, 'r') as file:
                self.body.setPlainText(file.read())
        except OSError:
            QMessageBox(QMessageBox.Icon.Critical, "Error", "Cannot open file. %s" % self.filePath).exec()

    def saveFile(self):
        try:
            with open(self.filePath, 'w') as file:
                file.write(self.body.toPlainText())
        except OSError:
            QMessageBox(QMessageBox.Icon.Critical, "Error", "Cannot save file. %s" % self.filePath).exec()

class TabContainer(QTabWidget):
    def __init__(self, theme: dict, settings: ConfigParser):
        QTabWidget.__init__(self)
        self.theme = theme
        self.settings = settings
        self.tabs = []
    
    def openOrCreateTab(self, filePath: str):
        for tab in self.tabs:
            if tab.filePath == filePath:
                self.setCurrentIndex(self.indexOf(tab))
                return
        self.createTab(filePath)
    
    def createTab(self, filePath: str):
        tab = Tab(self.theme, filePath)
        self.addTab(tab, filePath.split('/')[-1])
        self.tabs.append(tab)
        tab.loadFile()
        self.setCurrentIndex(self.indexOf(tab))
    
    def saveTab(self):
        self.widget(self.currentIndex()).saveFile()
    
    def closeTab(self):
        self.saveTab()
        tab = self.indexOf(self.currentWidget())
        self.tabs.pop(tab)
        self.removeTab(self.currentIndex())

class FilePopup(QDialog):
    def __init__(self, path):
        QDialog.__init__(self)
        self.path = path

        self.fileNameInput = QLineEdit()
        self.createFileButton = QPushButton("Create File")
        
        self.build()
    
    def build(self):
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.fileNameInput)
        self.layout().addWidget(self.createFileButton)
        self.createFileButton.clicked.connect(self.createFile)

        self.setWindowTitle("Create File")
    
    def createFile(self):
        with open(os.path.join(self.path, self.fileNameInput.text()), 'x'):
            pass
        self.done(0)
        return os.path.join(self.path, self.fileNameInput.text())

class FolderPopup(QDialog):
    def __init__(self, path: str):
        QDialog.__init__(self)
        self.path = path

        self.folderNameInput = QLineEdit()
        self.createFolderButton = QPushButton("Create Folder")

        self.build()
    
    def build(self):
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(self.folderNameInput)
        self.layout().addWidget(self.createFolderButton)
        self.createFolderButton.clicked.connect(self.createFolder)

        self.setWindowTitle("Create Folder")
    
    def createFolder(self):
        os.mkdir(os.path.join(self.path, self.folderNameInput.text()))
        self.done(0)

class FileTree(QWidget):
    def __init__(self, theme: dict, settings: ConfigParser, tabContainer: TabContainer):
        QWidget.__init__(self)
        self.theme = theme
        self.filePath = settings.get('usage', 'filepath')
        self.tabContainer = tabContainer

        self.model = QFileSystemModel()
        self.tree = QTreeView()

        self.build()

    def build(self):
        self.setLayout(QVBoxLayout())
        self.configureTreeView()
        self.configureStyling()
        
        self.layout().addWidget(self.tree)

    def updateFilePath(self, newFilePath: str):
        self.filePath = newFilePath
        self.configureTreeView()

    def configureStyling(self):
        self.setStyleSheet(f"""
            background: {self.theme['editor']['filemenu']['background']};
        """)

    def configureTreeView(self):
        self.model.setRootPath(self.filePath)
        index = self.model.index(self.model.rootPath())
        self.tree.setModel(self.model)
        self.tree.setRootIndex(index)
        self.tree.clicked.connect(self.treeOnClick)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.customContextMenu)
        for i in range(1, 4):
            self.tree.hideColumn(i)
    
    @pyqtSlot(QModelIndex)
    def treeOnClick(self, index: QModelIndex):
        fileIndex = self.model.index(index.row(), 0, index.parent())
        if self.model.fileInfo(fileIndex).isDir():
            return
        self.tabContainer.openOrCreateTab(self.model.filePath(fileIndex))

    def customContextMenu(self, pos):
        menu = QMenu(self)
        currentIndex = self.tree.currentIndex()

        path = self.model.filePath(currentIndex)
        if path == "":
            path += QDir.currentPath()
        
        if not self.model.isDir(currentIndex):
            baseName = self.model.fileInfo(currentIndex).baseName()
            path = self.model.filePath(currentIndex).split(baseName)[0][:-1]
        
        filePopup = FilePopup(path)
        folderPopup = FolderPopup(path)

        newFileAction = menu.addAction("&New File")
        newFolderAction = menu.addAction("&New Folder")

        selectedAction = menu.exec(self.tree.mapToGlobal(pos))

        if selectedAction == newFileAction:
            filePopup.exec()
        elif selectedAction == newFolderAction:
            folderPopup.exec()

class Harmony(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.configParser = loadSettings()
        self.theme = loadTheme(self.configParser)

        self.mainLayout = QHBoxLayout()
        self.tabContainer = TabContainer(self.theme, self.configParser)
        self.fileTree = FileTree(self.theme, self.configParser, self.tabContainer)

        self.build()
    
    def build(self):
        self.configureLayout()
        self.configureMenu()
        self.configureStyling()
        self.setCentralWidget(QWidget())
        self.centralWidget().setLayout(self.mainLayout)
        self.setWindowTitle(Window.Title)
        self.setGeometry(
            Window.X,
            Window.Y,
            Window.Width,
            Window.Height
        )

    def configureMenu(self):
        self.configureFileMenu()

    def configureFileMenu(self):
        fileMenu = self.menuBar().addMenu("&File")
        newAction = fileMenu.addAction("&New")
        newAction.setShortcut(QKeySequence("Ctrl+N"))

        openAction = fileMenu.addAction("&Open Folder")
        openAction.triggered.connect(self.openFolder)
        openAction.setShortcut(QKeySequence("Ctrl+O"))

        saveAction = fileMenu.addAction("&Save")
        saveAction.triggered.connect(self.tabContainer.saveTab)
        saveAction.setShortcut(QKeySequence("Ctrl+S"))

        closeAction = fileMenu.addAction("&Close")
        closeAction.triggered.connect(self.tabContainer.closeTab)
        closeAction.setShortcut(QKeySequence("Ctrl+W"))

    def openFolder(self):
        path = QFileDialog.getExistingDirectory(self, "Select a Folder", "C:\Harmony")
        self.fileTree.updateFilePath(path)

    def configureLayout(self):
        self.mainLayout.addWidget(self.tabContainer, 4)
        self.mainLayout.addWidget(self.fileTree, 1)

    def configureStyling(self):
        self.setStyleSheet(f"""
            background: {self.theme['editor']['background']};
            color: {self.theme['editor']['text']['colour']};
        """)
        self.menuBar().setStyleSheet(f"""
            background: {self.theme['editor']['menubar']['background']};
        """)

        fontName = self.configParser.get('font', 'name')
        fontSize = int(self.configParser.get('font', 'size'))

        self.setFont(QFont(fontName, fontSize))

def main():
    app = QApplication(argv)
    app.setStyle('Fusion')
    harmony = Harmony()
    harmony.show()
    app.exec()

if __name__ == "__main__":
    main()