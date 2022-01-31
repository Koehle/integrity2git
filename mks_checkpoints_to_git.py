#!/usr/bin/python
#

import os
from subprocess import Popen
from subprocess import PIPE
import time
import sys
import re
import platform
from datetime import datetime

# this is so windows doesn't output CR (carriage return) at the end of each line and just does LF (line feed)
if platform.system() == 'Windows':
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)    # did not work in my environment!?!

# because the binary output of "print()" function did not work, it was replaced by "sys.stdout.buffer.write()"
# binary output this way to prevent Windows from adding CR LF (carriage return line feed) at the end of each line!
# for git fast-import only LF (line feed) is accepted!

# Source for the following code snippet / python script:
# https://gist.github.com/johnberroa/cd49976220933a2c881e89b69699f2f7
# Removes umlauts from strings and replaces them with the letter+e convention
# :param string: string to remove umlauts from
# :return: unumlauted string
def remove_umlaut(string):
    u = 'ü'.encode()
    U = 'Ü'.encode()
    a = 'ä'.encode()
    A = 'Ä'.encode()
    o = 'ö'.encode()
    O = 'Ö'.encode()
    ss = 'ß'.encode()
    string = string.encode()
    string = string.replace(u, b'ue')
    string = string.replace(U, b'Ue')
    string = string.replace(a, b'ae')
    string = string.replace(A, b'Ae')
    string = string.replace(o, b'oe')
    string = string.replace(O, b'Oe')
    string = string.replace(ss, b'ss')
    string = string.decode('utf-8')
    return string

def inline_data(filename, code = 'M', mode = '644'):
    content = open(filename, 'rb').read()
    if platform.system() == 'Windows':
        #this is a hack'ish way to get windows path names to work git (is there a better way to do this?)
        filename = filename.replace('\\','/')
    sys.stdout.buffer.write(bytes("%s %s inline %s\n" % (code, mode, filename), 'utf-8'))
    sys.stdout.buffer.write(bytes('data %d\n' % (os.path.getsize(filename)), 'utf-8'))
    sys.stdout.buffer.write(content) # binary output!

def convert_revision_to_mark(revision):
    if not revision in marks:
        marks.append(revision)
    return marks.index(revision) + 1

def retrieve_revisions(devpath=0):
    if devpath:
        pipe = Popen('si viewprojecthistory --rfilter=devpath:"%s" --project="%s"' % (devpath, sys.argv[1]), shell=True, bufsize=1024, stdout=PIPE)
    else:
        pipe = Popen('si viewprojecthistory --rfilter=devpath::current --project="%s"' % sys.argv[1], shell=True, bufsize=1024, stdout=PIPE)
    versions = pipe.stdout.read().decode('cp850').split('\n') # decode('cp850') necessary because of german umlauts in MKS history
    versions = versions[1:]
    version_re = re.compile('[0-9]([\.0-9])+')
    revisions = []
    for version in versions:
        match = version_re.match(version)
        if match:
            version_cols = version.split('\t')
            revision = {}
            revision["number"] = version_cols[0]
            revision["author"] = remove_umlaut(version_cols[1]) # because git fast-input expects 'utf-8' for "author"
            revision["seconds"] = int(time.mktime(datetime.strptime(version_cols[2], "%d.%m.%Y %H:%M:%S").timetuple()))
            # version_cols[5] == MKS Checkpoint Label (may be empty)
            if(version_cols[5] != ""):
                revision["label"] = version_cols[5]
            else: # in case of an empty MKS Label
                revision["label"] = "-"
            # version_cols[6] == MKS Checkpoint description
            revision["description"]  = ('%s\n\n' % revision["label"]) + ('MKS Checkpoint Revision: %s\n' % revision["number"]) + ('MKS Checkpoint Description:\n\n%s\n' % version_cols[6])
            revisions.append(revision)
        else:
            # 'No version match' could be additional description lines of a previous revision,
            # e.g. if there are control characters like '\n' inside the checkpoint description!
            # We ignore empty "version entries" and check if "revisions list" is not empty:
            if((version != "") and (len(revisions)>=1)):
                revisions[len(revisions)-1]["description"] += '\n' + version # Add string to previous revision description!
    revisions.reverse() # Old to new
    re.purge()
    return revisions

