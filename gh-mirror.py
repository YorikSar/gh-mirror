"""Mirrors number of GitHub repositories."""
import argparse
import logging
import os.path
import re
import shutil
import signal
import subprocess
import sys
import urllib2
import HTMLParser


class GHRepoListParser(HTMLParser.HTMLParser):
    def __init__(self):
        HTMLParser.HTMLParser.__init__(self)
        self.level = 0
        self.repos = []

    def handle_starttag(self, tag, attrs):
        if self.level == 0:
            if tag == 'li':
                try:
                    classes = filter(lambda p: p[0] == 'class', attrs)[0][1]
                except IndexError:
                    pass
                else:
                    if classes == 'public source':
                        self.level = 1
        elif self.level == 1:
            if tag == 'h3':
                self.level = 2
        elif self.level == 2:
            if tag == 'a':
                self.level = 3
    
    def handle_data(self, data):
        if self.level == 3:
            self.repos.append(data)
            self.level = 0


def get_user_repos(user):
    url = 'http://github.com/%s/' % (user,)
    logging.debug('Fetching URL %s', url)
    response = urllib2.urlopen(url)
    logging.debug('Got response code %d', response.code)
    if response.code != 200:
        raise Exception('Got failure from GitHub server')
    data = response.read()
    logging.debug('Got %d bytes', len(data))
    try:
        content_type = response.headers['content-type']
        m = re.search('charset=([^; ]+)', content_type)
        encoding = m.group(1)
    except KeyError:
        encoding = 'ascii'
    parser = GHRepoListParser()
    parser.feed(data.decode(encoding))
    result = parser.repos
    logging.debug('Found repos: %s', result)
    return result


def ensure_exists(args, username):
    user_dir = os.path.join(args.target_dir, username)
    if not os.path.exists(user_dir):
        logging.info('Creating missing dir %s', user_dir)
        os.mkdir(user_dir)
        return False, user_dir
    return True, user_dir


class GitError(Exception):
    pass


def git(*args):
    cmd = ('git',) + args
    logging.debug("Executing command '%s'", ' '.join(cmd))
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == -signal.SIGINT:
        raise KeyboardInterrupt
    elif p.returncode < 0:
        raise GitError("Process '%s' was terminated by signal %d" % (
            ' '.join(cmd), -p.returncode))
    elif p.returncode > 0:
        raise GitError(
            "Process '%s' returned code %d.\nstdout:\n%s\nstderr:%s\n" % (
                ' '.join(cmd), p.returncode, out, err))


def sync_repo(user_dir, username, repo):
    repo_path = os.path.join(user_dir, repo)
    repo_url = 'git://github.com/%s/%s' % (username, repo)
    logging.info('Syncing %s with %s.', repo_path, repo_url)
    try:
        if os.path.exists(repo_path):
            git('--git-dir', repo_path, 'fetch')
        else:
            git('clone', '--mirror', repo_url, repo_path)
    except GitError as ex:
        log.error('Sync failed: %s', ex)
        return False
    else:
        return True


def main():
    argparser = argparse.ArgumentParser(description=__doc__)
    argparser.add_argument('repos', metavar='SPEC', nargs='+', type=unicode,
            help="repository or user spec (e.g. username or username/repo)")
    argparser.add_argument('--target-dir', '-D',
            help="directory to store repositories")
    argparser.add_argument('--verbose', '-v', dest='verbose',
            action='store_const', const=1, default=0)
    argparser.add_argument('--debug', '-d', dest='verbose',
            action='store_const', const=2)
    args = argparser.parse_args()

    logging.basicConfig(
            level=(logging.WARNING, logging.INFO, logging.DEBUG)[args.verbose])

    repos = []
    good = True
    for spec in args.repos:
        spl = spec.split('/')
        if len(spl) == 1:
            username = spl[0]
            repos = get_user_repos(username)
            existed, user_dir = ensure_exists(args, username)
            for item in os.listdir(user_dir):
                path = os.path.join(user_dir, item)
                if os.path.isdir(path) and item not in repos:
                    logging.info('Deleting repo missing at GitHub %s', path)
                    shutil.rmtree(path)
            for repo in repos:
                good = good and sync_repo(user_dir, username, repo)
        elif len(spl) == 2:
            existed, user_dir = ensure_exists(args, spl[0])
            good = good and sync_repo(user_dir, *spl)
        else:
            logging.error('Bad spec: %s', spec)
            return 1

if __name__ == '__main__':
    sys.exit(main())
