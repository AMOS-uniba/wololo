import argparsedirs
import datetime
import logging
import colorama
from pathlib import Path

import scalyca.exceptions
from schema import Schema, And, Or, Optional

from scalyca import colour as c, Scalyca

from classes.processor import FileProcessor
from utils.functions import format_boolean

log = logging.getLogger(__name__)
colorama.init()


class TreeConvertor(Scalyca):
    _version = '2Ö24-11-25'
    _prog = "Wololo"
    _schema = Schema({
        'source': And(Path, argparsedirs.ReadableDirType),
        'target': And(Path, argparsedirs.WriteableDirType),
        'ffmpeg': Path,
        'ffprobe': Path,
        'older_than': int,
        'video': {
            'codec': Or('libx264', 'rawvideo', 'ffv1'),
            'pixel_format': Or('rgba', 'gray'),
            'convert': Optional(bool),
        },
        'copy_files': bool,
        'delete_files': bool,
    })

    def __init__(self):
        super().__init__()
        self.processor: FileProcessor = None
        self.real_run: bool = False

    def add_arguments(self):
        self.add_argument('-s', '--source', type=argparsedirs.ReadableDirType,
                          help="Override <source> directory")
        self.add_argument('-t', '--target', type=argparsedirs.WriteableDirType,
                          help="Override <target> directory")
        self.add_argument('-o', '--older-than', type=int,
                          help="Delete files older than this many days. Overrides <older_than>")
        self.add_argument('-C', '--copy', action='store_true', default=False,
                          help="Copy or convert files")
        self.add_argument('-D', '--delete', action='store_true', default=False,
                          help="Delete files older than <older_than>")
        self.add_argument('-V', '--convert-video', action='store_true', default=False,
                          help="Convert video files")

    def override_configuration(self):
        if self.args.source:
            self.config.source = self.args.source
        self.config.source = Path(self.config.source)

        if self.args.target:
            self.config.target = self.args.target
        self.config.target = Path(self.config.target)

        if self.config.source == self.config.target:
            raise scalyca.exceptions.ConfigurationError("Source and target may not be the same!")

        self.config.ffmpeg = Path(self.config.ffmpeg)
        self.config.ffprobe = Path(self.config.ffprobe)

        self.config.copy_files = self.args.copy
        self.config.delete_files = self.args.delete
        self.config.video.convert = self.args.convert_video

        if self.args.older_than:
            self.config.older_than = self.args.older_than

        self.real_run = self.config.copy_files or self.config.delete_files

    def initialize(self):
        log.info(f"Source directory {c.path(str(self.config.source))}, "
                 f"target directory {c.path(str(self.config.target))}")

        if self.config.video.convert:
            log.info(f"Videos will be converted to {c.param(self.config.video.codec)}, "
                     f"pixel format {c.param(self.config.video.pixel_format)}")
        else:
            log.info(f"Videos {c.warn('will not')} be converted, only copied")

        log.info(f"This is a {c.ok('real run') if self.real_run else c.warn('dry run')}: "
                 f"copy files: {format_boolean(self.config.copy_files)}, "
                 f"delete old files: {format_boolean(self.config.delete_files)}")

        self.processor = FileProcessor(self.real_run, ffmpeg_path=self.config.ffmpeg, debug=self.args.debug)

    def main(self):
        start = datetime.datetime.now(datetime.UTC)
        files = self.config.source.rglob('*.*')
        processed: int = 0
        process_failed: int = 0
        processed_size: int = 0
        reclaimed_size: int = 0
        deleted: int = 0
        delete_failed: int = 0
        deleted_size: int = 0
        inspected: int = 0
        inspected_size: int = 0

        for file in sorted(files):
            source_path = Path(file)
            target_dir = Path(str(file.parent).replace(str(self.config.source), str(self.config.target)))
            target_path = Path(target_dir / file.name)
            try:
                source_age = datetime.datetime.now(datetime.UTC) - \
                             datetime.datetime.fromtimestamp(file.stat().st_mtime, datetime.UTC)

                inspected += 1
                inspected_size += source_path.stat().st_size

                is_updated = False
                if is_copied := target_path.exists():
                    target_age = datetime.datetime.now(datetime.UTC) - \
                                 datetime.datetime.fromtimestamp(target_path.stat().st_mtime, datetime.UTC)
                    if source_age < target_age:
                        is_updated = True

                is_old = (source_age.days >= self.config.older_than)

                should_process = not is_copied or is_updated and self.config.copy_files
                should_delete = is_old and is_copied and self.config.delete_files

                log.info(f"File age {c.num(source_age.days):>13} d, "
                         f"old: {format_boolean(is_old)} "
                         f"copied: {format_boolean(is_copied)} "
                         f"newer: {format_boolean(is_updated)} "
                         f"process: {format_boolean(should_process)}, "
                         f"delete: {format_boolean(should_delete)}, "
                         f"name: {c.path(file):<85}")

                if should_process:
                    try:
                        size = self.process(source_path, target_path)
                        processed += 1
                        processed_size += source_path.stat().st_size
                        reclaimed_size += size
                    except FileNotFoundError as e:
                        process_failed += 1
                        raise e
                    except OSError as e:
                        log.error(f"Processing failed: {e}")
                        process_failed += 1

                if should_delete:
                    try:
                        deleted_size += self.delete(source_path)
                        deleted += 1
                    except FileNotFoundError as e:
                        delete_failed += 1
                        raise e
                    except OSError as e:
                        log.error(f"Deletion failed: {e}")
                        delete_failed += 1
            except FileNotFoundError as e:
                log.error(f"File not found, skipping: {e}")

        log.info(f"{c.num(inspected)} files ({c.num(f'{inspected_size:_d}')} B) inspected")
        log.info(f"  - {c.num(processed)} ({c.num(f'{processed_size:_d}')} B) "
                 f"{'copied' if self.config.copy_files else 'to copy'} "
                 f"({(c.ok if process_failed == 0 else c.err)(process_failed)} failed)")
        log.info(f"     - {c.num(f'{reclaimed_size:_d}')} B reclaimed by reencoding")
        log.info(f"  - {c.num(deleted)} ({c.num(f'{deleted_size:_d}')} B) "
                 f"{'deleted' if self.real_run else 'to delete'} "
                 f"({(c.ok if delete_failed == 0 else c.err)(delete_failed)} failed)")

        if not self.real_run:
            log.info(f"This was a {c.warn('dry run')}, no files were actually copied or deleted")

        log.info(f"Finished in {datetime.datetime.now(datetime.UTC) - start}")

    def delete(self, path):
        """ Conditionally delete the specified file """
        return self.processor.delete(path)

    def process(self, source, target):
        """ Conditionally process the specified file: convert the video and copy all other files """
        log.debug(f"{'Processing' if self.config.copy_files else 'Would process'} file {c.path(str(source))}")

        if source.suffix == '.avi' and self.config.video.convert:
            return self.processor.convert_avi(source, target,
                                              codec=self.config.video.codec,
                                              pixel_format='gray')
        else:
            return self.processor.copy(source, target)
