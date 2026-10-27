#!/bin/bash

#在以下部分写出完成任务的命令
#***********begin*************#
cd /tmp
mkdir -p Dir Dir1 Dir2 Dir3 Dir4 Dir5
rm -rf Dir/Dir1 Dir/Dir2 Dir/Dir1Cpy Dir/Dir3 Dir/Dir4 Dir6
cp -r Dir1 Dir/
cp -r Dir2 Dir/
cp -r Dir1 Dir/Dir1Cpy
mv Dir3 Dir/
mv Dir4 Dir/
mv Dir5 Dir6
#************end**************#