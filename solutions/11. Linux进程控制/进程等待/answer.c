#include <stdio.h>
#include <stdlib.h>
#include <string.h>  
#include <unistd.h> 
#include<sys/types.h> 
#include<sys/wait.h>

int g_i4event;
int process_wait(void)
{
    /********Begin********/
    pid_t pid = fork();
    if (pid == 0)
    {
        sleep(3);
        exit(0);
    }
    else if (pid > 0)
    {
        g_i4event = 1;
        sleep(1);
        g_i4event = 2;
        int status = 0;
        wait(&status);
        g_i4event = 3;
    }
    return 0;
    /*********End*********/
}

int process_waitpid(void)
{
    /********Begin********/
    pid_t pid = fork();
    if (pid == 0)
    {
        sleep(3);
        exit(0);
    }
    else if (pid > 0)
    {
        g_i4event = 1;
        sleep(1);
        g_i4event = 2;
        int status = 0;
        waitpid(pid, &status, 0);
        g_i4event = 3;
    }
    return 0;
    /*********End*********/
}