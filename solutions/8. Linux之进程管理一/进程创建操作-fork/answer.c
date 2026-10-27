#include <unistd.h>
#include <sys/types.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

/************************
 * 提示: 不要在子进程或父进程中使用exit函数或者return来退出程序
*************************/
void createProcess()
{
	/********** BEGIN **********/
	pid_t pid;
	pid = fork();
	if(pid == -1)
	{
		printf("创建进程失败(%s)!\n", strerror(errno));
	}
	else if(pid == 0)
	{
		printf("Children\n");
	}
	else
	{
		printf("Parent\n");
	}
	/********** END **********/
}