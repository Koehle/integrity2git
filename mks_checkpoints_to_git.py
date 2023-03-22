#!/usr/bin/python
#

import os
import subprocess
import copy
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

# Dictionary keys
class CsvDictKeyConstants:
    # Columns for additional files only (not part of mks projects list):
    dvpth_name = 'devpath_name'     # Development path name for a specific project
    dvpth_strt = 'devpath_start'    # MKS starting revision for this devpath
    dvpth_vers = 'devpath_versions' # Version information for this devpath
    chkpt_revi = 'chkpnt_revisions' # MKS checkpoint revision(s)
    error_msg  = 'error_message'    # MKS error message taken from "stderr"

# Global file definitions
mks_all_chkpts_file = 'chkpts_all_revs.txt'# File contains all checkpoint revisions of the MKS project (write only)
mks_prc_chkpts_file = 'chkpts_alx_revs.txt'# File contains all checkpoint revisions to be processed (write only)
mks_brk_chkpts_file = 'chkpts_broken.txt'  # File contains checkpoint revisions with problems when creating a sandbox (read / write)
mks_cmp_chkpts_file = 'chkpts_compared.txt'# File contains checkpoints already compared for the MKS project (write only)
mks_exp_chkpts_file = 'chkpts_exported.txt'# File contains checkpoints already exported for the MKS project (write only)
mks_ign_chkpts_file = 'chkpts_ignore.txt'  # File contains checkpoints to be ignored for the MKS project (read only)
mks_rmc_chkpts_file = 'chkpts_rem_cmp.txt' # File contains checkpoints still to be compared for the MKS project (read / write)
mks_rme_chkpts_file = 'chkpts_rem_exp.txt' # File contains checkpoints still to be exported for the MKS project (read / write)
mks_ign_dvpths_file = 'dvpths_ignore.txt'  # File contains devpaths to be ignored information for the MKS project (read only)
mks_mis_dvpths_file = 'dvpths_missing.txt' # File contains missing devpath information for the MKS project (read only)
git_marks_sha_file  = ''                   # File contains git marks and commits (exported) - set as argument incl. path
git_marks_rev_file  = 'marks_2_rev.txt'    # File contains git marks and the MKS revision number (exported)
git_marks_cpd_file  = 'marks_cpd.txt'      # File contains number of compared marks (finished)
git_marks_rem_file  = 'marks_rem.txt'      # File contains number of remaining marks (to compare)
mks_revis_all_file  = 'revisions_all.txt'  # File contains number of all MKS revisions (existing)
mks_revis_prc_file  = 'revisions_alx.txt'  # File contains number of all MKS revisions to be processed
mks_revis_exp_file  = 'revisions_exp.txt'  # File contains number of exported revisions (finished)
mks_revis_rem_file  = 'revisions_rem.txt'  # File contains number of remaining revisions (to export)

# Global variables for git marks and MKS revisions
git_marks_cmpd_at_start = 0                # Number of compared git marks at script start (*f)
git_marks_mks_rev_list  = []               # List with existing git marks and the associated MKS revisions (*fu)
mks_revs2marks_list = []                   # List of MKS revisions to determine the associated git mark number (*cu)
mks_revisions_all_list = []                # List of all MKS checkpoint revisions for current project (*m)
mks_revisions_prc_list = []                # List of all MKS checkpoint revisions to be processed (*cu)
mks_revisions_brk_list = []                # List of broken MKS revisions with problems during export (*fu)
mks_revisions_cmp_list = []                # List with compared MKS revisions - redundant and for checks only (*fu)
mks_revisions_exp_list = []                # List with exported MKS revisions - redundant and for checks only (*fu)
mks_revisions_ign_list = []                # List with MKS revisions to be ignored during export and comparison (*f)
mks_revisions_rmc_list = []                # List of remaining MKS checkpoint revisions to be compared (*fu)
mks_revisions_rme_list = []                # List of remaining MKS checkpoint revisions to be exported (*fu)
mks_revisions_skipped  = False             # Flag to remember that MKS checkpoint revisions have been skipped (*cu)
# Additional information for the variables above:
# (*m)  == the content is taken from MKS and up to date
# (*f)  == the content is taken from file (as initialization)
# (*fu) == the content is taken from file and updated during the runtime of the script
# (*cu) == the content is only calculated and updated during the runtime of the script

# Global settings and variables for directory comparison and MKS export
IgnoreDirList=filecmp.DEFAULT_IGNORES      # use default directories to ignore from filecmp
IgnoreFileTypes = ['.pj', '.gitattributes', '.gitignore']  # ignore these file types!
dir_compare_errors = 0                     # error (results) of directory compare
dir_comp_err_list  = []                    # error list, containing differences as strings
op_mode : str = ''                         # script operation mode ("export" or "compare")

# External compare tool "Meld" which can be used in case of comparison errors
MELD_COMPARE_WINDOWS = 'C:\\Program Files (x86)\\Meld\\Meld.exe'

# Lists for git ref string manipulation (e.g. for devpaths or tags)
REMOVE_GIT_CHAR_LIST = ['\\','|','?',':','"','<','>','[',']','*','~','^']
REPLACE_GIT_CHAR_LIST = [[' ','..'],['_','.']]

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

# Some background information on the following function:
# In our MKS integrity sandbox, there may be folders that contain only one *.pj file.
# These are "empty" folders of (sub-)projects that do not have any other members yet.
# Since we ignore the file type '.pj' in our comparison, such folders seem to be empty,
# but "dcmp" does not ignore such folders, so we have to do that!
# Check if a folder contains only a *.pj file (and nothing else):
def is_pj_only_folder(path):
    retval = False                                  # init return value
    if os.path.isdir(path):                         # check if path is valid?
        files = os.listdir(path)                    # list elements in folder
        if (len(files) == 1):                       # only 1 element in folder?
            fullpath = os.path.join(path, files[0]) # fullpath of folder or file
            if os.path.isfile(fullpath):            # check if element is a file?
                if fullpath.endswith('.pj'):        # check if it is a *.pj file?
                    retval = True
        elif (len(files) == 0):                     # is folder completely empty?
            retval = True                           # ignore empty folders too!
    return retval

