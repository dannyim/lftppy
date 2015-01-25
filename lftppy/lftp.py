from utils import spawn
from . import exc
from pexpect import EOF, TIMEOUT
import re


class LFTP(object):

    # matches [n] where n is an integer
    job_id_matcher = re.compile(r'[\s]*\[(\d+)\]')
    # default lftp prompt
    prompt = "lftp .*?>"

    def __init__(self, host, port=None, username=None, password=None, **opts):
        """

        :param host: The ftp hostname
        :param port: The port for the ftp service
        :param username:
        :param password:
        :param opts: configuration for the lftp program
        :return:
        """
        self.host = host
        self.port = port or 21
        self.username = username
        self.password = password
        self.process = None
        self.last_cmd = None
        self.opts = opts
        self._connect(**opts)

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
        :return: a dictionary of jobs
        """
        result = {}
        n = -1
        curr_job_text = ""
        for line in text.splitlines():
            matches = LFTP.job_id_matcher.match(line)
            if matches:
                # start of next item, create the job with the text that we've aggregated
                prev = n
                n = int(matches.group(1))
                if prev != -1:
                    # do not build a job at the start
                    result[prev] = Job(prev, curr_job_text)
                # reset the text for the current job
                curr_job_text = line
            else:
                # build the current job text
                curr_job_text += line
        if n >= 0:
            # case for the last item
            result[n] = Job(n, curr_job_text)
        return result

    @property
    def jobs(self):
        """ Get the status of running jobs
        :return: dictionary of jobs and their current state
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
        if not self.is_running():
            raise exc.ConnectionError()
        if background:
            cmd += " &"
        self.send_input(cmd)
        output = self.get_output()
        return output

    def _connect(self, **opts):
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
        index = self.process.expect([self.prompt, EOF])
        output = self.process.before
        if index == 0:
            output = output + self.process.after
        if "Name or service not known" in output:
            raise exc.ConnectionError(output)
        # ensure that we are logged in
        # We do this by trying to send a command and
        # testing to see if there's a login error
        self.process.sendline("ls -la")
        index = self.process.expect([self.prompt, EOF, TIMEOUT])
        output = self.process.before
        if "Login failed" in output:
            raise exc.LoginError(output)

    def is_running(self):
        return self.process.isalive()

    def kill(self, job_no=None):
        """ kills the job if job_no is given, or kill the child process
        :param job_no:
        :return:
        """
        if job_no is not None:
            self.run("kill %d" % job_no)
        else:
            self.process.kill(9)

    def reconnect(self):
        self.last_cmd = None
        self._connect(**self.opts)

    def disconnect(self):
        self.process.terminate(force=True)

    def send_input(self, line):
        self.last_cmd = line
        self.process.sendline(line)

    @staticmethod
    def _check_for_errors(output):
        if "Access failed: 550" in output:
            raise exc.DownloadError(output)

    def _process_cmd_output(self, result):
        """ Strip out the command from the output.  Detect any errors.
        :param result:
        :return:
        """
        last_cmd = self.last_cmd
        bg_char_idx = last_cmd.rfind("&")
        if bg_char_idx > 0:
            last_cmd = last_cmd[:bg_char_idx]
        regex = "\s*(%s)\s*(.*)" % re.escape(last_cmd)
        self._check_for_errors(result)
        match = re.match(regex, result, re.DOTALL)
        if not match:
            # TODO(minadyn@gmail.com) raise an error if the command wasn't in the output?
            return result
        else:
            return match.group(2)

    def get_output(self, job_id=None, timeout=-1):
        """ Assumes successful connection to the ftp server
        :param job_id:
        :param timeout:
        :return: The latest output of the job with id job_id,
                or the current foreground process if no job_id is given
        """
        if job_id is None:
            matches = [
                self.prompt,
                "\[Waiting for response...\]",
                EOF,
                TIMEOUT
            ]
            # there are some cases where the prompt appears multiple
            # times, so we keep trying to match the prompt until it times out,
            # using a small timeout value
            # TODO(minadyn@gmail.com) handle the case of a legitimate timeout
            waiting = True
            max_tries = 5
            tries = 0
            result = ""
            while waiting:
                i = self.process.expect(matches, timeout=1)
                if i == matches.index(TIMEOUT) or tries > max_tries:
                    waiting = False
                tries += 1
                result += self.process.before
            # TODO(minadyn@gmail.com) handle EOF and TIMEOUT cases
        else:
            result = self.jobs[job_id].text
        result = self._process_cmd_output(result)
        return result

    def list(self, options=None):
        cmd = ['ls', '-la']
        return self.run(" ".join(cmd))

    def get(self, rfile, lfile, delete_src=False, delete_target=False, mode="binary",
            background=False):
        """ Get a single file
        :param rfile:
        :param lfile:
        :param delete_src:
        :param delete_target:
        :param mode:
        :param background:
        :return:
        """
        cmd_parts = ['get']
        if delete_src:
            cmd_parts.append('-E')
        if mode == 'ascii':
            cmd_parts.append('-a')
        cmd_parts.append(rfile)
        cmd_parts += ['-o', lfile]
        cmd = " ".join(cmd_parts)
        return self.run(cmd, background=background)

    def mirror(self, source, target, parallel=None, background=False):
        """

        :param source:
        :param target:
        :param parallel: how many files to download in parallel
        :param background: run the process in the background
        :return:
        """
        cmd = ['mirror', source, target]
        if parallel:
            cmd += [str(parallel)]
        if background:
            cmd += ['&']
        return self.run(" ".join(cmd))

    def rm(self, filename, recurse=False):
        """ Remove a single file
        :param filename: The file to delete, relative to the users home directory
        :return:
        :raises: lftppy.exc.DownloadError if the command fails
        """

        cmd = ['rm']
        if recurse:
            cmd.append('-r')
        cmd.append(filename)
        return self.run(" ".join(cmd))

class Job(object):
    def __init__(self, job_no, text):
        self.job_no = job_no
        self.text = text
        self.parse(text)

    def __str__(self):
        return self.text

    def parse(self, text):
        pass
