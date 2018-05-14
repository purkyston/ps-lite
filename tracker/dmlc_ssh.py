#!/usr/bin/env python
"""
DMLC submission script by ssh

One need to make sure all slaves machines are ssh-able.
"""

import argparse
import sys
import os
import subprocess
import tracker
import logging
from threading import Thread

class SSHLauncher(object):
    def __init__(self, args, unknown):
        self.args = args
        self.cmd = (' '.join(args.command) + ' ' + ' '.join(unknown))

        assert args.hostfile is not None
        with open(args.hostfile) as f:
            hosts = f.readlines()
        assert len(hosts) > 0
        self.hosts=[]
        for h in hosts:
            if len(h.strip()) > 0:
                self.hosts.append(h.strip())

        self.train_file = args.train_file

    def sync_dir(self, local_dir, slave_node, slave_dir):
        """
        sync the working directory from root node into slave node
        """
        remote = slave_node + ':' + slave_dir
        logging.info('rsync %s -> %s', local_dir, remote)

        # TODO uses multithread
        prog = 'rsync -az --rsh="ssh -o StrictHostKeyChecking=no" %s %s' % (
            local_dir, remote)
        subprocess.check_call([prog], shell = True)

    def sync_file(self, local_file, slave_node, slave_file):
        remote = slave_node + ':' + slave_file
        logging.info('rsync %s -> %s', local_file, remote)
        prog = 'rsync -az --rsh="ssh -o StrictHostKeyChecking=no" %s %s' % (
            local_file, remote
        )
        subprocess.check_call([prog], shell = True)

    def get_env(self, pass_envs):
        envs = []
        # get system envs
        keys = ['LD_LIBRARY_PATH', 'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY']
        for k in keys:
            v = os.getenv(k)
            if v is not None:
                envs.append('export ' + k + '=' + v + ';')
        # get ass_envs
        for k, v in pass_envs.items():
            envs.append('export ' + str(k) + '=' + str(v) + ';')
        return (' '.join(envs))

    def submit(self):
        def ssh_submit(nworker, nserver, pass_envs):
            """
            customized submit script
            """
            # thread func to run the job
            def run(prog):
                subprocess.check_call(prog, shell = True)

            # sync programs if necessary
            local_dir = os.getcwd()+'/'
            working_dir = local_dir
            if self.args.sync_dir is not None:
                working_dir = self.args.sync_dir
                for h in self.hosts:
                    self.sync_dir(local_dir, h, working_dir)

            train_file_list = []
            if self.args.train_file is not None:
                local_file = self.args.train_file
                with open(local_file, 'r') as fin:
                    data = fin.readlines()
                    print len(data)
                    cur_row = 0
                    num = int(len(data) * 1.0 / nworker)
                    for i in range(nworker):
                        filename = os.path.basename(local_file)
                        sliced_file = '/tmp/' + filename + '_' + str(i)
                        dst_file = sliced_file + '.copy'
                        train_file_list.append((sliced_file,dst_file))
                        with open(sliced_file, 'w') as fout:
                            fout.writelines(data[cur_row: cur_row + num])
                        cur_row += num

            # launch jobs
            print len(train_file_list)
            worker_count = 0
            for i in range(nworker + nserver):
                pass_envs['DMLC_ROLE'] = 'server' if i < nserver else 'worker'
                node = self.hosts[i % len(self.hosts)]
                prog = self.get_env(pass_envs) + ' cd ' + working_dir + '; ' + self.cmd
                if self.args.train_file is not None and pass_envs['DMLC_ROLE'] == 'worker':
                    self.sync_file(train_file_list[worker_count][0], node, train_file_list[worker_count][1])
                    prog += ' ' + train_file_list[worker_count][1]
                    worker_count += 1
                prog = 'ssh -o StrictHostKeyChecking=no ' + node + ' \'' + prog + '\''

                thread = Thread(target = run, args=(prog,))
                thread.setDaemon(True)
                thread.start()

        return ssh_submit

    def run(self):
        tracker.config_logger(self.args)
        tracker.submit(self.args.num_workers,
                       self.args.num_servers,
                       fun_submit = self.submit(),
                       pscmd = self.cmd)

def main():
    parser = argparse.ArgumentParser(description='DMLC script to submit dmlc job using ssh')
    parser.add_argument('-n', '--num-workers', required=True, type=int,
                        help = 'number of worker nodes to be launched')
    parser.add_argument('-s', '--num-servers', default = 0, type=int,
                        help = 'number of server nodes to be launched')
    parser.add_argument('-H', '--hostfile', type=str,
                        help = 'the hostfile of all slave nodes')
    parser.add_argument('command', nargs='+',
                        help = 'command for dmlc program')
    parser.add_argument('--sync-dir', type=str,
                        help = 'if specificed, it will sync the current \
                        directory into slave machines\'s SYNC_DIR')
    parser.add_argument('--train-file', type=str,
                        help = 'must be specificed, \
                               tracker will slice train data automatically')

    args, unknown = parser.parse_known_args()

    launcher = SSHLauncher(args, unknown)
    launcher.run()

if __name__ == '__main__':
    main()
