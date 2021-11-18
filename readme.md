# User Space File System

An undoable memory based user space file system for a Linux environment.

## Description


## Python version

Please use Python version 3.9 or lower versions. 

## Installation

### 0. open the correspending folder via CLI

### 1. Virtual environment set up and run it

**Windows**
```shell
$ py -3 -m venv venv
$ venv\Scripts\activate
```
**MacOS**
```shell
$ python3 -m venv venv
$ source venv/bin/activate
```
###  2. Install dependencies via requirment.txt

```shell 
$ pip install -r requirements.txt
```


### 3. Run 
From the directory, and within the activated virtual environment
```shell 
$ python3 memundo.py

OR

$ chmod u+x memundo.py
$ ./memundo.py
```

 ### Usage example

 ```shell
    touch file1 
    echo "hello" > hi 
    cat hi cat > file1  
        this is a test
    cat hi file1 > file2 
    cat hi >> file2 
    chmod u-w file2 gi
    ln -s hi hisym 
    cat hisym 
    rm file1 
    rm file2 
    mv hi hi2 
    cat hisym 
    cp hi2 hi 
    cat hisym 
    mkdir tempdir 
    rmdir tempdir
    undo
    redo
    quit 
```