# calculate differences (errors) of a directory comparison
def calc_diff_files(dcmp):
    global IgnoreFileTypes, dir_compare_errors, dir_comp_err_list
    for name in dcmp.diff_files:  # Different files
        dir_comp_err_list.append(name)
        dir_compare_errors += 1
    for name in dcmp.left_only:   # MKS only (missing files in GIT)
        if (name.endswith(tuple(IgnoreFileTypes))):
            continue
        # on the MKS side, empty or pj-only folders are allowed!
        if (is_pj_only_folder(os.path.join(dcmp.left, name))):
            continue
        dir_comp_err_list.append(name)
        dir_compare_errors += 1
    for name in dcmp.right_only:  # GIT only (missing files in MKS)
        if (name.endswith(tuple(IgnoreFileTypes))):
            continue
        # on the GIT side, there will be no empty folders,
        # because GIT does not manage empty folders!
        dir_comp_err_list.append(name)
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
    sys.stdout.buffer.write(bytes('%s %s inline %s\n' % (code, mode, filename), 'utf-8'))
    sys.stdout.buffer.write(bytes('data %d\n' % (os.path.getsize(filename)), 'utf-8'))
    sys.stdout.buffer.write(content) # binary output!

def convert_revision_to_mark(revision):
    global mks_revs2marks_list
    # check if the revision is included in the list
    if not revision in mks_revs2marks_list:
        # if not, add it to the list and create a new index
        mks_revs2marks_list.append(revision)
    # this list starts with index "0" but mark numbers start with value "1"
    # (list index for a "revision") + 1 == "mark number" for this "revision"
    return mks_revs2marks_list.index(revision) + 1

def get_last_mark_from_python():
    global mks_revs2marks_list
    # length of the list == number of marks == last "mark number"
    return len(mks_revs2marks_list)

def get_last_mark_from_file(filename):
    # init return value
    last_file_mark = int(0)
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
    global git_marks_sha_file
    git_commit = ""
    # read "marks file" (with all existing "mark entries")
    marks_file_list = open(git_marks_sha_file, 'r').read().split('\n')
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
        os.system('echo Error: The GIT commit requested as mark was not found in the marks file!')
        exit(code = 666)
    return git_commit

# Get list of exported GIT marks and MKS revisions
def get_marks_and_revisions_from_file(git_sandbox_path,filename):
    # The file contains several lines (strings)
    retlist = []
    file = os.path.join(git_sandbox_path, '.git', filename)
    # Check if this file exists
    if(os.path.isfile(file)):
        with open(file) as f:
            lines = f.read()
        retlist = lines.split('\n')
        # Remove all '' entries from list
        while('' in retlist):
            retlist.remove('')
    # "retlist" may be empty, if the file does not exist!
    return retlist

# Get a mark for a given MKS revision number from list
def get_mark_by_mks_revision(marks_to_rev_list,mks_revision):
    mark = int(-1)
    # check all list entries for given mks_revision
    for entry in marks_to_rev_list:
        # extract MKS revision between " " and "end of line"
        entry_revision = entry[(entry.find(" ")+1):]
        if(mks_revision == entry_revision):
            # extract the string between ":" and " " to get mark
            mark = int(entry[(entry.find(":")+1):(entry.find(" "))])
            break
    # mark not found, if value is '-1'
    return mark

# Get a MKS revision number for a given mark from list
def get_mks_revision_by_mark(marks_to_rev_list,mark):
    mks_revision = ""
    # check all list entries for given mark number
    for entry in marks_to_rev_list:
        # extract the string between ":" and " " to get mark
        entry_mark = int(entry[(entry.find(":")+1):(entry.find(" "))])
        if(mark == entry_mark):
            # extract SHA1-checksum between " " and "end of line"
            mks_revision = entry[(entry.find(" ")+1):]
            break
    # MKS revision not found, if value is ''
    return mks_revision

# Create a MKS revision list from the marks to revision list
def get_mks_revisions_exported(marks_to_rev_list):
    revisions_list = []
    for entry in marks_to_rev_list:
        # extract MKS revision between " " and "end of line"
        mks_revision = entry[(entry.find(" ")+1):]
        revisions_list.append(mks_revision)
    return revisions_list

# Create a list of the remaining MKS revisions to be processed
def get_mks_revisions_remaining(rev_all_list=[],rev_ign_list=[],rev_proc_list=[]):
    # first we create a local copy of the list with all MKS revisions
    rev_rem_list = list(copy.deepcopy(rev_all_list))
    # remove revisions to be ignored
    for entry in rev_ign_list:
        if (entry in rev_rem_list):
            rev_rem_list.remove(entry)
    # remove already processed revisions
    for entry in rev_proc_list:
        if (entry in rev_rem_list):
            rev_rem_list.remove(entry)
    # return list with remaining revisions
    return rev_rem_list

# Get an integer value from a specific file
def get_integer_value_from_file(git_sandbox_path,filename):
    # The file contains only one integer value!
    intVal = 0
    file = os.path.join(git_sandbox_path, '.git', filename)
    # Check if this file exists
    if(os.path.isfile(file)):
        with open(file) as f:
            line = f.readline()
            if(line != ''):
                intVal = int(line)
    return intVal

