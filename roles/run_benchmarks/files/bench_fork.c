/* Fork/exec rate benchmark.
   Forks N child processes sequentially, each child execs /bin/true and exits.
   Parent waits for each child before forking the next.
   Compile: gcc -O2 -o bench_fork bench_fork.c
   Run:     ./bench_fork 1000                    */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

int main(int argc, char **argv) {
    int n = argc > 1 ? atoi(argv[1]) : 1000;
    for (int i = 0; i < n; i++) {
        pid_t pid = fork();
        if (pid < 0) { perror("fork"); return 1; }
        if (pid == 0) {
            /* child: exec /bin/true and exit */
            execl("/bin/true", "true", (char *)NULL);
            _exit(127);
        }
        int status;
        waitpid(pid, &status, 0);
    }
    printf("forked %d processes\n", n);
    return 0;
}
