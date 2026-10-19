"""Build a standalone worker from the authoritative runtime package."""
import argparse
from caesar_rest.pipeline_worker_bundle import build_archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='New .pyz file; existing files are not overwritten')
    args = parser.parse_args()
    print('Worker SHA-256:', build_archive(args.output))


if __name__ == '__main__':
    main()
