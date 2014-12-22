lftppy
======
A python lftp wrapper.  
* Tested against lftp 4.6.0 on Centos 6.4

Install
===
Example Usage
===
<pre><code>
import lftppy
# create process
process = lftp.LFTP(hostname, port, username, password)
# mirror directory, put process in the background
process.mirror(dir_name, target_dir, background=True)
# get single file
result = process.get(filename)
# delete file
result = process.rm(filename)
# get latest output from running jobs
jobs = process.jobs
for idx, job in jobs.iteritems():
	print job
</code>
</pre>
Testing
===
* run all tests
	* <pre><code>$ nosetests</code></pre>
* run a single test
	* <pre><code>$ nosetests tests.testlftp.FTPServerBase</code></pre>