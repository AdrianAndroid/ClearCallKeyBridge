"""打包入口：双击 .app 时等同 `python -m clearcall200 --ui`。"""
import sys

from clearcall200.__main__ import main

if __name__ == "__main__":
    sys.exit(main(["--ui"] + sys.argv[1:]))
