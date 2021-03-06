#!/usr/bin/env python
# encoding: utf-8

"""
timeME - simple time tracker 

Note: create config.env and add DROPBOX_ACCESS_TOKEN to be able to commit files to your dropbox

Usage:
  ti (o|on) <name> [<time>...]
  ti (f|fin) [<time>...]
  ti (s|status)
  ti (t|tag) <tag>...
  ti (n|note) <note-text>...
  ti (l|log) [today]
  ti (i|interrupt)
  ti --no-color
  ti -h | --help
  ti (c|comm) 

Options:
  -h --help         Show this help.
  <start-time>...   A time specification.
  <tag>...          Tags can be made of any characters, but its probably a good
                    idea to avoid whitespace.
  <note-text>...    Some arbitrary text to be added as `notes` to the currently
                    working project.
"""

from __future__ import print_function
from __future__ import unicode_literals

import json
from datetime import datetime, timedelta
from collections import defaultdict
import re
from os import path, environ, getenv
import sys
from dotenv import load_dotenv
import dropbox

from colorama import *

class JsonStore(object):

    def __init__(self, filename):
        self.filename = filename

    def load(self):

        if path.exists(self.filename):
            with open(self.filename) as f:
                data = json.load(f)

        else:
            data = {'work': [], 'interrupt_stack': []}

        return data

    def dump(self, data):
        with open(self.filename, 'w') as f:
            json.dump(data, f, separators=(',', ': '), indent=2)


def red(str):
    if use_color:
        return Fore.RED + str + Fore.RESET
    else:
        return str

def green(str):
    if use_color:
        return Fore.GREEN + str + Fore.RESET
    else: 
        return str

def yellow(str):
    if use_color: 
        return Fore.YELLOW + str + Fore.RESET
    else:
        return str

def blue(str):
    if use_color: 
        return Fore.BLUE + str + Fore.RESET
    else:
        return str

def action_commit():
    access_key = environ.get("DROPBOX_ACCESS_TOKEN")
    data = store.load

    dbx = dropbox.Dropbox(access_key)
    time_sheet_file_path = path.join(path.dirname(__file__), '.ti-sheet.json')
    print("Uploading file to dropbox")
    with open(time_sheet_file_path, "rb") as f:
        dbx.files_upload(f.read(),'/.time-sheet.json', mode=dropbox.files.WriteMode('overwrite'))
    print("Upload finished")


def action_on(name, time, interrupt_task=False):
    data = store.load()
    work = data['work']

    if work and 'end' not in work[-1]:
        print('You are already working on ' + yellow(work[-1]['name']) +
                '. Stop it or use a different sheet.', file=sys.stderr)
        raise SystemExit(1)

    entry = {
        'name': name,
        'start': time,
    }

    work.append(entry)
    store.dump(data)

    coloured_name = green(name)
    if interrupt_task:
      coloured_name = blue(name)
      action_tag(['interrupt'])

    print('Started on ' + coloured_name + '.')
    action_commit()



def action_fin(time, back_from_interrupt=True):
    ensure_working()

    data = store.load()

    current = data['work'][-1]
    current['end'] = time
    time_diff = round((parse_isotime(time) - parse_isotime(current['start'])).seconds / 60.00, 2)
    current['total_mins'] = time_diff

    store.dump(data)
    print('So you stopped working on ' + red(current['name']) + '.')

    if back_from_interrupt and len(data['interrupt_stack']) > 0:
        name = data['interrupt_stack'].pop()['name']
        store.dump(data)
        action_on(name, time)
        if len(data['interrupt_stack']) > 0:
            print('You are now %d deep in interrupts.' % len(data['interrupt_stack']))
        else:
            print('Congrats, you\'re out of interrupts!')
    action_commit()


def action_interrupt(name, time):
    ensure_working()

    action_fin(time, back_from_interrupt=False)

    data = store.load()
    if 'interrupt_stack' not in data:
        data['interrupt_stack'] = []
    interrupt_stack = data['interrupt_stack']
    work = data['work']

    interrupted = data['work'][-1]
    interrupt_stack.append(interrupted)
    store.dump(data)

    action_on(name, time, True)
    print('You are now %d deep in interrupts.' % len(interrupt_stack))
    action_commit()



def action_note(content):
    ensure_working()

    data = store.load()
    current = data['work'][-1]

    if 'notes' not in current:
        current['notes'] = [content]
    else:
        current['notes'].append(content)

    store.dump(data)

    print('Yep, noted to ' + yellow(current['name']) + '.')
    action_commit()



def action_tag(tags):
    ensure_working()

    data = store.load()
    current = data['work'][-1]

    current['tags'] = set(current.get('tags') or [])
    current['tags'].update(tags)
    current['tags'] = list(current['tags'])

    store.dump(data)

    tag_count = len(tags)
    print('Okay, tagged current work with ' + str(tag_count) + ' tag' +
            ('s' if tag_count > 1 else '') + '.')
    action_commit()


def action_status():
    try:
        ensure_working()
    except SystemExit(1):
        return

    data = store.load()
    current = data['work'][-1]

    start_time = parse_isotime(current['start'])
    diff = timegap(start_time, datetime.utcnow())

    print('You have been working on {0} for {1}.'
            .format(green(current['name']), diff))