# Get devpaths to be ignored list from file
def get_ignore_devpaths_from_file(git_sandbox_path,filename):
    # The file contains a list of devpaths to be ignored!
    cKey = CsvDictKeyConstants # Keys for dictionary
    file_list = []
    ignore_devpaths_list_long = []
    ignore_devpaths_list_short = []
    file = os.path.join(git_sandbox_path, '.git', filename)
    # Check if this file exists
    if(os.path.isfile(file)):
        with open(file) as f:
            file_list = f.read().split('\n')
        # Create a new devpath list in the format we use in this script!
        for entry in file_list:
            if(entry == ''):
                continue
            # Each entry consists of two columns separated by ';'
            devpath_entry = {}
            columns = entry.split(';')
            devpath_entry[cKey.dvpth_name] = columns[0]
            devpath_entry[cKey.dvpth_strt] = columns[1].replace('Checkpoint_', '')
            ignore_devpaths_list_long.append(devpath_entry)
            # In addition, create a short list containing only devpath names
            ignore_devpaths_list_short.append(columns[0])
    # Return list of devpaths to be ignored for the current MKS project
    return ignore_devpaths_list_long, ignore_devpaths_list_short

# Get missing devpaths list from file
def get_missing_devpaths_from_file(git_sandbox_path,filename):
    # The file contains a list of missing devpaths!
    cKey = CsvDictKeyConstants # Keys for dictionary
    file_list = []
    missing_devpaths_list = []
    file = os.path.join(git_sandbox_path, '.git', filename)
    # Check if this file exists
    if(os.path.isfile(file)):
        with open(file) as f:
            file_list = f.read().split('\n')
        # Create a new devpath list in the format we use in this script!
        for entry in file_list:
            if(entry == ''):
                continue
            # Each entry consists of three columns separated by ';'
            devpath_entry = {}
            columns = entry.split(';')
            devpath_entry[cKey.dvpth_name] = columns[0]
            devpath_entry[cKey.dvpth_strt] = columns[1].replace('Checkpoint_', '')
            devpath_entry[cKey.dvpth_vers] = columns[2].replace('\\t', '\t').replace('\\n', '\n')
            missing_devpaths_list.append(devpath_entry)
    # Return list of missing devpaths for the current MKS project
    return missing_devpaths_list

# Write a given list to a new text-file inside '.git' directory
def write_list_to_file(git_sandbox_path,filename,data_list=[]):
    file = os.path.join(git_sandbox_path, '.git', filename)
    with open(file, 'w', newline='') as f:
        if(len(data_list) > 0):
            for entry in data_list:
                f.write(str(entry) + os.linesep)
        else:
            pass # create an empty file

# Excecute an MKS command with the subprocess module
def mks_cmd(cmd='', capture_output=False):
    global op_mode, mks_revisions_brk_list
    # Try the MKS command several times
    for attempt in range(3):
        try:
            # If "check" is true, and the process exits with a non-zero exit code, an exception will be raised.
            # Execution with result = "CompletedProcess" if there is no exception (Info: "timeout" value in seconds)
            result = subprocess.run(cmd, shell=True, bufsize=1024, capture_output=capture_output, timeout=300, check=True)
            # Exit the for loop if the execution was successful
            exit_code = 0
            break
        # Handling of exceptions (e.g. due to a "timeout" or another cause of error detected by the "check" option)
        except subprocess.CalledProcessError as e:
            # Exit the for loop with the return code of the subprocess (MKS Integrity "exit status values" from 0 to 255)
            exep_type = 'CalledProcessError'
            exit_code = e.returncode
            result    = e.returncode
            # When a "general command failure" occurs during "si createsandbox"
            if ( (exit_code == 128) and (cmd.startswith('si createsandbox')) ):
                result = exit_code = 0  # Ignore this error / returncode
                # Check the operation mode of this script
                if(op_mode == "export"):
                    # Search for the MKS project revision string
                    search_str = '--projectRevision='
                    tmp_val = cmd.find(search_str)
                    if (tmp_val != -1):
                        # Extract the MKS project revision string
                        tmp_str = cmd[(tmp_val + len(search_str)):]
                        tmp_str = tmp_str[:tmp_str.find(' ')]
                        # Append it to the broken revisions list
                        mks_revisions_brk_list.append(tmp_str)
            # In case of a "CalledProcessError" we don't try again
            break
        except subprocess.TimeoutExpired as e:
            # Take the timeout value + attempt as exit code (Note: MKS Integrity "exit status values" are <= 255)
            exep_type = 'TimeoutExpired'
            exit_code = e.timeout + attempt
            # Wait a moment before the next attempt
            time.sleep(5)
    # Error handling if execution was NOT successful
    if(exit_code != 0):
        # The MKS "cmd" message is forwarded to Git fast-import and is part of the "fast_import_crash" protocol,
        # as Git fast-import does not know our message (including the MKS command) and therefore stops execution as well!
        print('Exception "%s" during MKS command "%s" with returncode "%d"' % (exep_type, cmd, exit_code))
        exit(exit_code)
    return result

def retrieve_revisions(mks_project='',devpath='',missing_devpaths=[]):
    cKey = CsvDictKeyConstants # Keys for dictionary
    if(devpath == ''):
        # versions for the master branch
        result = mks_cmd('si viewprojecthistory --rfilter=devpath::current --project="%s"' % mks_project, capture_output=True)
        versions = result.stdout.decode('cp850').split('\n') # decode('cp850') necessary because of german umlauts in MKS history
        versions = versions[1:]
    elif not(devpath.lower().startswith('missing_devpath_')):
        # versions for a development path available on the MKS server
        result = mks_cmd('si viewprojecthistory --rfilter=devpath:"%s" --project="%s"' % (devpath, mks_project), capture_output=True)
        versions = result.stdout.decode('cp850').split('\n') # decode('cp850') necessary because of german umlauts in MKS history
        versions = versions[1:]
    else:
        # versions for a missing development path (the development path information is missing on the MKS server)
        # avoid an error message from the MKS server and don't try to retrieve information for a missing devpath
        versions = []
        # Check for missing devpath information we added manually:
        if(len(missing_devpaths) > 0):
            # Search the list for the current development path:
            for missing_devpath in missing_devpaths:
                if(devpath != missing_devpath[cKey.dvpth_name]):
                    continue
                # Take over the "versions" for this development path:
                versions = missing_devpath[cKey.dvpth_vers].split('\n')
        # Check if the missing devpath was found in our list
        if(len(versions) == 0):
            os.system('echo Error: "%s" was not found in the missing devpaths list!' % (devpath))
            exit(code = 666)
    # Prepare checks with regular expressions
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

