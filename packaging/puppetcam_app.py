"""Entry point of the installed app: the tray, or the command line when given arguments.

``Puppetcam.app/Contents/MacOS/puppetcam doctor`` still works from a terminal.
"""

import sys

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-psn_")]  # old macOS adds -psn_0_1234
    if args:
        from puppetcam.cli import main

        main(args)
    else:
        from puppetcam.tray import main

        main()