def action_log(period):
    data = store.load()
    work = data['work'] + data['interrupt_stack']
    log = defaultdict(lambda: {'delta': timedelta()})
    current = None

    for item in work:
        start_time = parse_isotime(item['start'])
        if 'end' in item:
            log[item['name']]['delta'] += parse_isotime(item['end']) - start_time
        else:
            log[item['name']]['delta'] += datetime.utcnow() - start_time
            current = item['name']

    name_col_len = 0

    for name, item in log.items():
        name_col_len = max(name_col_len, len(name))

        secs = item['delta'].seconds
        tmsg = []

        if secs > 3600:
            hours = int(secs / 3600)
            secs -= hours * 3600
            tmsg.append(str(hours) + ' hour' + ('s' if hours > 1 else ''))

        if secs > 60:
            mins = int(secs / 60)
            secs -= mins * 60
            tmsg.append(str(mins) + ' minute' + ('s' if mins > 1 else ''))

        if secs:
            tmsg.append(str(secs) + ' second' + ('s' if secs > 1 else ''))

        log[name]['tmsg'] = ', '.join(tmsg)[::-1].replace(',', ' &'[::-1], 1)[::-1]

    for name, item in sorted(log.items(), key=(lambda x: x[1]['delta']), reverse=True):
        print(name.ljust(name_col_len), ' ∙∙ ', item['tmsg'],
                end=' ← working\n' if current == name else '\n')


def is_working():
    data = store.load()
    return data.get('work') and 'end' not in data['work'][-1]


def ensure_working():
    if is_working(): return

    print("For all I know, you aren't working on anything."
            " I don't know what to do.", file=sys.stderr)
    print('See `timeME -h` to know how to start working.', file=sys.stderr)
    raise SystemExit(1)


def to_datetime(timestr):
    return parse_engtime(timestr).isoformat() + 'Z'


def parse_engtime(timestr):

    now = datetime.utcnow()
    if not timestr or timestr.strip() == 'now':
        return now

    match = re.match(r'(\d+|a) \s* (s|secs?|seconds?) \s+ ago $', timestr, re.X)
    if match is not None:
        n = match.group(1)
        seconds = 1 if n == 'a' else int(n)
        return now - timedelta(seconds=seconds)

    match = re.match(r'(\d+|a) \s* (mins?|minutes?) \s+ ago $', timestr, re.X)
    if match is not None:
        n = match.group(1)
        minutes = 1 if n == 'a' else int(n)
        return now - timedelta(minutes=minutes)

    match = re.match(r'(\d+|a|an) \s* (hrs?|hours?) \s+ ago $', timestr, re.X)
    if match is not None:
        n = match.group(1)
        hours = 1 if n in ['a', 'an'] else int(n)
        return now - timedelta(hours=hours)

    raise ValueError("Don't understand the time '" + timestr + "'")


def parse_isotime(isotime):
    return datetime.strptime(isotime, '%Y-%m-%dT%H:%M:%S.%fZ')


def timegap(start_time, end_time):
    diff = end_time - start_time

    mins = diff.seconds / 60

    if mins == 0:
        return 'less than a minute'
    elif mins == 1:
        return 'a minute'
    elif mins < 44:
        return '{} minutes'.format(mins)
    elif mins < 89:
        return 'about an hour'
    elif mins < 1439:
        return 'about {} hours'.format(mins / 60)
    elif mins < 2519:
        return 'about a day'
    elif mins < 43199:
        return 'about {} days'.format(mins / 1440)
    elif mins < 86399:
        return 'about a month'
    elif mins < 525599:
        return 'about {} months'.format(mins / 43200)
    else:
        return 'more than a year'


def helpful_exit(msg=__doc__):
    print(msg, file=sys.stderr)
    raise SystemExit


def parse_args(argv=sys.argv):
    global use_color

    if '--no-color' in argv:
        use_color = False
        argv.remove('--no-color')

    # prog = argv[0]
    if len(argv) == 1:
        helpful_exit('You must specify a command.')

    head = argv[1]
    tail = argv[2:]
      
    if head in ['-h', '--help', 'h', 'help']:
        helpful_exit()

    elif head in ['o', 'on']:
        if not tail:
            helpful_exit('Need the name of whatever you are working on.')

        fn = action_on
        args = {
            'name': tail[0],
            'time': to_datetime(' '.join(tail[1:])),
        }

    elif head in ['f', 'fin']:
        fn = action_fin
        args = {'time': to_datetime(' '.join(tail))}

    elif head in ['s', 'status']:
        fn = action_status
        args = {}

    elif head in ['c','comm']:
        fn = action_commit
        args = {}

    elif head in ['l', 'log']:
        fn = action_log
        args = {'period': tail[0] if tail else None}

    elif head in ['t', 'tag']:
        if not tail:
            helpful_exit('Please provide at least one tag to add.')

        fn = action_tag
        args = {'tags': tail}

    elif head in ['n', 'note']:
        if not tail:
            helpful_exit('Please provide some text to be noted.')

        fn = action_note
        args = {'content': ' '.join(tail)}

    elif head in ['i', 'interrupt']:
        if not tail:
            helpful_exit('Need the name of whatever you are working on.')

        fn = action_interrupt
        args = {
            'name': tail[0],
            'time': to_datetime(' '.join(tail[1:])),
        }

    else:
        helpful_exit("I don't understand '" + head + "'")

    return fn, args


def main():
    fn, args = parse_args()
    fn(**args)


store = JsonStore(getenv('SHEET_FILE', None) or
                    path.join(path.dirname(__file__), '.ti-sheet.json'))

#Loading Configuraton
dotenv_path = path.join(path.dirname(__file__), 'config.env')
load_dotenv(dotenv_path)

if __name__ == '__main__':
    use_color = True
    main()