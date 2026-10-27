#include <unistd.h>
#include <sys/types.h>
#include <stdio.h>

/**********************
 * pid: 当前进程ID
 * ppid: 父进程ID
***********************/
struct procIDInfo
{
	pid_t pid;
	pid_t ppid;
};

/************************
 * 返回值: 需要被打开的目录路径
*************************/
struct procIDInfo getProcInfo()
{
	struct procIDInfo ret;   //存放进程ID信息，并返回
	/********** BEGIN **********/
	ret.pid = getpid();
	ret.ppid = getppid();
	/********** END **********/

	return ret;
}