def retrieve_devpaths(mks_project='', missing_devpaths=[]):
    cKey = CsvDictKeyConstants # Keys for dictionary
    result = mks_cmd('si projectinfo --devpaths --noacl --noattributes --noshowCheckpointDescription --noassociatedIssues --project="%s"' % mks_project, capture_output=True)
    devpaths = result.stdout.decode('cp850') # decode('cp850') necessary because of german umlauts
    devpaths = devpaths [1:]
    devpaths_re = re.compile('    (.+) \(([0-9][\.0-9]+)\)\n')
    devpath_col = devpaths_re.findall(devpaths)
    # Check for missing devpaths (manually added)
    if(len(missing_devpaths) > 0):
        for missing_devpath in missing_devpaths:
            # Add missing devpath name and start e.g. ('Missing_Devpath_1', '1.4')
            devpath_col.append( (missing_devpath[cKey.dvpth_name],missing_devpath[cKey.dvpth_strt]) )
    re.purge()
    devpath_col_sort = sort_devpaths(devpath_col) #order development paths by version
    return devpath_col_sort

# Retrieve a list with all checkpoint revisions for a specific MKS project
def retrieve_all_mks_prj_checkpoints(mks_project=''):
    # Select the "revision" field to get only the checkpoint revisions from the MKS project history
    result = mks_cmd('si viewprojecthistory --fields=revision --project="%s"' % mks_project, capture_output=True)
    revisions = result.stdout.decode('cp850').split('\n') # decode('cp850') necessary because of german umlauts in MKS history
    # The first entry of this returned revision list contains the MKS project location as a string
    if not(revisions[0] == mks_project):
        os.system('echo Error: Wrong project information in checkpoint revision list received!')
        os.system('echo Info: The returned and provided project information must be the same!')
        os.system('echo Info: revisions[0] = "%s"' % (revisions[0]))
        os.system('echo Info: mks_project  = "%s"' % (mks_project))
        exit(code = 666)
    # Remove MKS project location from list
    revisions = revisions[1:]
    # Remove "empty revisions" from list
    while ('' in revisions):
        revisions.remove('')
    # Return checkpoint revisions list
    return revisions

def export_abort_continue(revision=[],ancestor_devpath='',last_mark=0,mark_limit=0,rev_ign_list=[]):
    global git_marks_mks_rev_list, mks_revisions_exp_list, mks_revisions_skipped
    # I noticed that the MKS client crashes when too many revisions are exported at once!
    # This mechanism is intended to divide the export to git into several steps...
    ancestor_mark = 0            # mark of the ancestor revision we will use to continue 
    # Check if the current MKS revision should be ignored?
    # This is a very special case to handle invalid checkpoints within a valid development path!
    # Normally all checkpoint revisions of a development path must be exported here!
    if (revision["number"] in rev_ign_list):
        skip_this_revision = 1 # No export to git for this revision!
        mks_revisions_skipped = True # Remember that MKS revisions have been skipped!
    else:
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
                if (mks_revisions_skipped == True):
                    mks_revisions_skipped = False # Reset the "revisions skipped" flag
                    ancestor_mark = get_last_mark_from_python() # Get the mark of the last git commit
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
            # Check if the MKS revision that represents the beginning of the current devpath exists.
            # This specific MKS revision must have been exported before this devpath...
            if not(ancestor_devpath in mks_revisions_exp_list):
                os.system('echo Error: Start revision "%s" for current devpath not found in mks revisions list!' % (ancestor_devpath))
                os.system('echo Info: Check if the MKS project revision has been exported before this devpath!')
                os.system('echo Info: If not, check if the reason could be a missing devpath in this project!')
                exit(code = 666)
            # If yes we overwrite an existing "ancestor_mark" because the "ancestor_devpath" has
            # priority (it's the starting revision of the "devpath" we are processing at the moment)
            # and has to be used as "ancestor_mark" now!
            # Hint: An existing "ancestor_mark" (we possibly overwrite here) is only the "last_mark"
            # of a previous script run and does NOT necessarily have a successor revision! So it's
            # OK to overwrite it with the ancestor revision of a devpath we need now!
            ancestor_mark = convert_revision_to_mark(ancestor_devpath)
            # Check if the calculated "ancestor_mark" is correct for the "ancestor_devpath" revision.
            # For this we use a list of already exported MKS checkpoint revisions and their mark numbers.
            if not(ancestor_mark == get_mark_by_mks_revision(git_marks_mks_rev_list,ancestor_devpath)):
                os.system('echo Error: Mark "%d" does not belong to revision "%s"!' % (ancestor_mark,ancestor_devpath))
                os.system('echo Info: Check this script for possible errors when creating the "ancestor_mark"!')
                exit(code = 666)
    # Return values ("ancestor_mark" replaces "ancestor_devpath" from now on)
    return skip_this_revision, ancestor_mark

