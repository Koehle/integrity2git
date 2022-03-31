#!/usr/bin/python
#

import os
from subprocess import Popen
from subprocess import PIPE
import time
import sys
import re
import platform
import filecmp
from filecmp import dircmp
from datetime import datetime
from operator import itemgetter

# this is so windows doesn't output CR (carriage return) at the end of each line and just does LF (line feed)
if platform.system() == 'Windows':
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)    # did not work in my environment!?!

# because the binary output of "print()" function did not work, it was replaced by "sys.stdout.buffer.write()"
# binary output this way to prevent Windows from adding CR LF (carriage return line feed) at the end of each line!
# for git fast-import only LF (line feed) is accepted!

# Global file definitions
git_marks_file      = ''                   # File contains git marks and commits (exported) - set as argument incl. path
git_marks_cmpd_file = 'marks_cpd.txt'      # File contains number of compared marks (finished)
git_marks_left_file = 'marks_left.txt'     # File contains number of remaining marks (to compare)
mks_revis_left_file = 'revisions_left.txt' # File contains number of remaining revisions (to export)
git_marks_cmpd_at_start = 0                # Number of compared git marks at script start (taken from file)

# Global settings and variables for directory comparison
IgnoreDirList=filecmp.DEFAULT_IGNORES      # use default directories to ignore from filecmp
IgnoreFileTypes = ['.pj']                  # ignore MKS project files *.pj only
dir_compare_errors = 0                     # error (results) of directory compare

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

# calculate differences (errors) of a directory comparison
def calc_diff_files(dcmp):
    global dir_compare_errors
    for name in dcmp.diff_files:  # Different files
        dir_compare_errors += 1
    for name in dcmp.left_only:   # Missing files B
        if (name.endswith(tuple(IgnoreFileTypes))):
            continue
        dir_compare_errors += 1
    for name in dcmp.right_only:  # Missing files A
        if (name.endswith(tuple(IgnoreFileTypes))):
            continue
        dir_compare_errors += 1
    # search recursively in subdirectories
    for sub_dcmp in dcmp.subdirs.values():
        calc_diff_files(sub_dcmp)

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

# Get a git commit SHA1-checksum for a given mark from marks file
def get_git_commit_by_mark(mark):
    global git_marks_file
    git_commit = ""
    # read "marks file" (with all existing "mark entries")
    marks_file_list = open(git_marks_file, 'r').read().split('\n')
    # check all list entries for given mark number
    for entry in marks_file_list:
        # extract the string between ":" and " " to get mark
        file_mark = int(entry[(entry.find(":")+1):(entry.find(" "))])
        if(mark == file_mark):
            # extract SHA1-checksum between " " and "end of line"
            git_commit = entry[(entry.find(" ")+1):]
            break
    # check if git commit is valid
    if(git_commit == ""):
        os.system("echo Error: The GIT commit requested as mark was not found in the marks file!")
        exit(code = 666)
    return git_commit

# Get an integer value from a specific file
def get_integer_value_from_file(git_sandbox_path,filename):
    # The file contains only one integer value!
    intVal = 0
    file = git_sandbox_path+"\\.git\\"+filename
    # Check if this file exists
    if(os.path.isfile(file)):
        with open(file) as f:
            line = f.readline()
            if(line != ''):
                intVal = int(line)
    return intVal

