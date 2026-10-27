#include <stdio.h>
#include <stdlib.h>
#include <string.h>  
#include <unistd.h> 
#include<sys/types.h> 
#include<sys/wait.h>
int g_i4event;
int father_son(void)
{
    /********Begin********/
    pid_t pid = fork();
    if (pid == 0) {
        g_i4event = 1;
        sleep(2);
        exit(0);
    } else {
        sleep(1);
        g_i4event = 2;
        exit(0);
    }
    /*********End*********/
}
int son_father_nowait(void)
{
    /********Begin********/
    pid_t pid = fork();
    if (pid == 0) {
        g_i4event = 1;
        sleep(1);
        exit(0);
    } else {
        sleep(2);
        g_i4event = 3;
        exit(0);
    }
    /*********End*********/
}
int son_father_wait(void)
{
    /********Begin********/
    pid_t pid = fork();
    if (pid == 0) {
        g_i4event = 1;
        sleep(1);
        exit(0);
    } else {
        wait(NULL);
        sleep(1);
        g_i4event = 4;
        exit(0);
    }
    /*********End*********/
}