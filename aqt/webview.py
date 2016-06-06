# Copyright: Damien Elmes <anki@ichi2.net>
# -*- coding: utf-8 -*-
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import sys
from anki.hooks import runHook
from aqt.qt import *
from aqt.utils import openLink
from anki.utils import isMac, isWin
import anki.js

# Page for debug messages
##########################################################################

class AnkiWebPage(QWebEnginePage):

    def __init__(self, onBridgeCmd):
        QWebEnginePage.__init__(self)
        self._onBridgeCmd = onBridgeCmd
        self._setupBridge()

    def _setupBridge(self):
        class Bridge(QObject):
            @pyqtSlot(str)
            def cmd(self, str):
                self.onCmd(str)

        self._bridge = Bridge()
        self._bridge.onCmd = self._onCmd

        self._channel = QWebChannel(self)
        self._channel.registerObject("py", self._bridge)
        self.setWebChannel(self._channel)

        js = QFile(':/qtwebchannel/qwebchannel.js')
        assert js.open(QIODevice.ReadOnly)
        js = bytes(js.readAll()).decode('utf-8')

        script = QWebEngineScript()
        script.setSourceCode(js + '''
            var pycmd;
            new QWebChannel(qt.webChannelTransport, function(channel) {
                pycmd = channel.objects.py.cmd;
                pycmd("domDone");
            });
        ''')
        script.setWorldId(QWebEngineScript.MainWorld)
        script.setInjectionPoint(QWebEngineScript.DocumentReady)
        script.setRunsOnSubFrames(False)
        self.profile().scripts().insert(script)

    def javaScriptConsoleMessage(self, lvl, msg, line, srcID):
        sys.stdout.write(
            (_("JS error on line %(a)d: %(b)s") %
             dict(a=line, b=msg+"\n")))

    def acceptNavigationRequest(self, url, navType, isMainFrame):
        # load all other links in browser
        openLink(url)
        return False

    def _onCmd(self, str):
        self._onBridgeCmd(str)

# Main web view
##########################################################################

class AnkiWebView(QWebEngineView):

    def __init__(self, canFocus=True):
        QWebEngineView.__init__(self)
        self.setObjectName("mainText")
        self._page = AnkiWebPage(self._onBridgeCmd)

        self._loadFinishedCB = None
        self.setPage(self._page)
        self.resetHandlers()
        self.allowDrops = False
        # reset each time new html is set; used to detect if still in same state
        self.key = None
        self.setCanFocus(canFocus)

    def keyPressEvent(self, evt):
        if evt.matches(QKeySequence.Copy):
            self.triggerPageAction(QWebEnginePage.Copy)
            evt.accept()
        # work around a bug with windows qt where shift triggers buttons
        if isWin and evt.modifiers() & Qt.ShiftModifier and not evt.text():
            evt.accept()
            return
        QWebEngineView.keyPressEvent(self, evt)

    def keyReleaseEvent(self, evt):
        if self._keyHandler:
            if self._keyHandler(evt):
                evt.accept()
                return
        QWebEngineView.keyReleaseEvent(self, evt)

    def contextMenuEvent(self, evt):
        if not self._canFocus:
            return
        m = QMenu(self)
        a = m.addAction(_("Copy"))
        a.triggered.connect(lambda: self.triggerPageAction(QWebEnginePage.Copy))
        runHook("AnkiWebView.contextMenuEvent", self, m)
        m.popup(QCursor.pos())

    def dropEvent(self, evt):
        pass

    def setKeyHandler(self, handler=None):
        # handler should return true if event should be swallowed
        self._keyHandler = handler

    def setHtml(self, html):
        self.key = None
        app = QApplication.instance()
        oldFocus = app.focusWidget()
        self._page.setHtml(html)
        # work around webengine stealing focus on setHtml()
        if oldFocus:
            oldFocus.setFocus()

    def stdHtml(self, body, css="", bodyClass="", js=None, head=""):
        if isMac:
            button = "font-weight: bold; height: 24px;"
        else:
            button = "font-weight: normal;"

        screen = QApplication.desktop().screen()
        dpi = screen.logicalDpiX()
        zoomFactor = max(1, dpi / 96.0)

        self.setHtml("""
<!doctype html>
<html><head><style>
body { zoom: %f; }
button {
%s
}
%s</style>
<script>
%s
</script>
%s

</head>
<body class="%s">%s</body></html>""" % (
    zoomFactor, button, css, js or anki.js.jquery+anki.js.browserSel,
    head, bodyClass, body))

    def setCanFocus(self, canFocus=False):
        self._canFocus = canFocus
        if self._canFocus:
            self.setFocusPolicy(Qt.WheelFocus)
        else:
            self.setFocusPolicy(Qt.NoFocus)

    def eval(self, js):
        self.page().runJavaScript(js)

    def _openLinksExternally(self, url):
        openLink(url)

    def _onBridgeCmd(self, cmd):
        if cmd == "domDone":
            self.onLoadFinished()
        else:
            self.onBridgeCmd(cmd)

    def defaultOnBridgeCmd(self, cmd):
        print("unhandled bridge cmd:", cmd)

    def defaultOnLoadFinished(self):
        pass

    def resetHandlers(self):
        self.setKeyHandler(None)
        self.onBridgeCmd = self.defaultOnBridgeCmd
        self.onLoadFinished = self.defaultOnLoadFinished
