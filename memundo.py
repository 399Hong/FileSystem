#!/usr/bin/env python3

import logging
import os
import sys
from copy import deepcopy
import threading
import subprocess

from collections import defaultdict
from errno import ENOENT, ENODATA
from stat import S_IFDIR, S_IFLNK, S_IFREG
from time import time

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn


class Memory(LoggingMixIn, Operations):

    def __init__(self):
        self.files = {}
        self.data = defaultdict(bytes)
        self.fd = 0
        self.undo = []
        self.redo = []
        #WIP create  chmod
        now = time()
        self.files['/'] = dict(
            st_mode=(S_IFDIR | 0o755),
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_nlink=2,
            st_uid = os.getuid(),
            st_gid = os.getgid(),
            st_size = 0#c

            )
        self.updateSize()

    def chmod(self, path, mode):
        prevMode = self.files[path]['st_mode']
        self.files[path]['st_mode'] &= 0o770000
        self.files[path]['st_mode'] |= mode
       
        self.undo.extend([f"memory_fs.chmod('{path}',{prevMode})"])
        self.redo.extend([
            f"memory_fs.chmod('{path}',{mode})"
        ])
        return 0

    def chown(self, path, uid, gid):
        prevUID = self.files[path]['st_uid']
        prevGID = self.files[path]['st_gid']
        self.files[path]['st_uid'] = uid
        self.files[path]['st_gid'] = gid
        self.undo.extend(
            [
                f"memory_fs.chown('{path}',{prevUID},{prevGID})"
            ])
        self.redo.extend([
            f"memory_fs.chown('{path}',{uid},{gid})"
        ])

        

    def create(self, path, mode):
        logging.info("created new file")
        now = time()
        self.files[path] = dict(
            st_mode=(S_IFREG | mode),
            st_nlink=1,
            st_size=0,
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_uid = os.getuid(),
            st_gid = os.getgid(),
            )
        self.data[path] = b''
        self.fd += 1
        self.updateSize()
        self.undo.extend([f"memory_fs.unlink('{path}')"]) #c 
        #keep the info about the path for deletion 
        self.redo.extend([
            f"memory_fs.files['{path}'] = {self.files[path]}",
            f"memory_fs.data['{path}'] = {self.data[path]}",
            f'memory_fs.updateSize()',
        ])
        return self.fd

    def getattr(self, path, fh=None):
        if path not in self.files:
            raise FuseOSError(ENOENT)
        return self.files[path]

    def getxattr(self, path, name, position=0):
        attrs = self.files[path].get('attrs', {})
        try:
            return attrs[name]
        except KeyError:
            raise FuseOSError(ENODATA)

    def listxattr(self, path):
        attrs = self.files[path].get('attrs', {})
        return attrs.keys()

    def mkdir(self, path, mode):
        now = time()
        self.files[path] = dict(
            st_mode=(S_IFDIR | mode),
            st_nlink=2,
            st_size=0,
            st_ctime=now,
            st_mtime=now,
            st_atime=now,
            st_uid = os.getuid(),
            st_gid = os.getgid(),
            )
        self.files['/']['st_nlink'] += 1
        self.updateSize()
        self.undo.extend([f"memory_fs.rmdir('{path}')"])

        self.redo.extend([
            f"memory_fs.files['{path}'] = {self.files[path]}",
            #f"memory_fs.data['{path}'] = {self.data[path]}",
            f"memory_fs.files['/']['st_nlink'] += 1",
            f'memory_fs.updateSize()',
        ])

    def open(self, path, flags):
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        return self.data[path][offset:offset + size]

    def readdir(self, path, fh):
        return ['.', '..'] + [x[1:] for x in self.files if x != '/']

    def readlink(self, path):
        return self.data[path]

    def removexattr(self, path, name):
        attrs = self.files[path].get('attrs', {})

        try:
            del attrs[name]
        except KeyError:
            pass        # Should return ENOATTR

    def rename(self, old, new):
    
        oldData = self.data.pop(old)
        oldFile = self.files.pop(old)

        self.undo.extend(
            [
            #rewind new file
            f"memory_fs.files['{new}'] = {self.files[new]}",
            f"memory_fs.data['{new}'] = {self.data[new]}",   

            # reconsturct old file
            f"memory_fs.files['{old}'] = {oldFile}",
            f"memory_fs.data['{old}'] = {oldData}",
  
            ])


        self.data[new] = oldData
        self.files[new] = oldFile

        self.redo.extend([
            f"memory_fs.rename('{old}','{new}')"
        ])



    def rmdir(self, path):
        # with multiple level support, need to raise ENOTEMPTY if contains any files
        prevFile = self.files[path]
        #prevData = self.data[path]
        prevFile_st_nlink =  self.files['/']['st_nlink']

        self.files.pop(path)
        self.files['/']['st_nlink'] -= 1
        self.updateSize()
        self.undo.extend(
            [f"memory_fs.files['{path}'] = {prevFile}",
             #f"memory_fs.data['{path}'] = {prevData}",
             f"memory_fs.files['/']['st_nlink'] = { prevFile_st_nlink }"

            ])
        self.redo.extend([
            f"memory_fs.rmdir('{path}')"
        ])


    def setxattr(self, path, name, value, options, position=0):
        # Ignore options
        attrs = self.files[path].setdefault('attrs', {})
        attrs[name] = value

    def statfs(self, path):
        return dict(f_bsize=512, f_blocks=4096, f_bavail=2048)

    def symlink(self, target, source):
        now = time()
        self.files[target] = dict(
            st_mode=(S_IFLNK | 0o777),
            st_nlink=1,
            st_ctime= now,
            st_mtime= now,
            st_atime= now,
            st_size=len(source),
            st_uid = os.getuid(),
            st_gid = os.getgid(),
        )
        self.data[target] = source
        self.updateSize()

        self.undo.extend(
            [
                f"memory_fs.unlink('{target}')",
                
            ])

        self.redo.extend([
            f"memory_fs.files['{target}'] = {self.files[target]}",
            f"memory_fs.data['{target}'] = '{source}'",
            #f"memory_fs.files['/']['st_nlink'] += 1"
            f'memory_fs.updateSize()',
        ])

    def truncate(self, path, length, fh=None):
        deletedData =  self.data[path][length:]
        
        # make sure extending the file fills in zero bytes
        self.data[path] = self.data[path][:length].ljust(
            length, '\x00'.encode('ascii'))
        self.files[path]['st_size'] = length

            
               
        self.undo.extend(
        [
            f"memory_fs.write('{path}',{deletedData},{length}, {fh})",
            
        ])

        self.redo.extend([
            f"memory_fs.truncate('{path}',{length},{fh})"
        ])
        


    def unlink(self, path):

        prevFile = self.files[path]
        prevData = self.data[path]

        self.data.pop(path)
        self.files.pop(path)
        self.updateSize()
        self.undo.extend(
                [f"memory_fs.files['{path}'] = {prevFile}",
                f"memory_fs.data['{path}'] = {prevData}",
                #f"memory_fs.files['/']['st_nlink'] = { prevFile_st_nlink }"

                 ])
        self.redo.extend([
            f"memory_fs.unlink('{path}')"
        ])

    def utimens(self, path, times=None):
        #print("****time updated****")
        now = time()
        oldAtime = self.files[path]['st_atime']
        oldMtime = self.files[path]['st_mtime'] 
        atime, mtime = times if times else (now, now)
        self.files[path]['st_atime'] = atime
        self.files[path]['st_mtime'] = mtime
        self.undo.extend(
        [
        f"memory_fs.files['{path}']['st_atime'] = {oldAtime}",
        f"memory_fs.files['{path}']['st_mtime'] = {oldMtime}",
        #f"memory_fs.files['/']['st_nlink'] = { prevFile_st_nlink }"
            ])

        self.redo.extend([

                f"memory_fs.files['{path}']['st_atime'] = {atime}",
                f"memory_fs.files['{path}']['st_mtime'] = {mtime}",
        ])

    def write(self, path, data, offset, fh):

        overwrittenData = self.data[path]

        self.data[path] = (
            # make sure the data gets inserted at the right offset
            self.data[path][:offset].ljust(offset, '\x00'.encode('ascii'))
            + data
            # and only overwrites the bytes that data is replacing
            + self.data[path][offset + len(data):])
        self.files[path]['st_size'] = len(self.data[path])

        self.undo.extend(
        [
            f"memory_fs.files['{path}']['st_size'] = len(memory_fs.data['{path}'])",
            f"memory_fs.data['{path}'] = {overwrittenData}"
            
        ])
        self.redo.extend([

            f"memory_fs.write('{path}',{data},{offset},{fh})"



        ])


        


        return len(data)

    def updateSize(self,path = '/') :
        logging.info(sys.getsizeof(self.data))
        
        self.files[path]['st_size'] = sum(map(sys.getsizeof,self.files.values()))

