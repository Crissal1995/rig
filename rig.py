import time
import sys
import praw
import json
import base36
import collections
import threading
import argparse
import pathlib
import datetime
import logging

try:
    import numpy as np
    from sklearn.linear_model import LinearRegression
    has_libs = True
except ImportError:
    np, LinearRegression = [None] * 2
    has_libs = False


description = '''
RIG - Reddit ID Grabber, a script to collect your most wanted IDs on Reddit.
The ID is a six-digit base36 (numbers and ascii letters) unique identifier
used by reddit in the format https://redd.it/abcdef.

First, create an app here: https://www.reddit.com/prefs/apps; then take the ID, the Secret and
(optional) how many repetition (threads) you want with that particular API.

The best way to get more parallelism is launching this script more times with different accounts.
'''

rootLogger = logging.getLogger()
rootLogger.setLevel(logging.INFO)

fileHandler = logging.FileHandler("rig.log")
fileHandler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
rootLogger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
rootLogger.addHandler(consoleHandler)

id_taken = False


class Worker(threading.Thread):
    def __init__(self, target_id, payload):
        super().__init__()
        self.username = payload.username
        self.subreddit = payload.subreddit
        self.client = payload.client
        assert any([self.username, self.subreddit]), 'No username nor subreddit provided!'
        # preferenza per subreddit se fornito
        self.where_to_post = self.subreddit or 'u_{}'.format(self.username)
        self.target_id = target_id
        self.target_id_decoded = base36.loads(target_id)

    def run(self):
        global id_taken

        rootLogger.info('{} started'.format(self.name))
        sub = self.client.subreddit(self.where_to_post)
        title = self.target_id.upper()
        while True:
            try:
                post = sub.submit(
                    title=title,
                    selftext='This is not the one'
                )
            except Exception as e:
                rootLogger.error('{}, while submitting, terminated for an exception: {}'.format(self.name, e))
                return

            distance = self.target_id_decoded - base36.loads(post.id)
            rootLogger.info('Distance: {d}, posted ID: {i}'.format(d=distance, i=post.id))
            if distance > 0:
                try:
                    post.delete()
                except Exception as e:
                    rootLogger.error('{}, while deleting > 0, terminated for an exception: {}'.format(self.name, e))
                    return
                else:
                    continue
            elif distance == 0:
                rootLogger.info('Congrats! You won your ID "{}"'.format(self.target_id))
                id_taken = True  # è thread_safe grazie all'unicità degli ID
                try:
                    post.edit('You did it! You did it!'.upper())
                except Exception as e:
                    rootLogger.error('{}, while editing == 0, terminated for an exception: {}'.format(self.name, e))
                finally:
                    return
            elif distance < 0:
                rootLogger.info('ID "{}" passed'.format(self.target_id))
                try:
                    post.delete()
                except Exception as e:
                    rootLogger.error('{}, while deleting < 0, terminated for an exception: {}'.format(self.name, e))
                finally:
                    return


def wait(watch_mode, target_id, reddit):
    subreddit = reddit.subreddit('all')
    rootLogger.info('Entering wait mode...')
    target_id_decoded = base36.loads(target_id) if not watch_mode else None
    min_distance = 270

    if has_libs:
        ids, times = np.array([]), np.array([])
        to_predict = np.array(target_id_decoded).reshape(1, -1)
    else:
        ids, times, to_predict = [None] * 3  # fix assignment warning

    while True:
        max_id, time_id = None, None
        while not max_id:
            max_id = max([base36.loads(s.id) for s in subreddit.new(limit=2)], default=0)
            time_id = time.time()

        if watch_mode:
            rootLogger.info('Last ID: {lastid}'.format(
                lastid=base36.dumps(max_id),
            ))
            hint = max_id + 1500
            rootLogger.info('Try to capture {}'.format(base36.dumps(hint)))
            quit(0)

        if has_libs:
            ids = np.append(ids, max_id)
            times = np.append(times, time_id)
            # rootLogger.info('id {di} found'.format(di=base36.dumps(max_id)))

        if has_libs and len(ids) > 1:
            X, y = ids.reshape(-1, 1), times.reshape(-1, 1)
            reg = LinearRegression().fit(X, y)
            pred = reg.predict(to_predict)  # ndarray
            pred = datetime.datetime.fromtimestamp(pred[0][0])  # datetime
        elif has_libs:
            pred = 'Cannot calculate (need two or more ids)'
        else:
            pred = 'Cannot calculate (need missing libraries)'

        distance = target_id_decoded - max_id

        rootLogger.info('Last ID: {lastid} - Distance: {d} - ETA: {eta}'.format(
            lastid=base36.dumps(max_id),
            d=distance,
            eta=pred
        ))

        if distance <= 0:
            rootLogger.info('ID "{}" passed.'.format(target_id))
            quit(1)
        elif distance <= min_distance:
            rootLogger.info('Exiting wait mode...')
            return
        else:
            tts = round(min(10, distance / 200), 2)
            rootLogger.info('Sleep for {} seconds...'.format(tts))
            time.sleep(tts)