def retrieve_revisions(mks_project=0,devpath=0):
    if devpath:
        pipe = Popen('si viewprojecthistory --rfilter=devpath:"%s" --project="%s"' % (devpath, mks_project), shell=True, bufsize=1024, stdout=PIPE)
    else:
        pipe = Popen('si viewprojecthistory --rfilter=devpath::current --project="%s"' % mks_project, shell=True, bufsize=1024, stdout=PIPE)
    versions = pipe.stdout.read().decode('cp850').split('\n') # decode('cp850') necessary because of german umlauts in MKS history
    versions = versions[1:]
    version_re = re.compile('[0-9]([\.0-9])+')
    letters_re = re.compile('[^0-9.]') # matches any non-digit [^0-9] or non-dot [^.] character
    revisions = []
    for version in versions:
        match = version_re.match(version) # check if version starts with a number
        if match:
            version_cols = version.split('\t')
            # We have to check whether it is a valid version entry or "something else"!
            # So far we know that this version starts with a number, but we need to check more:
            # - we need at least 3 columns [0 = "number"] [1 = "author"] [2 = "seconds"]
            # - the number in column [0] must have at least 3 characters (e.g. 1.1) and it must contain at least one dot "."
            # - furthermore column [0] must only contain numbers (0-9) or dots ".". All other characters indicate an invalid version!
            if( (len(version_cols) < 3) or (len(version_cols[0]) < 3) or (version_cols[0].find('.') == -1) or (letters_re.search(version_cols[0])) ):
                # The current "version" starts with a number, but it is not a valid version entry!
                # This string may belong to the previous revision description, so we add it there:
                if(len(revisions)>=1):
                    revisions[len(revisions)-1]["description"] += '\n' + version # Add string to previous revision description!
                continue # with next version entry
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

def retrieve_devpaths(mks_project=0):
    pipe = Popen('si projectinfo --devpaths --noacl --noattributes --noshowCheckpointDescription --noassociatedIssues --project="%s"' % mks_project, shell=True, bufsize=1024, stdout=PIPE)
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
            # If yes we overwrite an existing "ancestor_mark" because the "ancestor_devpath" has
            # priority (it's the starting revision of the "devpath" we are processing at the moment)
            # and has to be used as "ancestor_mark" now!
            # Hint: An existing "ancestor_mark" (we possibly overwrite here) is only the "last_mark"
            # of a previous script run and does NOT necessarily have a successor revision! So it's
            # OK to overwrite it with the ancestor revision of a devpath we need now!
            ancestor_mark = convert_revision_to_mark(ancestor_devpath)
    # Return values ("ancestor_mark" replaces "ancestor_devpath" from now on)
    return skip_this_revision, ancestor_mark

# Export of MKS revisions as GIT commits
def export_to_git(mks_project,revisions=0,devpath=0,ancestor_devpath=0,last_mark=0,mark_limit=0):
    revisions_exported = 0
    abs_sandbox_path = os.getcwd()
    integrity_file = os.path.basename(mks_project)
    for revision in revisions:
        # Check abort conditions for exporting the current revision
        skip_this_revision, ancestor_mark = export_abort_continue(revision,ancestor_devpath,last_mark,mark_limit)
        ancestor_devpath = 0 # reset to zero ("ancestor_mark" is relevant now!)
        if skip_this_revision:
            continue
        #revision_col = revision["number"].split('\.')
        mark = convert_revision_to_mark(revision["number"])
        #Create a build sandbox of the revision
        os.system('si createsandbox --populate --recurse --project="%s" --projectRevision=%s --yes tmp%d' % (mks_project, revision["number"], mark))
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

# Comparison of MKS revisions with the resulting GIT commits (after export)
def compare_git_mks(mks_project,revisions=0,mks_compare_sandbox_path=0,git_sandbox_path=0,git_mark_limit=0):
    global git_marks_cmpd_at_start
    global dir_compare_errors
    revisions_compared = 0
    integrity_file = os.path.basename(mks_project)
    for revision in revisions:
        # Generate mark for current revision
        mark = convert_revision_to_mark(revision["number"])
        # Check abort conditions for comparing the current revision
        if( (mark <= git_marks_cmpd_at_start) or (mark > (git_marks_cmpd_at_start + git_mark_limit)) ):
            continue    # Skip this revision
        #Create a build sandbox of the revision
        os.chdir(mks_compare_sandbox_path)
        os.system('si createsandbox --populate --recurse --project="%s" --projectRevision=%s --yes tmp%d' % (mks_project, revision["number"], mark))
        os.chdir('tmp%d' % mark) #the reason why a number is added to the end of this is because MKS doesn't always drop the full file structure when it should, so they all should have unique names
        tmp_mks_compare_sandbox_path = os.getcwd()
        # Checkout GIT commit that belongs to this mark (and MKS revision) in detached head state
        git_commit = get_git_commit_by_mark(mark)
        os.chdir(git_sandbox_path)
        os.system("git checkout --detach --recurse-submodules %s" % git_commit)
        # Compare directories (MKS revision and GIT commit)
        dcmp = dircmp(tmp_mks_compare_sandbox_path, git_sandbox_path, ignore=IgnoreDirList)
        dir_compare_errors = 0  # Initialize global variable before checking the results
        calc_diff_files(dcmp)   # Evaluate results of directory comparison
        if(dir_compare_errors != 0):
            os.system("echo Error: Comparison of MKS revision and GIT commit failed for mark %d!" % mark)
            exit(code = 666)
        #Drop the MKS sandbox
        os.chdir(mks_compare_sandbox_path)
        os.system("si dropsandbox --yes -f --delete=all tmp%d/%s" % (mark, integrity_file))
        # Sum up compared revisions
        revisions_compared +=1
    return revisions_compared