# Export of MKS revisions as GIT commits
def export_to_git(mks_project='',revisions=[],devpath='',ancestor_devpath='',last_mark=0,mark_limit=0):
    global IgnoreFileTypes, git_marks_mks_rev_list, mks_revisions_exp_list, mks_revisions_ign_list
    revisions_exported = int(0)
    abs_sandbox_path = os.getcwd()
    integrity_file = os.path.basename(mks_project)
    for revision in revisions:
        # Check abort conditions for exporting the current revision
        skip_this_revision, ancestor_mark = export_abort_continue(revision,ancestor_devpath,last_mark,mark_limit,mks_revisions_ign_list)
        ancestor_devpath = '' # reset ("ancestor_mark" is relevant now!)
        if skip_this_revision:
            continue
        # Check if the MKS revision to be exported already exists
        if (revision["number"] in mks_revisions_exp_list):
            os.system('echo Error: Revision "%s" has already been exported!' % (revision["number"]))
            os.system('echo Info: Check project history for faulty development paths and ignore them!')
            exit(code = 666)
        # Get or generate a mark number for current revision
        mark = convert_revision_to_mark(revision["number"])
        # Create a build sandbox of the revision
        mks_cmd('si createsandbox --populate --recurse --project="%s" --projectRevision=%s --yes tmp%d' % (mks_project, revision["number"], mark))
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
        sys.stdout.buffer.write(bytes(('encoding iso-8859-1\n'), 'utf-8')) #encoding for the following description ('iso-8859-1')
        sys.stdout.buffer.write(bytes(('data %d\n%s\n' % (len(revision["description"]), revision["description"])), 'iso-8859-1'))
        if ancestor_mark:
            # There are 3 cases where this code is relevant:
            # 1) we're starting a development path so we need to start from it was originally branched from
            # 2) we continue an earlier export and import at this point (start from there again)
            # 3) we ignore some invalid revisions of a development path and start again from a valid revision
            sys.stdout.buffer.write(bytes(('from :%d\n' % ancestor_mark), 'utf-8')) 
        sys.stdout.buffer.write(b'deleteall\n')
        tree = os.walk('.')
        for dir in tree:
            # Skip '.git' and all subdirectories
            if (dir[0].find('.git') != -1):
                continue
            for filename in dir[2]:
                if (dir[0] == '.'):
                    fullfile = filename
                else:
                    fullfile = os.path.join(dir[0], filename)[2:]
                # The *.pj files are used by MKS and should be skipped
                if (fullfile.endswith(tuple(IgnoreFileTypes))):
                    continue
                # Skip this python script during export
                if (fullfile.find(os.path.basename(__file__)) != -1):
                    continue
                inline_data(fullfile)
        # Check the contents of the revision label (may have been changed previously)
        if(revision["label"] != "-"):
            TmpStr = "%s__%s" % (revision["number"], revision["label"])
        else: # Use MKS Revision number as tag only!
            TmpStr = revision["number"]
        # Check if the new tag is valid (e.g. it must not contain spaces)
        # Details on the requirements for a "git tag" are here:
        # https://www.git-scm.com/docs/git-check-ref-format
        # Remove selected characters
        for char in REMOVE_GIT_CHAR_LIST:
            TmpStr = TmpStr.replace(char, '')
        # Replace selected characters
        for idx in range(len(REPLACE_GIT_CHAR_LIST[0])):
            TmpStr = TmpStr.replace(REPLACE_GIT_CHAR_LIST[0][idx], REPLACE_GIT_CHAR_LIST[1][idx])
        # The new tag string must not end with a dot "."
        while(TmpStr.endswith('.')):
            TmpStr = TmpStr[:-1]
        # Create a "lightweight tag" with "reset command" for this commit
        sys.stdout.buffer.write(bytes(('reset refs/tags/%s\n' % TmpStr), 'utf-8')) # MKS Checkpoint information as GIT tag
        sys.stdout.buffer.write(bytes(('from :%d\n' % mark), 'utf-8'))             # specify commit for this tag by "mark"
        # Drop the MKS sandbox
        os.chdir('..') # return to GIT directory
        mks_cmd('si dropsandbox --yes -f --delete=all "tmp%d/%s"' % (mark, integrity_file))
        # Create a list with git mark numbers and MKS revisions:
        TmpStr = ':' + str(mark) + ' ' + revision["number"]
        git_marks_mks_rev_list.append(TmpStr)
        # Add revision number to MKS revisions exported list:
        mks_revisions_exp_list.append(revision["number"])
        # Sum up exported revisions
        revisions_exported +=1
    # return the number of exported revisions
    return revisions_exported

