#include <unistd.h>
#include <sys/types.h>
#include <stdlib.h>
#include <stdio.h>

void printPid()
{
    printf("%d\n", getpid());
}

void exitProcess()
{
    /********** BEGIN **********/
    atexit(printPid);
    printf("注册退出处理函数成功\n");
    fflush(stdout);
    /********** END **********/
}