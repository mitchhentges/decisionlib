import argparse

from decisionlib.hook import schedule_hook
from decisionlib.shell import fetch_secret


def main():
    print('"decisionlib" is just a (py3) library, you need (py2) "decisionlib-cli" to schedule'
          'hook decision tasks or use helper utilities')
    exit(1)


if __name__ == '__main__':
    main()
