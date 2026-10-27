#!/bin/bash

#创建newUser新用户
#***********begin*************#
useradd newUser
#************end**************#

#在符号<<前输入设置用户密码的命令(命令与<< EOF保持在同一行), 密码输入在下一行，确认密码输入在下下行
#例如：
#command << EOF
#password
#password
#EOF
#***********begin*************#
passwd newUser << EOF
123456
123456
EOF
#************end**************#

#使用su命令切换当前用户身份为newUser，并且执行whoami指令，然后恢复原来的身份；
#提示使用su命令的-c参数完成
#***********begin*************#
su newUser -c whoami
#************end**************#