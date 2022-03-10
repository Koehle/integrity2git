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
from operator import itemgetter

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

# Sorting the development path list by changing the MKS revision number string beforehand
def sort_devpaths(devpath_list):
    devpath_list_sort = []
    rev_list_maxlen = 0
    # As first step we need to know the maximum length of the MKS revision number
    # e.g. revision number '1.43.1.27' leads to '4' list entries --> length == 4
    for devpath in devpath_list:
            length = len(devpath[1].split('.'))
            rev_list_maxlen = max(length, rev_list_maxlen)
    # As next step, we need to split revision number string and create a new list
    for devpath in devpath_list:
        revision_list = []
        revision_string = ""
        devpath_sort = {}
        # split revision number string to list
        revision_list = devpath[1].split('.')
        # extend revision list to required length
        while(len(revision_list) < rev_list_maxlen):
            revision_list.append('0')
        # modifiy list entries and generate string again
        for i in range(len(revision_list)):
            # add leading zeros to each list entry
            revision_list[i] = revision_list[i].zfill(4)
            # combine list entries again to one string without separator "."
            revision_string += revision_list[i]
        # Generate new devpath entry with this revision string for sorting
        devpath_sort = devpath[0], devpath[1], revision_string
        devpath_list_sort.append(devpath_sort)
    # As a last step we use the new list element "revision string" for the sort operation
    # Sort by new item 2 (revision string) first. Then sort by item 0 (devpath name string).
    devpath_list_sort.sort(key=(itemgetter(2,0)))
    return(devpath_list_sort)

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

def get_last_mark_from_python():
    return len(marks)

def get_last_mark_from_file(filename):
    # read "marks file" (with all existing "mark entries")
    marks_file_list = open(filename, 'r').read().split('\n')
    # get last mark of a previous import to git from this file
    for entry in marks_file_list:
        if(entry == ''):    # check for EOF and leave "for loop" if reached
            continue        # the last entry or line of marks file is relevant
        # extract the string between ":" and " "
        last_file_mark = int(entry[(entry.find(":")+1):(entry.find(" "))])
        # converted to an "int" we get the "mark" (number) inside this entry
    return last_file_mark

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
            if devpath: # check for invalid devpaths (they can be recognized by "revision numbers")
                revision_list = revision["number"].split('.')
                if(len(revision_list) <= 2): # All master branch revisions typically have 2 entries (e.g. '1.4')
                    return revisions         # devpath revisions should have more than 2 entries (e.g. '1.4.1.9') - if not skip!
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
    devpath_col_sort = sort_devpaths(devpath_col) #order development paths by version
    return devpath_col_sort

def export_abort_continue(revision,ancestor_devpath,last_mark,mark_limit):
    # I noticed that the MKS client crashes when too many revisions are exported at once!
    # This mechanism is intended to divide the export to git into several steps...
    ancestor_devpath_mark = 0    # mark of the ancestor revision of a devpath
    ancestor_mark = 0            # mark of the ancestor revision we will use to continue 
    # Check "arguments" for abort condition (mark_limit) to prevent MKS / Java crash
    # and "last_mark" to continue with an import after a previous abort due to limit.
    if( last_mark ): # If there is a "last_mark" from a previous import
        if( get_last_mark_from_python() < last_mark ):
            # create NEW python internal "mark list", until the mark for the continuation is reached...
            convert_revision_to_mark(revision["number"])
            skip_this_revision = 1 # No export to git for this revision!
        elif( get_last_mark_from_python() == last_mark ):
            # The last mark is the ancestor for our current revision!
            ancestor_mark = last_mark # remember it as ancestor to continue!
            skip_this_revision = 0 # Export this revision to git!
        elif( get_last_mark_from_python() >= (last_mark + mark_limit) ):
            # Abort condition is defined by "last_mark" + "mark_limit"
            skip_this_revision = 1 # No export to git for this revision!
        else: # All revisions from "last_mark" to "last_mark + mark_limit"
            skip_this_revision = 0 # Export this revision to git!
    elif( mark_limit ): # If only "mark_limit" is defined
        if( get_last_mark_from_python() >= mark_limit ):
            # Abort condition is defined by one argument (mark limit) only!
            skip_this_revision = 1 # No export to git for this revision!
        else:
            skip_this_revision = 0 # Export this revision to git!
    # Check if this revision is skipped?
    if not skip_this_revision:
        # Check if there is an ancestor revision for a devpath?
        if ancestor_devpath:
            ancestor_devpath_mark = convert_revision_to_mark(ancestor_devpath)
            # If there is no ancestor mark for continuation of MKS export and git import defined
            if not ancestor_mark:
                ancestor_mark = ancestor_devpath_mark
            # We may want to continue based on a revision that is the ancestor for a devpath
            # and also our "last_mark" from a previous import.
            # In this case our "ancestor_mark" and the "ancestor_devpath_mark" must be identical,
            # because there can be only one "mark" for the "from" statement of git fast-import...
            elif( ancestor_devpath_mark != ancestor_mark ):
                assert "Invalid revision or mark for continuation detected!"
    # Return values ("ancestor_mark" replaces "ancestor_devpath_mark" from now on)
    return skip_this_revision, ancestor_mark