def receive_undo_request():
    
    carry_on = True
    while carry_on:
 
        global flag
        #print(flag)
        command = input ("undoshell: ")
        if command == "undo":
            
            #print("UNDO in progress...")
            while True:
                if s == []:
                    #print("Error. No operations has been performed ")
                    break # nothing to do proceed to get next comment
                else:
                    instructions = deepcopy(s[-1])
                    s.pop()
                    redoinstructions = deepcopy(redo[-1])
                    redo.pop()

                    if instructions == []:
                        continue # non-modfication command move, proceed to check for other commands 
                    for i in instructions[::-1]:
                        #print("Executing",i)
                        #logging.info("trying....")
                        exec(i)
                    #print("stack after undo",s)
                    redoUndo.append([redoinstructions,instructions])# 0 for redo ins 1 for undo ins
                    flag = False
                    break # finished undoing 
            #print("undo completed")
        elif command == "redo":
            #print("REDO in progress...")
            while True:
                if flag == True:
                    print("redo not possible")
                    break
                if redoUndo  == []:
                    #print("Error. No operations has been performed ")
                    break # nothing to do proceed to get next comment
                else:
                    r = deepcopy(redoUndo [-1][0]) #redo
                    u = deepcopy(redoUndo [-1][1])# undo
                    redoUndo.pop()

                    if r == []:
                        continue # non-modfication command move, proceed to check for other commands 
                    for i in r:
                        #print("Executing",i)
                        logging.info("trying....")
                        exec(i)
                    #print("stack after redo",redoUndo)
                    s.append(u) # update undo list as an insturction is redo meaning that it can be undo again
                    redo.append(r)
                    flag = False
                    break # finished undoing 
            #print("redo completed")
        elif command == "quit":
            #print ("Shutting down user space file system.")
            os.system("umount -f memdir")

            ## for linux
            # fusermount -u memdir
            carry_on = False
        elif command == "stack":
            print(s)
            print(memory_fs.data)
        else:
            memory_fs.undo = []
            memory_fs.redo = []
            
            subprocess.run(command, shell=True, cwd="memdir")

            s.append(memory_fs.undo)
            redo.append(memory_fs.redo)
            if memory_fs.undo != []:
                flag = True

if __name__ == '__main__':
    base_dir = os.getcwd()
    memory_fs = Memory()
    redo = []
    redoUndo = []
    s = []
    flag = True
    threading.Thread(target=receive_undo_request).start()
    logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.DEBUG)
    fuse = FUSE(memory_fs, "memdir", foreground=True, allow_other=False)
