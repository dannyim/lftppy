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
        self.storage = tempfile.mkdtemp()
        tempfile.NamedTemporaryFile(dir=self.home)

    def _teardown_home(self):
        pass

    def setUp(self):
        self.ftp = None
        self.host = 'localhost'
        self.port = 9001
        self._setup_home()
        authorizer = DummyAuthorizer()
        authorizer.add_user('vagrant', 'vagrant', self.home, perm='elrdfmw')
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

    def test_process_not_running(self):
        ftp = self.ftp
        ftp.kill()
        time.sleep(0.5)
        self.assertRaises(exc.ConnectionError, lambda: ftp.list())

    def test_kill(self):
        ftp = self.ftp
        ftp.kill()
        # need to wait a little bit
        time.sleep(0.5)
        self.assertFalse(ftp.is_running())

    def test_raw(self):
        ftp = self.ftp
        res = ftp.raw("ls -la")
        self.assertEqual(res, "")

    def test_job_ids(self):
        """ ensure jobs are created with the correct ids
        """
        files = []
        for i in range(5):
            f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
            f.file.write(os.urandom(1024*1024*5))
            files.append(f)
        ftp = self.ftp
        ftp.run("set net:limit-rate 1000")
        for f in files:
            fname = f.name
            self.assertTrue(os.path.exists(fname))
            ftp.run("get -O %s %s" % (self.storage, os.path.basename(fname)), True)
            time.sleep(0.5)
        jobs = ftp.jobs
        for idx, job in jobs.iteritems():
            self.assertEqual(idx, job.job_no)

    def test_job_idx(self):
        files = []
        for i in range(2):
            f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
            f.file.write(os.urandom(1024*1024*5))
            files.append(f)
        ftp = self.ftp
        ftp.run("set net:limit-rate 1000")
        commands = []
        for f in files:
            fname = f.name
            self.assertTrue(os.path.exists(fname))
            cmd = "get -O %s %s" % (self.storage, os.path.basename(fname))
            commands.append(cmd)
            ftp.run(cmd, True)
            time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), len(files))
        j0 = ftp.jobs[0]
        j0_txt = j0.text
        self.assertTrue(commands[0] in j0_txt)
        j0_out = ftp.get_output(0)
        self.assertTrue(commands[0] in j0_out)


    def test_kill_single_job(self):
        # add a few big files to download
        f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
        f.file.write(os.urandom(1024 * 1024 * 10))
        ftp = self.ftp
        ls = ftp.list()
        ftp.run("set net:limit-rate 1000")
        ftp.run("get -O %s %s" % (self.storage, os.path.basename(f.name)), True)
        time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), 1)
        ftp.kill(0)
        time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), 0)

    def test_kill_multiple_jobs(self):
        files = []
        for i in range(5):
            f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
            f.file.write(os.urandom(1024*1024*5))
            files.append(f)
        ftp = self.ftp
        ftp.run("set net:limit-rate 1000")
        for f in files:
            fname = f.name
            self.assertTrue(os.path.exists(fname))
            ftp.run("get -O %s %s" % (self.storage, os.path.basename(fname)), True)
            time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), len(files))
        for i in range(len(files)):
            ftp.kill(i)
            time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), 0)

    def test_kill_job_no(self):
        files = []
        for i in range(5):
            f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
            f.file.write(os.urandom(1024*1024*5))
            files.append(f)
        ftp = self.ftp
        ftp.run("set net:limit-rate 1000")
        for f in files:
            fname = f.name
            self.assertTrue(os.path.exists(fname))
            ftp.run("get -O %s %s" % (self.storage, os.path.basename(fname)), True)
            time.sleep(0.5)
        ftp.kill(1)
        time.sleep(0.5)
        self.assertEqual([0, 2, 3, 4], ftp.jobs.keys())
        ftp.kill(2)
        time.sleep(0.5)
        self.assertEqual([0, 3, 4], ftp.jobs.keys())

    def test_mirror(self):
        path = tempfile.mkdtemp(dir=self.home)
        num_files = 5
        for i in range(num_files):
            f = tempfile.NamedTemporaryFile('w+b', dir=path)
            f.file.write(os.urandom(1024 * 1024 * 4))
        ftp = self.ftp
        ftp.run("set net:limit-rate 10000")
        ftp.mirror(os.path.basename(path), self.storage, background=True)
        time.sleep(0.5)
        self.assertEqual(len(os.listdir(self.storage)), 1)
        self.assertEqual(len(ftp.jobs), 1)

    def test_get(self):
        f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
        f.file.write(os.urandom(1024 * 1024 * 5))
        ftp = self.ftp
        ftp.run("set net:limit-rate 10000")
        fname = os.path.basename(f.name)
        target_path = os.path.join(self.storage, fname)
        ftp.get(fname, target_path, delete_src=False, background=True)
        time.sleep(0.5)
        self.assertEqual(len(ftp.jobs), 1)

    def test_get_dir_failure(self):
        d = tempfile.mkdtemp(dir=self.home)
        f = tempfile.NamedTemporaryFile(mode='w+b', dir=d)
        ftp = self.ftp
        dname = os.path.basename(d)
        self.assertRaises(exc.DownloadError,
                          lambda: ftp.get(dname, self.storage, background=True))

    def test_get_delete_src(self):
        f = tempfile.NamedTemporaryFile('w+b', dir=self.home)
        f.file.write(os.urandom(1024 * 1024 * 5))
        ftp = self.ftp
        fname = os.path.basename(f.name)
        target_path = os.path.join(self.storage, fname)
        f.close()
        ftp.get(fname, target_path, delete_src=True, background=True)
        time.sleep(0.5)
        home_ls = os.listdir(self.home)
        self.assertEqual(len(home_ls), 0)


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