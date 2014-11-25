from utils import spawn
from . import exc
from pexpect import EOF, TIMEOUT
import re


class LFTP(object):
    job_id_matcher = re.compile(r'[\s]*\[(\d+)\]')
    def __init__(self, host, port=None, username=None, password=None):
        """

        :param host: The ftp hostname
        :param port: The port for the ftp service
        :param username:
        :param password:
        :return:
        """
        self.host = host
        self.port = port or 21
        self.username = username
        self.password = password
        self.process = None
        self._connect()

    def raw(self, string, timeout=-1):
        if not self.process:
            raise exc.ConnectionError()
        self.send_input(string)
        output = self.get_output(timeout=timeout)
        return output

    def send_bg(self):
        """ Puts the foreground process to the background
        :return:
        """
        self.process.sendcontrol('z')

    @staticmethod
    def parse_jobs(text):
        """ Transforms the result from the 'jobs' lftp command
        to an array of jobs.
        The format of the 'jobs' command for n jobs is:
        [n] text_n
            ...
            text_n
        [n-1] text_n-1
            ...
            text_n-1
        ...
        [1] text_1
            ...
            text_1
        [0] text_0
            ...
            text_0
        :param text: The text to parse
        :return: an array of jobs
        """
        result = {}
        n = -1
        curr_job_text = ""
        for l in text.splitlines():
            matches = LFTP.job_id_matcher.match(l)
            if matches:
                # start with n, decrease to 0
                # start of next item, create the job with the text that we've aggregated
                prev = n
                n = int(matches.group(1))
                if prev != -1:
                    # do not build a job at the start
                    result[n + 1] = Job(curr_job_text)
                # reset the text for the current job
                curr_job_text = l
            else:
                # build the current job text
                curr_job_text += l
        if n >= 0:
            # case for the last item
            result[n] = Job(curr_job_text)
        return result

    @property
    def jobs(self):
        """ Get the status of running jobs
        :return: List of jobs and their current state
        """
        jobs_output = self.run("jobs")
        # parse jobs output and put into array
        result = self.parse_jobs(jobs_output)
        return result

    def run(self, cmd, background=False):
        """
        :param cmd: The command to run on the ftp site
        :param background: run the command in the background
        :return:
        """
        if not self.process:
            raise exc.ConnectionError()
        if background:
            cmd += " &"
        self.send_input(cmd)
        output = self.get_output()
        return output

    def _connect(self):
        """
        Attempt to connect to ftp server
        :return:
        :raises: exc.ConnectionError, exc.LoginError
        """
        cmd = ['lftp']
        cmd += ['-p', str(self.port)]
        cmd += ['-u', "%s,%s" % (self.username, self.password), self.host]
        process = spawn(" ".join(cmd))
        self.process = process
        # ensure that we can connect
        index = self.process.expect(["lftp .*", EOF])
        output = self.process.before
        if index == 0:
            output = output + self.process.after
        if "Name or service not known" in output:
            raise exc.ConnectionError(output)
        # ensure that we are logged in
        # We do this by trying to send a command and
        # testing to see if there's a login error
        self.process.sendline("ls")
        index = self.process.expect(["ls .*", EOF, TIMEOUT], timeout=1)
        output = self.process.before
        if "Login failed" in output:
            raise exc.LoginError(output)

    def disconnect(self):
        self.process.terminate()

    def send_input(self, line):
        self.process.sendline(line)

    def get_output(self, job_id=None, timeout=-1):
        """ Assumes successful connection to the ftp server
        :param job_id:
        :param timeout:
        :return: The latest output of the job with id job_id,
                or the current foreground process if no job_id is given
        """
        if not job_id:
            self.process.expect("lftp .*>", timeout=timeout)
            return self.process.before
        else:
            return self.jobs[job_id]

    def list(self, options=None):
        cmd = ['ls', '-la']
        return self.run(" ".join(cmd))

    def get(self, rfile, lfile, delete_src=False, delete_target=False, mode="binary"):
        pass

    def mirror(self, source, target, parallel=None):
        """

        :param source:
        :param target:
        :param parallel:
        :return:
        """
        cmd = ['mirror', source, target]
        if parallel:
            cmd += [str(parallel)]
        self.process.sendline(" ".join(cmd))


class Job(object):
    def __init__(self, text):
        self.text = text
        self.parse(text)

    def parse(self, text):
        pass
