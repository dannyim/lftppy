from distutils.core import setup
setup(
    name = 'lftppy',
    packages = ['lftppy'],
    version = '0.1',
    description = 'A wrapper around lftp',
    author = 'Danny Im',
    author_email = 'minadyn@gmail.com',
    url = 'https://github.com/minadyn/lftppy',
    download_url = 'https://github.com/minadyn/lftppy/tarball/0.1',
    keywords = ['lftp', 'ftp'],
    install_requires = [
        'pexpect >=3.3, < 4.0',
        'sure',
        'mock',
        'six',
        'pyftpdlib',
    ]
)