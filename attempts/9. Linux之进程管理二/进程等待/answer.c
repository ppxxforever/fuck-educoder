#include <unistd.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <stdio.h>

/************************
 * 返回值: 调用成功且子进程正常退出返回退出代码，否则返回-1
*************************/
int waitProcess()
{
	int status = -1;
	/********** BEGIN **********/
	pid_t pid = fork();
	if (pid == -1)
	{
		return -1;
	}
	else if (pid == 0)
	{
		_exit(22);
	}
	else
	{
		if (waitpid(pid, &status, 0) == -1)
		{
			return -1;
		}
		if (WIFEXITED(status))
		{
			return WEXITSTATUS(status);
		}
		return -1;
	}
	/********** END **********/
	
	return status;
}