def export_to_git(revisions,devpath=0,ancestor_devpath=0,last_mark=0,mark_limit=0):
    revisions_exported = 0
    abs_sandbox_path = os.getcwd()
    integrity_file = os.path.basename(sys.argv[1])
    for revision in revisions:
        # Check abort conditions for exporting the current revision
        skip_this_revision, ancestor_mark = export_abort_continue(revision,ancestor_devpath,last_mark,mark_limit)
        ancestor_devpath = 0 # reset to zero ("ancestor_mark" is relevant now!)
        if skip_this_revision:
            continue
        #revision_col = revision["number"].split('\.')
        mark = convert_revision_to_mark(revision["number"])
        #Create a build sandbox of the revision
        os.system('si createsandbox --populate --recurse --project="%s" --projectRevision=%s --yes tmp%d' % (sys.argv[1], revision["number"], mark))
        os.chdir('tmp%d' % mark) #the reason why a number is added to the end of this is because MKS doesn't always drop the full file structure when it should, so they all should have unique names
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
        if ancestor_mark:
            # There are 2 cases where this code is relevant:
            # 1) we're starting a development path so we need to start from it was originally branched from
            # 2) we continue an earlier export and import at this point (start from there again)
            sys.stdout.buffer.write(bytes(('from :%d\n' % ancestor_mark), 'utf-8')) 
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
        #Drop the sandbox
        os.chdir("..") # return to GIT directory
        os.system("si dropsandbox --yes -f --delete=all tmp%d/%s" % (mark, integrity_file))
        # Sum up exported revisions
        revisions_exported +=1
    # return the number of exported revisions
    return revisions_exported

def get_number_of_mks_revisions(devpaths=0):
    mks_revisions_sum = 0
    master_revisions = retrieve_revisions() # revisions for the master branch
    mks_revisions_sum += len(master_revisions)
    for devpath in devpaths:
        devpath_revisions = retrieve_revisions(devpath[0])  # revisions for a specific development path
        mks_revisions_sum += len(devpath_revisions)
    return mks_revisions_sum    # sum of all revisions for the current MKS integrity project

marks = []
git_last_mark = 0
git_mark_limit = 0
mks_revisions_exported = 0
devpaths = retrieve_devpaths()
revisions = retrieve_revisions()
#Change directory to GIT directory (if argument is available)
if (len(sys.argv) > 2):
    os.chdir('%s' % (sys.argv[2]))
# check for .git directory
assert os.path.isdir(".git"), "Call git init first"
# check if we should read a file with git marks from a previous git fast-import?
if( (len(sys.argv) > 3) and (sys.argv[3] != "") ):
    if (os.path.isfile(sys.argv[3])): # check if file exists?
        git_last_mark = get_last_mark_from_file(sys.argv[3])
# check whether a maximum number of revisions to be processed has been defined?
if( (len(sys.argv) > 4) and (sys.argv[4] != "") and (int(sys.argv[4]) != 0) ):
    git_mark_limit = int(sys.argv[4])
# Export to GIT
mks_revisions_exported += export_to_git(revisions,0,0,git_last_mark,git_mark_limit) #export master branch first!!
for devpath in devpaths:
    devpath_revisions = retrieve_revisions(devpath[0])
    if(len(devpath_revisions) == 0): # Check number of revision entries for devpath (by "no entries" an invalid devpath is indicated).
        continue                     # Skip invalid devpath!
    mks_revisions_exported += export_to_git(devpath_revisions,devpath[0].replace(' ','_'),devpath[1],git_last_mark,git_mark_limit) #branch names can not have spaces in git so replace with underscores
# Calculation of remaining MKS revisions (after running this script) as a reminder for a later run of this script
mks_revisions_left = (get_number_of_mks_revisions(devpaths) - mks_revisions_exported - git_last_mark)
# Write remaining MKS revisions to a file in .git directory (overwrite file 'w' if it exists)
os.chdir(".git")
with open('revisions_left.txt', 'w') as f:
    f.write('%d' % mks_revisions_left)
# This file can be read to decide if the script needs to be called again.