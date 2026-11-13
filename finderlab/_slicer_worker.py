"""POSIX resource-limited exec helper; invoked only by slicer.py, not a shell."""

import os
import resource
import sys


def main():
    memory, file_size, cpu = map(int, sys.argv[1:4])
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_FSIZE, (file_size, file_size))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.execv(sys.argv[4], sys.argv[4:])


if __name__ == "__main__":
    main()