# Comparison of MKS revisions with the resulting GIT commits (after export)
def compare_git_mks(mks_project='',revisions=[],mks_compare_sandbox_path='',git_sandbox_path='',git_mark_limit=0):
    global git_marks_cmpd_at_start, git_marks_mks_rev_list, mks_revisions_cmp_list, mks_revisions_ign_list
    global IgnoreDirList, dir_compare_errors, dir_comp_err_list
    revisions_compared = int(0)
    integrity_file = os.path.basename(mks_project)
    for revision in revisions:
        # Check if the current MKS revision should be ignored?
        # This is a very special case to handle invalid checkpoints within a valid development path!
        # Normally all checkpoint revisions of a development path must be exported here!
        if (revision["number"] in mks_revisions_ign_list):
            continue
        # Get or generate a mark number for current revision
        mark = convert_revision_to_mark(revision["number"])
        # Check abort conditions for comparing the current revision
        if( (mark <= git_marks_cmpd_at_start) or (mark > (git_marks_cmpd_at_start + git_mark_limit)) ):
            continue    # Skip this revision
        # Check if the calculated mark is correct for the MKS checkpoint revision number
        # For this we use a list of already exported MKS checkpoint revisions and their mark numbers
        if not(mark == get_mark_by_mks_revision(git_marks_mks_rev_list,revision["number"])):
            os.system('echo Error: Mark "%d" does not belong to revision "%s"!' % (mark,revision["number"]))
            os.system('echo Info: Check the MKS project history for modifications since the export process!')
            exit(code = 666)
        # Check whether the MKS revision to be compared has already been compared
        if (revision["number"] in mks_revisions_cmp_list):
            os.system('echo Error: Revision "%s" has already been compared!' % (revision["number"]))
            os.system('echo Info: Check the MKS project history for modifications since the export process!')
            exit(code = 666)
        # Create a build sandbox of the revision
        os.chdir(mks_compare_sandbox_path)
        mks_cmd('si createsandbox --populate --recurse --project="%s" --projectRevision=%s --yes tmp%d' % (mks_project, revision["number"], mark))
        os.chdir('tmp%d' % mark) #the reason why a number is added to the end of this is because MKS doesn't always drop the full file structure when it should, so they all should have unique names
        tmp_mks_compare_sandbox_path = os.getcwd()
        # Checkout GIT commit that belongs to this mark (and MKS revision) in detached head state
        git_commit = get_git_commit_by_mark(mark)
        os.chdir(git_sandbox_path)
        os.system('git checkout --detach --recurse-submodules %s' % git_commit)
        # Compare directories (left: MKS revision vs. right: GIT commit)
        dcmp = dircmp(tmp_mks_compare_sandbox_path, git_sandbox_path, ignore=IgnoreDirList)
        dir_comp_err_list = []  # Initialize global error list before checking the results
        dir_compare_errors = 0  # Initialize global variable before checking the results
        calc_diff_files(dcmp)   # Evaluate results of directory comparison
        if(dir_compare_errors != 0):
            os.system('echo Error: Comparison of MKS revision and GIT commit failed for mark %d!' % mark)
            os.system('echo MKS Sandbox: "%s"' % tmp_mks_compare_sandbox_path)
            os.system('echo GIT Sandbox: "%s"' % git_sandbox_path)
            # Output differences on the console to facilitate troubleshooting
            os.system('echo List the differences found during the comparison:')
            for entry in dir_comp_err_list:
                os.system('echo "%s"' % entry)
            # Check if program "Meld" is available:
            if(os.path.isfile(MELD_COMPARE_WINDOWS)):
                os.system('echo Calling the program "Meld" to visually compare the sandboxes...')
                # Create command string for calling the "Meld" program with MKS and GIT sandbox path
                cmd_str = '"' + MELD_COMPARE_WINDOWS + '" "' + tmp_mks_compare_sandbox_path + '" "' + git_sandbox_path + '"'
                # Call the "Meld" program to display the differences
                subprocess.call(cmd_str, shell=True)
            exit(code = 666)
        # Drop the MKS sandbox
        os.chdir(mks_compare_sandbox_path)
        mks_cmd('si dropsandbox --yes -f --delete=all "tmp%d/%s"' % (mark, integrity_file))
        # Add revision number to MKS revisions compared list:
        mks_revisions_cmp_list.append(revision["number"])
        # Sum up compared revisions
        revisions_compared +=1
    return revisions_compared

# Calculate the number of MKS checkpoint revisions this script will process (export & compare)
def get_number_of_mks_revisions_to_process(mks_project='',devpaths=[],devpaths_tb_ignored=[],revisions_tb_ignored=[]):
    prj_revisions_list = retrieve_revisions(mks_project) # revisions for the master branch
    for devpath in devpaths:
        # specific devpaths should be ignored
        if (devpath[0] in devpaths_tb_ignored):
            continue
        devpath_revisions = retrieve_revisions(mks_project,devpath[0],mks_missing_devpaths)  # revisions for a specific development path
        prj_revisions_list.extend(devpath_revisions) # add the development path revisions to the projects revisions list
    # Remove all checkpoint revisions to be ignored from this list (only revisions belonging to a valid development path are relevant here)!
    for rev_ignore in revisions_tb_ignored:
        for entry in prj_revisions_list:
            if (rev_ignore == entry['number']):
                prj_revisions_list.remove(entry)
                break # inner loop
    return len(prj_revisions_list)  # sum of all revisions for the current MKS integrity project

# Check and modify development path name before export to git
def check_and_modify_devpath_name(dvpth_name:str='', existing_dvpths:list[str]=[]):
    # Branch names can not have spaces in git so replace with underscores
    dvpth_name = dvpth_name.replace(' ','_')
    # Check if this development path name already exists
    while (dvpth_name.lower() in existing_dvpths):
        # Add a trailing "x" to this devpath name (to prevent duplicate davpath names).
        # We had problems with development paths that differed only by capitalization.
        dvpth_name = dvpth_name + 'x'
    # Add this devpath name to the list (lowercase letters only)!
    existing_dvpths.append(dvpth_name.lower())
    # Return the new devpath name (including capital letters)
    return dvpth_name

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
git_last_mark = int(0)
git_mark_limit = int(0)
mks_ignore_dvpths_l = []    # list of MKS devpaths to be ignored (with checkpoint where devpath starts)
mks_ignore_dvpths_s = []    # list of MKS devpaths to be ignored (only devpath names)
mks_missing_devpaths = []
mks_revisions_compared = int(0)
mks_revisions_exported = int(0)
mks_compare_sandbox_path = ""
# ARGUMENT [1]:
# Check operation mode of this script
if (len(sys.argv) > 1):
    op_mode = sys.argv[1]
    # Check given operation mode:
    if not( (op_mode == "compare") or (op_mode == "export") ):
        os.system('echo Error: Invalid operation mode!')
        exit(code = 601)
else:
    os.system('echo Error: Missing operation mode!')
    exit(code = 602)
# ARGUMENT [2]:
# Get MKS project location
if (len(sys.argv) > 2):
    mks_project = sys.argv[2]
    #if not(os.path.exists(mks_project)):
    #    os.system('echo Error: Invalid MKS Integrity project!')
    #    exit(code = 603)
