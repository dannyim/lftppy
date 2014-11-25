import pexpect


def spawn(command):
    child = pexpect.spawn(command)
    return child


def run(command):
    return pexpect.run(command)