def get_number_of_mks_revisions(mks_project=0,devpaths=0):
    mks_revisions_sum = 0
    master_revisions = retrieve_revisions(mks_project) # revisions for the master branch
    mks_revisions_sum += len(master_revisions)
    for devpath in devpaths:
        devpath_revisions = retrieve_revisions(mks_project,devpath[0])  # revisions for a specific development path
        mks_revisions_sum += len(devpath_revisions)
    return mks_revisions_sum    # sum of all revisions for the current MKS integrity project


# ==================================================================
# Arguments for this script:
# 
# sys.argv[0] = This script
# sys.argv[1] = Operation mode ("compare" or "export" mode)
# sys.argv[2] = MKS project    (MKS server project location)
# sys.argv[3] = GIT directory  (for MKS export & GIT import)
# sys.argv[4] = GIT mark file  (marks list from previous run)
# sys.argv[5] = GIT mark limit (marks to process per script run)
# sys.argv[6] = MKS directory  (Sandbox to "compare" with GIT)
#
# ==================================================================
marks = []
git_last_mark = 0
git_mark_limit = 0
mks_revisions_compared = 0
mks_revisions_exported = 0
mks_compare_sandbox_path = ""
# ARGUMENT [1]:
# Check operation mode of this script
if (len(sys.argv) > 1):
    op_mode = sys.argv[1]
    # Check given operation mode:
    if not( (op_mode == "compare") or (op_mode == "export") ):
        os.system("echo Error: Invalid operation mode!")
        exit(code = 601)
else:
    os.system("echo Error: Missing operation mode!")
    exit(code = 602)
# ARGUMENT [2]:
# Get MKS project location
if (len(sys.argv) > 2):
    mks_project = sys.argv[2]
    #if not(os.path.exists(mks_project)):
    #    print("Error: Invalid MKS Integrity project!")
    #    exit(code = 603)
else:
    os.system("echo Error: Missing MKS project location!")
    exit(code = 604)
# ARGUMENT [3]:
# Change directory to GIT directory (if argument is available)
if (len(sys.argv) > 3):
    if (os.path.exists(sys.argv[3])):
        git_sandbox_path = sys.argv[3]
        os.chdir('%s' % (git_sandbox_path))
        if not(os.path.isdir(".git")):
            print("Error: Missing git directory!")
            exit(code = 605)
    else:
        print("Error: Invalid path to git directory!")
        exit(code = 606)
# ARGUMENT [4]:
# check if we should read a file with git marks from a previous git fast-import?
if( (len(sys.argv) > 4) and (sys.argv[4] != "") ):
    git_marks_file = sys.argv[4]
    if (os.path.isfile(git_marks_file)): # check if file exists?
        git_last_mark = get_last_mark_from_file(git_marks_file)
    else:
        # For compare mode this file is mandatory!
        if(op_mode == "compare"):
            print("Error: Missing git marks file!")
            exit(code = 607)