else:
    os.system('echo Error: Missing MKS project location!')
    exit(code = 604)
# ARGUMENT [3]:
# Change directory to GIT directory (if argument is available)
if (len(sys.argv) > 3):
    if (os.path.exists(sys.argv[3])):
        git_sandbox_path = sys.argv[3]
        os.chdir('%s' % (git_sandbox_path))
        if not(os.path.isdir('.git')):
            os.system('echo Error: Missing git directory!')
            exit(code = 605)
    else:
        os.system('echo Error: Invalid path to git directory!')
        exit(code = 606)
# ARGUMENT [4]:
# check if we should read a file with git marks from a previous git fast-import?
if( (len(sys.argv) > 4) and (sys.argv[4] != "") ):
    git_marks_sha_file = sys.argv[4]
    if (os.path.isfile(git_marks_sha_file)): # check if file exists?
        git_last_mark = get_last_mark_from_file(git_marks_sha_file)
    else:
        # For compare mode this file is mandatory!
        if(op_mode == "compare"):
            os.system('echo Error: Missing git marks file!')
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
        os.system('echo Error: Location for MKS compare sandbox does not exist!')
        exit(code = 608)
else:
    # For compare mode this argument is mandatory!
    if(op_mode == "compare"):
        os.system('echo Error: Missing MKS sandbox location!')
        exit(code = 609)
    # In export mode, the MKS and GIT sandbox locations are identical!

# Get list of already exported GIT marks and the associated MKS revisions as initial value from file:
git_marks_mks_rev_list = get_marks_and_revisions_from_file(git_sandbox_path,git_marks_rev_file)
# Get list of already exported MKS revisions as initial value from file:
mks_revisions_exp_list = get_marks_and_revisions_from_file(git_sandbox_path,mks_exp_chkpts_file)
# Get a list of broken MKS revisions with problems during export
mks_revisions_brk_list = get_marks_and_revisions_from_file(git_sandbox_path,mks_brk_chkpts_file)
# Get list of already compared MKS revisions as initial value from file:
mks_revisions_cmp_list = get_marks_and_revisions_from_file(git_sandbox_path,mks_cmp_chkpts_file)
# Get number of already compared marks as initial value from file (necessary to skip compared MKS revisions):
mks_revisions_compared = git_marks_cmpd_at_start = get_integer_value_from_file(git_sandbox_path,git_marks_cpd_file)
# Fetch information about MKS checkpoints to be ignored from a file (if available):
mks_revisions_ign_list = get_marks_and_revisions_from_file(git_sandbox_path,mks_ign_chkpts_file)
# Fetch information about MKS development paths to be ignored from a file (if available):
mks_ignore_dvpths_l, mks_ignore_dvpths_s = get_ignore_devpaths_from_file(git_sandbox_path,mks_ign_dvpths_file)
# Fetch information about missing MKS development paths from a file (if available):
mks_missing_devpaths = get_missing_devpaths_from_file(git_sandbox_path,mks_mis_dvpths_file)

# Retrieve all MKS checkpoint revisions for this project from MKS project history
mks_revisions_all_list = retrieve_all_mks_prj_checkpoints(mks_project)
# Create a list of all MKS checkpoint revisions to be processed ("all list" - "ignore list")
mks_revisions_prc_list = get_mks_revisions_remaining(mks_revisions_all_list,mks_revisions_ign_list,[])
# Identify the MKS development paths for this project
devpaths = retrieve_devpaths(mks_project,mks_missing_devpaths)
# Get number of MKS checkpoint revisions to be processed by this script (export and compare mode)
mks_revisions_to_process = get_number_of_mks_revisions_to_process(mks_project,devpaths,mks_ignore_dvpths_s,mks_revisions_ign_list)
# We use different methods to generate "the list of revisions to be processed" and to calculate
# "the number of revisions to be processed". To force the user to consciously look at MKS project
# errors, we added a plausibility check here:
if not( len(mks_revisions_prc_list) == mks_revisions_to_process ):
    os.system('echo Error: Mismatching number of MKS checkpoints to be processed by this script!')
    os.system('echo Info: Check the list creation and calculation process for differences!')
    os.system('echo       One or more of the following 3 situations could be present:')
    os.system('echo (S1): Maybe some checkpoint revisions need to be ignored and provided as input to this script!')
    os.system('echo       Typically these checkpoint revisions are faulty and do not belong to any devpaths!')
    os.system('echo       None of the checkpoints that are part of a valid devpath should be ignored!')
    os.system('echo (S2): Some devpaths may be faulty and they need to be ignored for the calculation process!')
    os.system('echo       Typically, these devpaths have no "real" checkpoint revisions in the project history!')
    os.system('echo       Please provide faulty devpaths as input to this script via the devpaths ignore file!')
    os.system('echo (S3): It is also possible that devpaths are missing and their revisions are not included')
    os.system('echo       in the number of revisions to be processed. In this case, please supply the')
    os.system('echo       missing devpaths via the missing devpaths file as input to this script.')
    exit(code = 610)

# Check the operation mode of this script:
if(op_mode == "export"):
    # ------------
    # EXPORT Mode:
    # ------------
    # Export MKS revisions to GIT.
    # The script should first be executed in this mode.
    master_revisions = retrieve_revisions(mks_project)  # revisions for the master branch
    mks_revisions_exported += export_to_git(mks_project,master_revisions,0,0,git_last_mark,git_mark_limit) #export master branch first!!
    devpath_name_list = [] # remember devpaths names of this project (in lowercase letters) for additional checks
    for devpath in devpaths:
        if(devpath[0] in mks_ignore_dvpths_s): # Check if this devpath is faulty and should be ignored
            continue                           # Skip invalid devpath!
        devpath_revisions = retrieve_revisions(mks_project,devpath[0],mks_missing_devpaths)  # revisions for a specific development path
        if(len(devpath_revisions) == 0): # Check number of revision entries for devpath (by "no entries" an invalid devpath is indicated).
            continue                     # Skip invalid devpath!
        devpath_name = check_and_modify_devpath_name(devpath[0], devpath_name_list) # check and modify development path name before export to git
        mks_revisions_exported += export_to_git(mks_project,devpath_revisions,devpath_name,devpath[1],git_last_mark,git_mark_limit) # export devpath branch
    # --- end of export mode ---
