#include <stdio.h>
#include <sys/types.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/wait.h>

/************************
 * 提示: 在子进程中如果执行exec函数失败要使用exit函数正确退出子进程
*************************/
void execlProcess()
{
	pid_t pid = vfork();
	if(pid == -1)
	{
		printf("创建子进程失败(%s)\n", strerror(errno));
		return;
	}
	else if(pid == 0)
	{
		//子进程
		/********** BEGIN **********/
		execlp("mkdir", "mkdir", "testDir", NULL);
		_exit(-1);
		/********** END **********/
	}
	else
	{
		//父进程
		/********** BEGIN **********/
		waitpid(pid, NULL, 0);
		printf("Parent Process\n");
		/********** END **********/
	}
}