def retrieve_devpaths():
    pipe = Popen('si projectinfo --devpaths --noacl --noattributes --noshowCheckpointDescription --noassociatedIssues --project="%s"' % sys.argv[1], shell=True, bufsize=1024, stdout=PIPE)
    devpaths = (pipe.stdout.read()).decode('utf-8')
    devpaths = devpaths [1:]
    devpaths_re = re.compile('    (.+) \(([0-9][\.0-9]+)\)\n')
    devpath_col = devpaths_re.findall(devpaths)
    re.purge()
    #devpath_col.sort(key=lambda x: map(int, x[1].split('.'))) #order development paths by version -> does not work in my case -> !!! ToDo !!!
    return devpath_col

def export_to_git(revisions,devpath=0,ancestor=0):
    abs_sandbox_path = os.getcwd()
    integrity_file = os.path.basename(sys.argv[1])
    if not devpath: #this is assuming that devpath will always be executed after the mainline import is finished
        move_to_next_revision = 0
    else:
        move_to_next_revision = 1
    for revision in revisions:
        #revision_col = revision["number"].split('\.')
        mark = convert_revision_to_mark(revision["number"])
        if move_to_next_revision:
            os.system('si retargetsandbox --project="%s" --projectRevision=%s %s/%s' % (sys.argv[1], revision["number"], abs_sandbox_path, integrity_file))
            os.system('si resync --yes --recurse --sandbox="%s/%s"' % (abs_sandbox_path, integrity_file)) # sandbox location is required in case of devpath
        move_to_next_revision = 1
        if devpath:
            sys.stdout.buffer.write(bytes(('commit refs/heads/devpath/%s\n' % devpath), 'utf-8'))
        else:
            sys.stdout.buffer.write(b'commit refs/heads/master\n') # binary output!
        sys.stdout.buffer.write(bytes(('mark :%d\n' % mark), 'utf-8'))
        # According to git fast-import documentation author (name) is typically UTF-8 encoded.
        # https://www.git-scm.com/docs/git-fast-import
        sys.stdout.buffer.write(bytes(('committer %s <> %d +0100\n' % (revision["author"], revision["seconds"])), 'utf-8')) #Germany UTC time zone
        # The optional encoding command indicates the encoding of the commit message.
        sys.stdout.buffer.write(bytes(('encoding iso-8859-15\n'), 'utf-8')) #encoding for the following description ('iso-8859-15')
        sys.stdout.buffer.write(bytes(('data %d\n%s\n' % (len(revision["description"]), revision["description"])), 'iso-8859-15'))
        if ancestor:
            sys.stdout.buffer.write(bytes(('from :%d\n' % convert_revision_to_mark(ancestor)), 'utf-8')) #we're starting a development path so we need to start from it was originally branched from
            ancestor = 0 #set to zero so it doesn't loop back in to here
        sys.stdout.buffer.write(b'deleteall\n')
        tree = os.walk('.')
        for dir in tree:
            for filename in dir[2]:
                if (dir[0] == '.'):
                    fullfile = filename
                else:
                    fullfile = os.path.join(dir[0], filename)[2:]
                # The *.pj files are used by MKS and should be skipped
                if (fullfile.endswith('.pj')):
                    continue
                if (fullfile[0:4] == ".git"):
                    continue
                if (fullfile.find('mks_checkpoints_to_git') != -1):
                    continue
                inline_data(fullfile)
        # Check the contents of the revision label (may have been changed previously)
        if(revision["label"] != "-"):
            TmpStr = "%s__%s" % (revision["number"], revision["label"])
        else: # Use MKS Revision number as tag only!
            TmpStr = revision["number"]
        # Create a "lightweight tag" with "reset command" for this commit
        sys.stdout.buffer.write(bytes(('reset refs/tags/%s\n' % TmpStr), 'utf-8')) # MKS Checkpoint information as GIT tag
        sys.stdout.buffer.write(bytes(('from :%d\n' % mark), 'utf-8'))             # specify commit for this tag by "mark"

marks = []
devpaths = retrieve_devpaths()
revisions = retrieve_revisions()
#Change directory to GIT directory (if argument is available)
if (len(sys.argv) > 2):
    os.chdir('%s' % (sys.argv[2]))
#Create a build sandbox of the first revision
os.system('si createsandbox --populate --recurse --project="%s" --projectRevision=%s tmp' % (sys.argv[1], revisions[0]["number"]))
os.chdir('tmp')
export_to_git(revisions) #export master branch first!!
for devpath in devpaths:
    devpath_revisions = retrieve_revisions(devpath[0])
    export_to_git(devpath_revisions,devpath[0].replace(' ','_'),devpath[1]) #branch names can not have spaces in git so replace with underscores
#Drop the sandbox
integrity_file = os.path.basename(sys.argv[1])
os.chdir("..") #leave 'tmp' and return to GIT directory
os.system("si dropsandbox --yes -f --delete=all tmp/%s" % (integrity_file))