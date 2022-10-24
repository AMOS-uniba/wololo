#!/usr/bin/env python

"""
    Bulk file copy and AVI conversion utility for AMOS.
    Requires a YAML configuration file (can be overriden with arguments).
    Version 2022.10.24
    Ⓒ Kvík, 2021-2022


    For use in production you should create an EXE file with `pyinstaller.exe --onefile sightings.py`,
    see pyinstaller documentation.
"""

from pathlib import Path
from pprint import pprint as pp
import os
import argparse
import re
import shutil
import logging
import yaml
import dotmap
import datetime
import subprocess

import colour as c
import log

logger = log.setupLog('root')


class ReadableDir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if not Path(values).is_dir():
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a valid path".format(values))
        if os.access(values, os.R_OK):
            setattr(namespace, self.dest, values)
        else:
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a readable directory".format(values))


class WriteableDir(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if not os.path.isdir(values):
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a valid path".format(values))
        if os.access(values, os.W_OK):
            setattr(namespace, self.dest, values)
        else:
            raise argparse.ArgumentTypeError("readable_dir: {0} is not a writeable directory".format(values))


def format_boolean(condition, yes='yes', no=' no'):
    return c.ok(yes) if condition else c.err(no)


class SightingManager():
    def __init__(self):
        self.create_argparser()
        self.load_config()

        logger.info("AMOS sighting synchronization and conversion utility")
        logger.info(f"Source directory {c.path(str(self.source_dir))}, target directory {c.path(str(self.target_dir))}")
        if self.config.convert_video:
            logger.info(f"Videos will be converted to {c.param(self.config.video.codec)}, pixel format {c.param(self.config.video.pixel_format)}")
        else:
            logger.info(f"Videos {c.warn('will not')} be converted, only copied")
        logger.info(f"This is a {c.warn('dry run') if self.dry_run else c.ok('real run')}: " \
            f"copy files: {format_boolean(self.config.copy_files)}, delete old files: {format_boolean(self.config.delete_files)}")

        if self.args.debug:
            logger.info("Config is")
            self.config.pprint()

    def create_argparser(self):
        self.parser = argparse.ArgumentParser(description="Synchronize AMOS sightings")
        self.parser.add_argument('ini', type=argparse.FileType('r'), help="YAML configuration file")
        self.parser.add_argument('-s', '--source', action=ReadableDir, help="Override <source> directory")
        self.parser.add_argument('-t', '--target', action=WriteableDir, help="Override <target> directory")
        self.parser.add_argument('-o', '--older-than', type=int, help="Override <older_than>")
        self.parser.add_argument('-C', '--copy', action='store_true', help="Copy or convert files")
        self.parser.add_argument('-D', '--delete', action='store_true', help="Delete files older than <older_than>")
        self.parser.add_argument('-V', '--convert-video', action='store_true', help="Convert video files")
        self.parser.add_argument('-d', '--debug', action='store_true', help="Turn on more verbose output")
        self.args = self.parser.parse_args()

    def load_config(self):
        self.config = dotmap.DotMap(yaml.safe_load(self.args.ini), _dynamic=False)
        self.config.convert_video = False

        if self.args.source is not None:
            logger.warning(f"Overriding source {c.param(self.config.source)} from command line to {c.param(self.args.source)}")
            self.config.source = self.args.source
        if self.args.target is not None:
            logger.warning(f"Overriding target {c.param(self.config.target)} from command line to {c.param(self.args.target)}")
            self.config.target = self.args.target
        if self.args.older_than is not None:
            logger.warning(f"Overriding older_than {c.param(self.config.older_than)} from command line to {c.param(self.args.older_than)}")
            self.config.older_than = self.args.older_than
        if self.args.convert_video:
            logger.warning(f"Overriding convert_video {c.param(self.config.convert_video)} from command line to {c.param(self.args.convert_video)}")
            self.config.convert_video = True

        self.config.copy_files = True if self.args.copy else False
        self.config.delete_files = True if self.args.delete else False

        self.source_dir = Path(self.config.source)
        self.target_dir = Path(self.config.target)
        self.dry_run = not (self.config.copy_files or self.config.delete_files)

    def run(self):
        start = datetime.datetime.utcnow()
        files = self.source_dir.rglob('*.*')
        processed = 0
        process_failed = 0
        processed_size = 0
        reclaimed_size = 0
        deleted = 0
        delete_failed = 0
        deleted_size = 0
        inspected = 0
        inspected_size = 0

        for file in sorted(files):
            source_path = Path(file)
            target_dir = Path(str(file.parent).replace(str(self.source_dir), str(self.target_dir)))
            target_path = Path(target_dir / file.name)
            try:
                source_age = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(file.stat().st_mtime)

                inspected += 1
                inspected_size += source_path.stat().st_size

                is_updated = False
                if is_copied := target_path.exists():
                    target_age = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(target_path.stat().st_mtime)
                    if source_age < target_age:
                        is_updated = True

                is_old = (source_age.days >= self.config.older_than)

                should_process = not is_copied or is_updated and self.config.copy_files
                should_delete = is_old and is_copied and self.config.delete_files

                logger.info(f"{c.path(file):<85} age {c.num(source_age.days):>13} d, " \
                    f"old: {format_boolean(is_old)} " \
                    f"copied: {format_boolean(is_copied)} " \
                    f"newer: {format_boolean(is_updated)} " \
                    f"process: {format_boolean(should_process)}, " \
                    f"delete: {format_boolean(should_delete)}")

                if should_process:
                    try:
                        size = self.process(source_path, target_path)
                        processed += 1
                        processed_size += source_path.stat().st_size
                        reclaimed_size += size
                    except OSError as e:
                        logger.error(f"Processing failed: {e}")
                        process_failed += 1
                    except FileNotFoundError as e:
                        process_failed += 1
                        raise e

                if should_delete:
                    try:
                        size = source_path.stat().st_size
                        self.delete(source_path)
                        deleted += 1
                        deleted_size += size
                    except OSError as e:
                        logger.error(f"Deletion failed: {e}")
                        delete_failed += 1
                    except FileNotFoundError as e:
                        delete_failed += 1
                        raise e
            except FileNotFoundError as e:
                logger.error(f"File not found, skipping: {e}")


        logger.info(f"{c.num(inspected)} files ({c.num(f'{inspected_size / 2**20:6.0f}')} MB) inspected")
        logger.info(f"  - {c.num(processed)} ({c.num(f'{processed_size / 2**20:6.0f}')} MB) " \
                    f"{'copied' if self.config.copy_files else 'to copy'} ({(c.ok if process_failed == 0 else c.err)(process_failed)} failed)")
        logger.info(f"     - {c.num(f'{(reclaimed_size) / 2**20:6.0f}')} MB reclaimed by reencoding")
        logger.info(f"  - {c.num(deleted)} ({c.num(f'{deleted_size / 2**20:6.0f}')} MB) " \
                    f"{'deleted' if self.dry_run else 'to delete'} ({(c.ok if delete_failed == 0 else c.err)(delete_failed)} failed)")

        if self.dry_run:
            logger.info(f"This was a {c.warn('dry run')}, no files were actually copied or deleted")

        logger.info(f"Finished in {datetime.datetime.utcnow() - start}")

    def inspect_video_header(self, path):
        """ Inspect the video header for the faulty "Y16 " and if found, change it to "Y800" """
        with open(path, 'r+b') as file:
            file.seek(188)
            format = file.read(4)

            if format == b'Y16 ':
                logger.warning(f"File {c.path(str(path))}: fixing video header from {c.param('Y16 ')} to {c.param('Y800')}")
                file.seek(188)
                file.write(b'Y800')


    def delete(self, path):
        """ Conditionally delete the specified file """
        logger.info(f"{'Deleting' if self.config.delete_files else 'Would delete'} file {c.path(str(path))}")
        if self.config.delete_files:
            try:
                path.unlink()
            except OSError as e:
                logger.error(f"Could not delete {str(path)}: {e.strerror}")
                raise e

    def process(self, source, target):
        """ Conditionally process the specified file: convert the video and copy all other files """
        logger.debug(f"{'Processing' if self.config.copy_files else 'Would process'} file {c.path(str(source))}")

        if source.suffix == '.avi' and self.config.convert_video:
            return self.convert_avi(source, target, self.config.video.codec)
        else:
            return self.copy(source, target)

    def copy(self, source, target):
        """ Conditionally copy the specified file <source> to <target> """
        logger.info(f"{'Copying' if self.config.copy_files else 'Would copy'} {c.path(source)} to {c.path(target)}")

        if self.config.copy_files:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)

        return 0

    def convert_avi(self, source, target, codec='rawvideo', pixel_format='gray'):
        """ Conditionally convert the specified AVI file to the new format using ffmpeg """
        if not source.exists():
            return 0

        self.inspect_video_header(source)
        target.parent.mkdir(parents=True, exist_ok=True)

        loglevel = 32 if self.args.debug else 24
        commands = [
            self.config.ffmpeg,
            "-hide_banner",                         # do not show config every time
            "-y",                                   # automatically answer "yes" to all questions
            "-i", str(source),                      # input file
            "-loglevel", str(loglevel),             # do not show ffmpeg logs
            "-c:v", codec,                          # output codec
        ]
        # For x264 we also need to set the quantization parameter to 0 for lossless
        if codec == 'libx264':
            commands += ['-qp', '0']
        commands += [
            "-pix_fmt", pixel_format,               # pixel format
            str(target),                            # output file
        ]

        logger.info(f"{'Converting' if self.config.copy_files else 'Would convert'} {c.path(str(source))} to {c.path(target)}")

        if self.config.copy_files:
            cp = subprocess.run(commands)
            if cp.returncode != 0:
                raise OSError()

            return source.stat().st_size - target.stat().st_size
        else:
            logger.info(f"Would run {' '.join(commands)}")
            return 0


sm = SightingManager()
sightings = sm.run()