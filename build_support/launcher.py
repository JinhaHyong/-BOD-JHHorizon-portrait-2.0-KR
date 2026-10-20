"""Normal startup plus an explicit, isolated check for the frozen bundle."""

import sys

if __name__ == '__main__':
    if '--deployment-check' in sys.argv:
        from build_support.deployment_check import run
        position = sys.argv.index('--deployment-check')
        if len(sys.argv) <= position + 1:
            sys.exit(2)
        sys.exit(run(sys.argv[position + 1]))
    from main import main
    sys.exit(main())