def load_config(config_json_fp):
    config_json = json.load(open(config_json_fp))
    required_fields = ('username', 'password', 'user_agent', 'clients')
    assert all(field in config_json for field in required_fields), \
        'Invalid configuration file! Missing fields, set them correctly'

    username = config_json.get('username')
    password = config_json.get('password')
    user_agent = config_json.get('user_agent')

    clients_list = []
    clients = config_json.get('clients')
    if not clients:
        raise ValueError('Cannot instantiate any PRAW client without API ID and Secret!')

    for client in clients:
        reddit = praw.Reddit(
            username=username,
            password=password,
            user_agent=user_agent,
            client_id=client['id'],
            client_secret=client['secret']
        )
        # https://praw.readthedocs.io/en/latest/code_overview/reddit_instance.html#praw.Reddit.validate_on_submit
        reddit.validate_on_submit = True
        repetitions = max(client.get('repeat', 1), 0)
        clients_list += [reddit] * repetitions

    subreddit = config_json.get('subreddit') or config_json.get('sr') or config_json.get('sub') or config_json.get('r/')
    rootLogger.info('User "{u}" will post in {r}'.format(
        u=username,
        r='r/' + str(subreddit) if subreddit else 'u/' + str(username)
    ))
    Payload = collections.namedtuple('Payload', ['client', 'username', 'subreddit'])
    return [Payload(client=c, username=username, subreddit=subreddit) for c in clients_list]


def start_threads(threads):
    assert threads, 'No thread to start!'
    for thread in threads:
        thread.start()
        time.sleep(.3)
    for thread in threads:
        thread.join()


def main(watch_mode, config_json_fp, target_id=None):
    global id_taken
    assert watch_mode or (not watch_mode and target_id), 'Cannot grab ID without a target!'
    rootLogger.info('Watch mode: {}'.format(watch_mode))
    if not watch_mode:
        rootLogger.info('Looking for post id: {}'.format(target_id))
    payloads = load_config(config_json_fp)
    threads = [Worker(target_id, payload) for payload in payloads] if not watch_mode else None
    wait(watch_mode, target_id, payloads.pop().client)
    start_threads(threads)

    logging.info('"{t}" {status}'.format(
        t=target_id,
        status='TAKEN' if id_taken else 'LOST'
    ))
    quit(0 if id_taken else 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=description.strip())
    parser.add_argument('-p', '--post-id', type=str,
                        help='The ID you want to capture. If not specified, will start in watch mode')
    parser.add_argument('-c', '--config', type=str,
                        help='JSON configuration file with your credentials. Defaults to config.json',
                        default='config.json')
    parser.add_argument('-w', '--watch', action='store_true',
                        help='Force watch mode instead of grabbing')
    args = parser.parse_args()

    _watch_mode = bool(args.watch) or not bool(args.post_id)
    post_id = None
    if not _watch_mode:
        post_id = args.post_id.lower()
        assert len(post_id) == 6, 'Wrong ID format, must specify 6 base36 chars'
        _ = base36.loads(post_id)  # assert valid base36 format

    config_fp = pathlib.Path(str(args.config))
    assert config_fp.exists(), 'Cannot find {}'.format(config_fp)
    rootLogger.info('"{}" set for configuration...'.format(args.config))

    main(_watch_mode, config_fp, target_id=post_id)