# ARGUMENT [5]:
# check whether a maximum number of revisions to be processed has been defined?
if( (len(sys.argv) > 5) and (sys.argv[5] != "") and (int(sys.argv[5]) != 0) ):
    git_mark_limit = int(sys.argv[5])
# ARGUMENT [6]:
# check whether a separate MKS sandbox location has been passed as an argument
if( (len(sys.argv) > 6) and (sys.argv[6] != "") ):
    mks_compare_sandbox_path = sys.argv[6]
    if not(os.path.exists(mks_compare_sandbox_path)):
        print("Error: Location for MKS compare sandbox does not exist!")
        exit(code = 608)
else:
    # For compare mode this argument is mandatory!
    if(op_mode == "compare"):
        print("Error: Missing MKS sandbox location!")
        exit(code = 609)
    # In export mode, the MKS and GIT sandbox locations are identical!

# Get number of already compared marks as initial value from file (necessary to skip compared MKS revisions):
mks_revisions_compared = git_marks_cmpd_at_start = get_integer_value_from_file(git_sandbox_path,git_marks_cmpd_file)

# Identify the MKS development paths and revisions
devpaths = retrieve_devpaths(mks_project)
revisions = retrieve_revisions(mks_project)  # revisions for the master branch

# Check the operation mode of this script:
if(op_mode == "export"):
    # ------------
    # EXPORT Mode:
    # ------------
    # Export MKS revisions to GIT.
    # The script should first be executed in this mode.
    mks_revisions_exported += export_to_git(mks_project,revisions,0,0,git_last_mark,git_mark_limit) #export master branch first!!
    for devpath in devpaths:
        devpath_revisions = retrieve_revisions(mks_project,devpath[0])  # revisions for a specific development path
        if(len(devpath_revisions) == 0): # Check number of revision entries for devpath (by "no entries" an invalid devpath is indicated).
            continue                     # Skip invalid devpath!
        mks_revisions_exported += export_to_git(mks_project,devpath_revisions,devpath[0].replace(' ','_'),devpath[1],git_last_mark,git_mark_limit) #branch names can not have spaces in git so replace with underscores
    # --- end of export mode ---
elif(op_mode == "compare"):
    # -------------
    # COMPARE Mode:
    # -------------
    # Compare MKS revisions with GIT commits (after a previous export).
    # The script can be run in this mode as a second step to check the export to GIT.
    mks_revisions_compared += compare_git_mks(mks_project,revisions,mks_compare_sandbox_path,git_sandbox_path,git_mark_limit) # compare master branch
    for devpath in devpaths:
        devpath_revisions = retrieve_revisions(mks_project,devpath[0])  # revisions for a specific development path
        if(len(devpath_revisions) == 0): # Check number of revision entries for devpath (by "no entries" an invalid devpath is indicated).
            continue                     # Skip invalid devpath!
        mks_revisions_compared += compare_git_mks(mks_project,devpath_revisions,mks_compare_sandbox_path,git_sandbox_path,git_mark_limit) # compare devpath branch
    # --- end of compare mode ---

# Calculation of remaining MKS revisions (after running this script) as a reminder for a later run of this script
mks_revisions_all = get_number_of_mks_revisions(mks_project,devpaths)
mks_revisions_to_compare = (mks_revisions_all - mks_revisions_compared)
mks_revisions_to_export  = (mks_revisions_all - mks_revisions_exported - git_last_mark)
# Write remaining MKS revisions to a file in .git directory (overwrite file 'w' if it exists)
os.chdir(git_sandbox_path+"\\.git")
# Compared MKS revisions and git marks (compare mode)
with open(git_marks_cmpd_file, 'w') as f:
    f.write('%d' % mks_revisions_compared)
# Remaining MKS & git marks to compare (compare mode)
with open(git_marks_left_file, 'w') as f:
    f.write('%d' % mks_revisions_to_compare)
# Remaining MKS revisions to export (export mode)
with open(mks_revis_left_file, 'w') as f:
    f.write('%d' % mks_revisions_to_export)
# The files can be read to decide if the script needs to be called again.
exit(code = 0)  # Normal exit (no error)