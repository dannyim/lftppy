import unittest
import sure
from lftppy import lftp
from lftppy import exc
from ftplib import FTP
from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import threading
import tempfile
import os
import time


class FTPServerBase(unittest.TestCase):
    def _run_ftp_server(self):
        self.server.serve_forever()

    def _setup_home(self):
        """ Initialize the temporary homedir of the test user
        """
        self.home = tempfile.mkdtemp()
        tempfile.NamedTemporaryFile(dir=self.home)

    def _teardown_home(self):
        pass

    def setUp(self):
        self.ftp = None
        self.host = 'localhost'
        self.port = 9001
        self._setup_home()
        authorizer = DummyAuthorizer()
        authorizer.add_user('vagrant', 'vagrant', self.home)
        authorizer.add_anonymous(self.home)
        handler = FTPHandler
        handler.authorizer = authorizer
        self.server = FTPServer((self.host, self.port), handler)
        # run ftp server in a separate thread so as to not block tests from running
        self.thread = threading.Thread(target=self._run_ftp_server)
        self.thread.daemon = True
        self.thread.start()
        self.ftp = lftp.LFTP(self.host, self.port, 'vagrant', 'vagrant')

    def tearDown(self):
        if self.ftp:
            self.ftp.disconnect()
        self.server.close_all()
        self._teardown_home()

    def test_empty_homedir(self):
        ftp = self.ftp
        # listing of an empty directory
        ls = ftp.list()
        self.assertEqual(ls, "")

    def test_dir(self):
        ftp = self.ftp
        tempdir = tempfile.mkdtemp(dir=self.home)
        ls = ftp.list()
        ls.should.contain(os.path.basename(tempdir))


class LFTPInvalidTest(unittest.TestCase):
    def test_bad_host(self):
        hostname = "does_not_exist"
        self.assertRaises(exc.ConnectionError, lambda: lftp.LFTP(hostname))

    def test_bad_login(self):
        hostname = 'ftp.openbsd.org'
        user = 'anon'
        pw = 'test@example.org'
        self.assertRaises(exc.LoginError,
                          lambda: lftp.LFTP(hostname, username=user, password=pw))


class LFTPTest(FTPServerBase):
    def test_disconnect(self):
        ftp = self.ftp
        self.assertTrue(ftp.is_running())
        ftp.disconnect()
        self.assertFalse(ftp.is_running())

    def test_reconnect(self):
        ftp = self.ftp
        ftp.disconnect()
        ftp.reconnect()
        self.assertTrue(ftp.is_running())

    def test_kill(self):
        ftp = self.ftp
        ftp.kill()
        # need to wait a little bit
        time.sleep(0.5)
        self.assertFalse(ftp.is_running())


class JobParserTest(unittest.TestCase):
    def test_empty(self):
        results = lftp.LFTP.parse_jobs("")
        self.assertEqual(results, {})

    def test_single(self):
        text = """
[0] mirror zaurus  -- 142k/195M (0%) 69.1 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 89060 (0%) [Receiving data]
        """
        results = lftp.LFTP.parse_jobs(text)
        self.assertEqual(len(results), 1)

    def test_multiple(self):
        text = """
[1] mirror vax
    Getting files information (40%) [Waiting for response...]
[0] mirror zaurus  -- 317k/195M (0%) 19.3 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 265720 (0%) 19.3K/s eta:50m [Receiving data]
        """
        results = lftp.LFTP.parse_jobs(text)
        self.assertEqual(len(results), 2)

    def test_subtasks(self):
        text = """
[2] mirror -P 3 sparc  -- 2.2M/201M (1%) 622.2 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 2001660 (3%) 583.8K/s eta:92s [Receiving data]
\\transfer `boot.net'
    `boot.net' at 48180 (77%) [Receiving data]
\\transfer `bootxx'
    `bootxx' at 0 (0%) [Waiting for response...]
[1] mirror vax  -- 2.8M/754M (0%) 4.3 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 2666446 (2%) eta:42m [Receiving data]
[0] mirror zaurus  -- 4.4M/195M (2%) 3.6 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 4334242 (7%) eta:17m [Receiving data]
        """
        results = lftp.LFTP.parse_jobs(text)
        self.assertEqual(len(results), 3)
        # todo test subtask creation

    def test_done(self):
        text = """
[0] Done (mirror -P 3 sparc)
    Total: 1 directory, 23 files, 0 symlinks
    New: 23 files, 0 symlinks
    200391421 bytes transferred in 367 seconds (533.8 KiB/s)
        """.lstrip()
        results = lftp.LFTP.parse_jobs(text)
        # todo test job status

    def test_in_progress(self):
        text = """
[1] mirror vax
    Getting files information (40%) [Waiting for response...]
[0] mirror zaurus  -- 317k/195M (0%) 19.3 KiB/s
\\transfer `base55.tgz'
    `base55.tgz' at 265720 (0%) 19.3K/s eta:50m [Receiving data]
        """
        results = lftp.LFTP.parse_jobs(text)
        # todo test job in progress