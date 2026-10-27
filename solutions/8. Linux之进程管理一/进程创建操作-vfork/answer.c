#include <unistd.h>
#include <sys/types.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <stdlib.h>

/************************
 * 提示: 不要在子进程中使用return来退出程序
*************************/
void createProcess()
{
	/********** BEGIN **********/
	pid_t pid;
	pid = vfork();
	if(pid == -1)
	{
		printf("创建进程失败(%s)!\n", strerror(errno));
		exit(-1);
	}
	else if(pid == 0)
	{
		printf("Children\n");
		exit(0);
	}
	else
	{
		printf("Parent\n");
	}
	
	/********** END **********/

	exit(0);
}