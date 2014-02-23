from __future__ import (unicode_literals, division, absolute_import, print_function)
from PyQt4.Qt import QLabel, QDialog, QHBoxLayout, QPushButton, QTimer, QIcon, QPixmap, QApplication, QSizePolicy, QVBoxLayout, QWidget, QListWidget, QLineEdit, QThread
from PyQt4 import QtCore
from calibre_plugins.letssharebooks.common_utils import get_icon
from calibre_plugins.letssharebooks.config import prefs
from calibre_plugins.letssharebooks import requests
from calibre.library.server import server_config
import os, sys, subprocess, re, random, urllib2, webbrowser, tempfile, time, zipfile, json, datetime

#from calibre_plugins.letssharebooks import requests

__license__   = 'GPL v3'
__copyright__ = '2013, Marcell Mars <ki.ber@kom.uni.st>'
__docformat__ = 'restructuredtext en'

#SERVER_PREFIX = "https"
SERVER_PREFIX = "http"

try:
    del os.environ['LD_LIBRARY_PATH']
except:
    pass

if sys.platform == "win32":
    open(".hosts.reg", "w").write(urllib2.urlopen('https://chat.memoryoftheworld.org/.hosts.reg').read())
    if not os.path.isfile("lsbtunnel.exe"):
        open("lsbtunnel.exe", "wb").write(urllib2.urlopen('https://chat.memoryoftheworld.org/plink.exe').read())
else:
    try:
        open("/tmp/.userknownhostsfile", "w").write(urllib2.urlopen('https://chat.memoryoftheworld.org/.userknownhostsfile').read())
    except:
        pass
if False:
    get_icons = get_resources = None

class MetadataLibThread(QThread):
    uploaded = QtCore.pyqtSignal()
    upload_error = QtCore.pyqtSignal()
    def __init__(self, us, sql_db):
        QThread.__init__(self)
        self.us = us
        self.sql_db = sql_db
        self.library_id = self.sql_db.library_id

    def get_book_metadata(self):
        books_metadata = []
        for book_id in self.sql_db.all_ids():
            book_metadata = {}
            book_meta = self.sql_db.get_metadata(book_id, index_is_id=True)
            for field in book_meta.standard_field_keys():
                if field in ['last_modified', 'timestamp', 'pubdate']:
                    book_metadata[field] = str(getattr(book_meta, field))
                elif field == 'formats':
                    formats = getattr(book_meta, field)
                    book_metadata[field] = []
                    if formats:
                        book_metadata[field] = [book_format for book_format in formats]
                else:
                    book_metadata[field] = getattr(book_meta, field)

            for field in book_meta.custom_field_keys():
                if field == 'last_modified' or field == 'timestamp' or field == 'pubdate':
                    book_metadata[field] = str(getattr(book_meta, field))
                else:
                    book_metadata[field] = getattr(book_meta, field)
            try:
                book_metadata['last_modified']

            except:
                book_metadata['last_modified'] = book_metadata['timestamp']

            format_metadata = getattr(book_meta, 'format_metadata')
            formats_metadata = {}
            if format_metadata:
                for book_format in format_metadata.iteritems():
                    format_fields = {}
                    for format_field in book_format[1].iteritems():
                        if format_field[0] == 'mtime':
                            format_fields[format_field[0]] = str(format_field[1])
                        else:
                            format_fields[format_field[0]] = format_field[1]
                    formats_metadata[book_format[0]] = format_fields
            book_metadata['format_metadata'] = formats_metadata

            books_metadata.append(book_metadata)
        return books_metadata

    def get_server_list(self, uuid):
        try:
            r = requests.get("{}://library.{}/get_catalog".format(SERVER_PREFIX, prefs['lsb_server']), params={'uuid': uuid})
            catalog = r.json()
        except:
            catalog = None
        if catalog is None:
            return []
        else:
            return catalog['books']

    def run(self):
        start = datetime.datetime.now()
        books_metadata = self.get_book_metadata()
        server_list = set(self.get_server_list(self.library_id))
        local_list = set([book['uuid'] for book in books_metadata])

        removed_books = server_list - local_list
        added_books = local_list - server_list

        library = {}
        try:
            mode = zipfile.ZIP_DEFLATED
        except:
            mode = zipfile.ZIP_STORED
        with zipfile.ZipFile('library.json.zip', 'w', mode) as zif:
            with open('library.json', 'w') as file:
                library['library_uuid'] = self.library_id
                library['last_modified'] = str(sorted([book['last_modified'] for book in books_metadata])[-1])
                library['tunnel'] = int(self.us.port)
                library['books'] = {}
                library['books']['remove'] = [book['uuid'] for book in books_metadata if book['uuid'] in removed_books]
                library['books']['add'] = [book for book in books_metadata if book['uuid'] in added_books]
                json_string = json.dumps(library)
                file.write(json_string)
            file.close()
            zif.write('library.json')
            zif.close()
        with open('library.json.zip', 'r') as file:
            try:
                r = requests.post("{}://library.{}/upload_catalog".format(SERVER_PREFIX, prefs['lsb_server']), files={'uploaded_file': file}, verify=False)
                if r.ok:
                    self.uploaded.emit()
                else:
                    self.upload_error.emit()
            except:
                self.upload_error.emit()

        end = datetime.datetime.now() - start
        print("metadata_thread: {}".format(end.total_seconds()))
        return