elif(op_mode == "compare"):
    # -------------
    # COMPARE Mode:
    # -------------
    # Compare MKS revisions with GIT commits (after a previous export).
    # The script can be run in this mode as a second step to check the export to GIT.
    master_revisions = retrieve_revisions(mks_project)  # revisions for the master branch
    mks_revisions_compared += compare_git_mks(mks_project,master_revisions,mks_compare_sandbox_path,git_sandbox_path,git_mark_limit) # compare master branch
    for devpath in devpaths:
        if(devpath[0] in mks_ignore_dvpths_s): # Check if this devpath is faulty and should be ignored
            continue                           # Skip invalid devpath!
        devpath_revisions = retrieve_revisions(mks_project,devpath[0],mks_missing_devpaths)  # revisions for a specific development path
        if(len(devpath_revisions) == 0): # Check number of revision entries for devpath (by "no entries" an invalid devpath is indicated).
            continue                     # Skip invalid devpath!
        mks_revisions_compared += compare_git_mks(mks_project,devpath_revisions,mks_compare_sandbox_path,git_sandbox_path,git_mark_limit) # compare devpath branch
    # --- end of compare mode ---

# Calculation of remaining MKS revisions (after running this script) for checks and as a reminder for a later run of this script
mks_revisions_rmc_list = get_mks_revisions_remaining(mks_revisions_all_list,mks_revisions_ign_list,mks_revisions_cmp_list) # compare
mks_revisions_rme_list = get_mks_revisions_remaining(mks_revisions_all_list,mks_revisions_ign_list,mks_revisions_exp_list) # export
mks_revisions_rem_to_compare = (mks_revisions_to_process - mks_revisions_compared)
mks_revisions_rem_to_export  = (mks_revisions_to_process - mks_revisions_exported - git_last_mark)

# Write information to files in .git directory (overwrite file 'w' if it exists)
# The files can be read to decide if the script needs to be called again.
os.chdir(os.path.join(git_sandbox_path, '.git'))
# No. of compared MKS revisions and git marks (compare mode)
with open(git_marks_cpd_file, 'w') as f:
    f.write('%d' % mks_revisions_compared)
# No. of remaining MKS & git marks to compare (compare mode)
with open(git_marks_rem_file, 'w') as f:
    f.write('%d' % mks_revisions_rem_to_compare)
# No. of all MKS project checkpoint revisions (for information)
with open(mks_revis_all_file, 'w') as f:
    f.write('%d' % (len(mks_revisions_all_list)))
# No. of MKS project revisions to be processed (export mode)
with open(mks_revis_prc_file, 'w') as f:
    f.write('%d' % mks_revisions_to_process)
# No. of remaining MKS revisions to export (export mode)
with open(mks_revis_rem_file, 'w') as f:
    f.write('%d' % mks_revisions_rem_to_export)

# List of git marks and MKS revisions (export mode)
write_list_to_file(git_sandbox_path, git_marks_rev_file,  git_marks_mks_rev_list)
# List of all MKS checkpoint revisions (export mode)
write_list_to_file(git_sandbox_path, mks_all_chkpts_file, mks_revisions_all_list)
# List of MKS checkpoint revisions to be processed (export mode)
write_list_to_file(git_sandbox_path, mks_prc_chkpts_file, mks_revisions_prc_list)
# List of already exported MKS revisions (export mode)
write_list_to_file(git_sandbox_path, mks_exp_chkpts_file, mks_revisions_exp_list)
# List of broken MKS revisions with problems during export (export mode)
write_list_to_file(git_sandbox_path, mks_brk_chkpts_file, mks_revisions_brk_list)
# List of already compared MKS revisions (compare mode)
write_list_to_file(git_sandbox_path, mks_cmp_chkpts_file, mks_revisions_cmp_list)
# List of remaining MKS revisions to be exported (export mode)
write_list_to_file(git_sandbox_path, mks_rme_chkpts_file, mks_revisions_rme_list)
# List of remaining MKS revisions to be compared (compare mode)
write_list_to_file(git_sandbox_path, mks_rmc_chkpts_file, mks_revisions_rmc_list)

# --- Additional plausibility checks after writing the files ---
# Check whether the number of list entries (revisions to be compared)
# matches the calculation of the revisions still to be compared.
if not( len(mks_revisions_rmc_list) == mks_revisions_rem_to_compare ):
    os.system('echo Error: Mismatch in number of MKS checkpoint revisions to be compared detected!')
    os.system('echo Info: No. of remaining revisions in list = %d' % (len(mks_revisions_rmc_list)))
    os.system('echo Info: Calculation of remaining revisions = %d' % (mks_revisions_rem_to_compare))
    exit(code = 611)
# Check whether the number of list entries (revisions to be exported)
# matches the calculation of the revisions still to be exported.
if not( len(mks_revisions_rme_list) == mks_revisions_rem_to_export ):
    os.system('echo Error: Mismatch in number of MKS checkpoint revisions to be exported detected!')
    os.system('echo Info: No. of remaining revisions in list = %d' % (len(mks_revisions_rme_list)))
    os.system('echo Info: Calculation of remaining revisions = %d' % (mks_revisions_rem_to_export))
    exit(code = 612)

# If no errors were detected:
exit(code = 0)  # Normal exit (no error)

