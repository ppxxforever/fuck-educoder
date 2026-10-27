#!/bin/bash

#在以下部分写出完成任务的命令
#***********begin*************#
chmod u=x oldDir1
chmod g-w oldDir2
chmod o+x oldDir3
chmod u=r,g=w,o=x oldDir4
chmod -R u=r,g=w,o=x oldDir5
#************end**************#