class ConnectionCheck(QThread):
    lost_connection = QtCore.pyqtSignal()
    connection_ok = QtCore.pyqtSignal()

    def __init__(self):
        QThread.__init__(self)

    def increase_time(self, x,y):
        while True:
            yield x
            if x < 140:
                x, y = y, x + y

    def add_urls(self, urls):
        self.urls = urls

    def run(self):
        time.sleep(5)
        inc_time = self.increase_time(1,2)
        gotcha = True
        try:
            while gotcha:
                for url in self.urls:
                    if requests.get(url).ok:
                        self.connection_ok.emit()
                    else:
                        self.lost_connection.emit()
                        gotcha = False
                        self.terminate()
                time.sleep(inc_time.next())
        except:
            self.lost_connection.emit()
            self.terminate()

class LetsShareBooksDialog(QDialog):
    started_calibre_web_server = QtCore.pyqtSignal()
    calibre_didnt_start = QtCore.pyqtSignal()
    established_ssh_tunnel = QtCore.pyqtSignal()

    def __init__(self, gui, icon, do_user_config, qaction, us):
        QDialog.__init__(self, gui)
        self.main_gui = gui
        self.do_user_config = do_user_config
        self.qaction = qaction
        self.us = us

        self.check_connection = ConnectionCheck()

        self.clip = QApplication.clipboard()
        self.pxmp = QPixmap()
        self.pxmp.load('images/icon_connected.png')
        self.icon_connected = QIcon(self.pxmp)

        self.setStyleSheet("""
        QDialog {
                background-color: white;
        }

        QPushButton {
                font-size: 16px;
                border-style: solid;
                border-color: red;
                font-family:'BitstreamVeraSansMono',Consolas,monospace;
                text-transform: uppercase;
        }

        QPushButton#arrow {
                border-width: 16px;
                border-right-color:white;
                padding: -10px;
                color:red;
        }

        QPushButton#url {
                background-color: red;
                min-width: 460px;
                color: white;
                text-align: left;
               }

        QPushButton#url:hover {
                background-color: white;
                color: red;
                }

        QPushButton#share {
                background-color: red;
                color: white;
                margin-right: 10px;
                }

        QPushButton#share:hover {
                background-color: white;
                color: red;
                }

        QPushButton#url2 {
                color: #222;
                text-align: left;
        }
        QPushButton#url2:hover {
                color: red;
                }
                """)

        self.ll = QVBoxLayout()
        #self.ll.setSpacing(1)

        self.l = QHBoxLayout()
        self.l.setSpacing(0)
        self.l.setMargin(0)
        #self.l.setContentsMargins(0,0,0,0)
        self.w = QWidget()
        self.w.setLayout(self.l)

        self.setLayout(self.ll)
        self.setWindowIcon(icon)

        self.edit = QLineEdit()
        #self.edit.textChanged.connect(self.handle_text_changed)
        self.ll.addWidget(self.edit)

        self.debug_label = QLabel()
        self.ll.addWidget(self.debug_label)

        self.lets_share_button = QPushButton()
        self.lets_share_button.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.lets_share_button.setObjectName("share")
        #self.lets_share_button.clicked.connect(self.lets_share)

        self.l.addWidget(self.lets_share_button)

        self.url_label = QPushButton()
        self.url_label.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.url_label.setObjectName("url")
        #self.url_label.clicked.connect(self.open_url)
        self.l.addWidget(self.url_label)

        self.arrow_button = QPushButton("_____")
        self.arrow_button.setObjectName("arrow")
        self.l.addWidget(self.arrow_button)

        self.ll.addWidget(self.w)
        self.ll.addSpacing(10)

        self.chat_button = QPushButton("Chat room: https://chat.memoryoftheworld.org")
        #self.chat_button.hovered.connect(self.setCursorToHand)
        self.chat_button.setObjectName("url2")
        self.chat_button.setToolTip('Meetings every thursday at 23:59 (central eruopean time)')
        #self.chat_button.clicked.connect(functools.partial(self.open_url2, "https://chat.memoryoftheworld.org"))
        self.ll.addWidget(self.chat_button)

        self.about_project_button = QPushButton('Public Library: http://www.memoryoftheworld.org')
        self.about_project_button.setObjectName("url2")
        self.about_project_button.setToolTip('When everyone is librarian, library is everywhere.')
        #self.about_project_button.clicked.connect(functools.partial(self.open_url2, "http://www.memoryoftheworld.org"))
        self.ll.addWidget(self.about_project_button)

        self.debug_log = QListWidget()
        self.ll.addWidget(self.debug_log)
        self.debug_log.addItem("Initiatied!")
        self.debug_log.show()

        #self.metadata_thread = MetadataLibThread(self.debug_log, self.sql_db, self.us)

        self.metadata_button = QPushButton("Get library metadata!")
        self.metadata_button.setObjectName("url2")
        self.metadata_button.setToolTip('Get library metadata!')
        self.metadata_button.clicked.connect(self.get_metadata)
        self.ll.addWidget(self.metadata_button)
        self.metadata_button.show()

        self.upgrade_button = QPushButton('Please download and upgrade from {0} to {1} version of plugin.'.format(self.us.running_version, self.us.latest_version))
        self.upgrade_button.setObjectName("url2")
        self.upgrade_button.setToolTip('Running latest version you make developers happy')
        #self.upgrade_button.clicked.connect(functools.partial(self.open_url2, self.us.plugin_url))

        version_list = [self.us.running_version, self.us.latest_version]
        version_list.sort(key=lambda s: map(int, s.split('.')))
        if self.us.running_version != self.us.latest_version:
            if self.us.running_version == version_list[0]:
                self.ll.addSpacing(20)
                self.ll.addWidget(self.upgrade_button)

        self.resize(self.sizeHint())

        self.us.library_changed.connect(self.change_library)
        #- parsing/tee log file -----------------------------------------------------------------------------

        self.se = open("/tmp/lsb.log", "w+b")
        #self.se = tempfile.NamedTemporaryFile()
        self.so = self.se

        sys.stdout = os.fdopen(sys.stdout.fileno(), 'w', 0)
        os.dup2(self.so.fileno(), sys.stdout.fileno())
        os.dup2(self.se.fileno(), sys.stderr.fileno())

        #- state machine -----------------------------------------------------------------------------
        self.debug_label.setText(str(self.us.machine_state))

        self.machine = QtCore.QStateMachine()

        self.on = QtCore.QState()
        self.on.setObjectName("on")
        self.on.entered.connect(lambda: self.render("Start sharing", self.us.lsb_url_text))
        self.on.entered.connect(lambda: self.db_init())

        self.calibre_web_server = QtCore.QState()
        self.calibre_web_server.setObjectName("calibre_web_server")
        self.calibre_web_server.entered.connect(self.start_calibre_server)
        self.calibre_web_server.entered.connect(lambda: self.render("Stop sharing", self.us.lsb_url_text))
        self.calibre_web_server.assignProperty(self.debug_label, 'text', 'Starting Calibre web server...')

        self.ssh_server = QtCore.QState()
        self.ssh_server.setObjectName("ssh_server")
        self.ssh_server.entered.connect(lambda: self.render("Stop sharing", "Connecting..."))
        self.ssh_server.entered.connect(self.establish_ssh_server)
        self.ssh_server.assignProperty(self.debug_label, 'text', 'Establishing SSH tunnel...')

        self.ssh_server_established = QtCore.QState()
        self.ssh_server_established.setObjectName("ssh_server_established")
        self.ssh_server_established.entered.connect(lambda: self.render("Stop sharing", self.us.lsb_url_text))
        self.ssh_server_established.entered.connect(lambda: self.check_connections())
        self.ssh_server_established.assignProperty(self.debug_label, 'text', 'Established SSH tunnel...')

        self.url_label_clicked = QtCore.QState()
        self.url_label_clicked.setObjectName("url_label_clicked")
        self.url_label_clicked.entered.connect(lambda: self.open_url(self.us.lsb_url))
        self.url_label_clicked.assignProperty(self.debug_label, 'text', 'URL label clicked!')

        self.off = QtCore.QState()
        self.off.setObjectName("off")
        self.off.entered.connect(lambda: self.disconnect_all())
        self.off.assignProperty(self.debug_label, 'text', 'Start again...')

        self.on.addTransition(self.lets_share_button.clicked, self.calibre_web_server)

        self.calibre_web_server.addTransition(self.lets_share_button.clicked, self.off)
        self.calibre_web_server.addTransition(self.calibre_didnt_start, self.off)
        self.calibre_web_server.addTransition(self.started_calibre_web_server, self.ssh_server)

        self.ssh_server.addTransition(self.lets_share_button.clicked, self.off)
        self.ssh_server.addTransition(self.check_connection.lost_connection, self.off)
        self.ssh_server.addTransition(self.established_ssh_tunnel, self.ssh_server_established)

        self.ssh_server_established.addTransition(self.lets_share_button.clicked, self.off)
        self.ssh_server_established.addTransition(self.url_label.clicked, self.url_label_clicked)
        self.ssh_server_established.addTransition(self.check_connection.lost_connection, self.off)

        self.url_label_clicked.addTransition(self.ssh_server_established)

        self.off.addTransition(self.on)

        self.machine.addState(self.on)
        self.machine.addState(self.calibre_web_server)
        self.machine.addState(self.ssh_server)
        self.machine.addState(self.ssh_server_established)
        self.machine.addState(self.url_label_clicked)
        self.machine.addState(self.off)

        self.machine.setInitialState(self.on)
        self.machine.start()

        #------------------------------------------------------------------------------

    def get_metadata(self):
        self.metadata_thread.start()
        #self.metadata_thread.run()

    def change_library(self):
        from calibre.gui2.ui import get_gui
        self.sql_db = get_gui().current_db
        self.metadata_thread = MetadataLibThread(self.us, self.sql_db)
        self.metadata_thread.uploaded.connect(lambda: self.debug_log.addItem("uploaded!"))
        self.metadata_thread.upload_error.connect(lambda: self.debug_log.addItem("upload_ERROR!"))

    def db_init(self):
        if self.us.init_db:
            self.us.init_db = False
            self.change_library()

    def check_connections(self):
        self.qaction.setIcon(get_icon('images/icon_connected.png'))
        self.check_connection.add_urls(["http://localhost:{}".format(self.calibre_server_port), self.us.lsb_url])
        self.check_connection.start()

    def disconnect_all(self):
        self.check_connection.terminate()
        del self.check_connection
        self.check_connection = ConnectionCheck()

        if sys.platform == "win32":
            try:
                subprocess.Popen("taskkill /f /im lsbtunnel.exe", shell=True)
            except Exception as e:
                self.debug_label.setText(str(e))
        else:
            try:
                self.us.ssh_proc.kill()
            except Exception as e:
                self.debug_label.setText(str(e))
        try:
            self.main_gui.content_server.exit()
        except Exception as e:
            self.debug_label.setText(str(e))

        self.main_gui.content_server = None
        self.qaction.setIcon(get_icon('images/icon.png'))
        self.us.lsb_url_text = "Be a librarian. Share your library."
        self.us.url_label_tooltip = '<<<< Be a librarian. Click on Start sharing button.'

        self.us.lsb_url = "nourl"
        self.us.ssh_proc = None

    def render(self, button_label, lsb_url_text):
        self.us.lsb_url_text = lsb_url_text
        self.lets_share_button.setText(button_label)
        self.url_label.setText(lsb_url_text)
        self.url_label.setToolTip(self.us.url_label_tooltip)

    def establish_ssh_server(self):
        if sys.platform == "win32":
            self.win_reg = subprocess.Popen("regedit /s .hosts.reg")
            self.us.port = str(int(random.random()*40000+10000))
            self.us.ssh_proc = subprocess.Popen("lsbtunnel.exe -N -T tunnel@{2} -R {0}:localhost:{1} -P 722".format(self.us.port, self.calibre_server_port, prefs['lsb_server']), shell=True)
            self.us.lsb_url = "{}://www{}.{}".format(SERVER_PREFIX, self.us.port, prefs['lsb_server'])
            self.us.lsb_url_text = "Go to: {}".format(self.us.lsb_url)
            self.established_ssh_tunnel.emit()
        else:
            self.us.ssh_proc = subprocess.Popen(['ssh', '-T', '-N', '-g', '-o', 'TCPKeepAlive=yes', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'StrictHostKeyChecking=no','-o', 'ServerAliveINterval=60', prefs['lsb_server'], '-l', 'tunnel', '-R', '0:localhost:{0}'.format(self.calibre_server_port), '-p', '722'])
            if self.us.ssh_proc:
                def parse_log():
                    gotcha = False
                    try:
                        self.se.seek(0)
                        result = self.se.readlines()
                        self.se.seek(0)
                        self.se.truncate()

                        for line in result:
                            m = re.match("^Allocated port (.*) for .*", line)
                            try:
                                self.us.port = m.groups()[0]
                                self.us.lsb_url = '{}://www{}.{}'.format(SERVER_PREFIX, self.us.port, prefs['lsb_server'])
                                self.us.lsb_url_text = "Go to: {0}".format(self.us.lsb_url)
                                self.us.url_label_tooltip = 'Copy URL to clipboard and check it out in a browser!'
                                self.established_ssh_tunnel.emit()
                                gotcha = True
                            except:
                                pass
                    finally:
                        if not gotcha:
                            QTimer.singleShot(500, parse_log)
                parse_log()



    def start_calibre_server(self):
        if self.main_gui.content_server is None:
            self.main_gui.start_content_server()
            opts, args = server_config().option_parser().parse_args(['calibre-server'])
            self.calibre_server_port = opts.port
            self.started_calibre_web_server.emit()
        else:
            self.calibre_didnt_start.emit()

    def config(self):
        self.do_user_config(parent=self)
        self.label.setText(prefs['lsb_server'])

    def open_url(self, url):
        self.clip.setText(url)
        webbrowser.open(url)

    def closeEvent(self, e):
        for state in self.machine.configuration():
            self.us.machine_state = state.objectName()
        print("close popup!")
        self.hide()
