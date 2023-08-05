#!/bin/bash
#SBATCH -J sshrt
#SBATCH -p normal
#SBATCH -N 1
#SBATCH -o %x.out
#SBATCH -e %x.err

python server-linux.py
