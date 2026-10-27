#!/bin/bash
# 使用vi/vim编辑器查看当前目录下已存在文件oldFile，然后保存退出vi/vim编辑器

cd /root || exit 1

# 使用 vim 非交互模式打开 oldFile 并保存退出
vim -u NONE -n -e -s -c "wq" /root/oldFile

if [ $? -eq 0 ]; then
    echo "使用vi/vim打开文件并且保存成功"
else
    echo "使用vi/vim打开文件并且保存失败" >&2
    exit 1
fi