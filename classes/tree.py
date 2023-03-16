import argparse
import yaml
import dotmap
import datetime
from pathlib import Path

from utils import colour as c, log
from utils.functions import format_boolean
from argparsedirs import ReadableDir, WriteableDir
from classes.processor import FileProcessor

logger = log.setup('root')


class DirectoryConvertor:
    def __init__(self):
        self.config: dotmap.DotMap | None = None
        self.parser = None
        self.args = None
        self.source_dir: Path | None = None
        self.target_dir: Path | None = None
        self.real_run: bool = False

        self.create_argparser()
        self.load_config()

        logger.info("AMOS sighting synchronization and conversion utility")
        logger.info(f"Source directory {c.path(str(self.source_dir))}, "
                    f"target directory {c.path(str(self.target_dir))}")

        if self.config.video.convert:
            logger.info(f"Videos will be converted to {c.param(self.config.video.codec)}, "
                        f"pixel format {c.param(self.config.video.pixel_format)}")
        else:
            logger.info(f"Videos {c.warn('will not')} be converted, only copied")

        logger.info(f"This is a {c.ok('real run') if self.real_run else c.warn('dry run')}: "
                    f"copy files: {format_boolean(self.config.copy_files)}, "
                    f"delete old files: {format_boolean(self.config.delete_files)}")

        if self.args.debug:
            logger.info("Config is")
            self.config.pprint()

        self.processor = FileProcessor(self.real_run, ffmpeg_path=self.config.ffmpeg, debug=self.args.debug)

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

    @staticmethod
    def _warn_override(config_param, args_param):
        logger.warning(f"Overriding source {c.param(config_param)} from command line to {c.param(args_param)}")

    def load_config(self):
        self.config = dotmap.DotMap(yaml.safe_load(self.args.ini), _dynamic=False)
        self.config.video.convert = False

        if self.args.source is not None:
            self._warn_override(self.config.source, self.args.source)
            self.config.source = self.args.source
        if self.args.target is not None:
            self._warn_override(self.config.target, self.args.target)
            self.config.target = self.args.target
        if self.args.older_than is not None:
            self._warn_override(self.config.older_than, self.args.older_than)
            self.config.older_than = self.args.older_than
        if self.args.convert_video:
            self._warn_override(self.config.video.convert, self.args.video.convert)
            self.config.video.convert = True

        self.config.copy_files = True if self.args.copy else False
        self.config.delete_files = True if self.args.delete else False

        self.source_dir = Path(self.config.source)
        self.target_dir = Path(self.config.target)
        self.real_run = not (self.config.copy_files or self.config.delete_files)

    def run(self):
        start = datetime.datetime.utcnow()
        files = self.source_dir.rglob('*.*')
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
            target_dir = Path(str(file.parent).replace(str(self.source_dir), str(self.target_dir)))
            target_path = Path(target_dir / file.name)
            try:
                source_age = datetime.datetime.utcnow() - datetime.datetime.fromtimestamp(file.stat().st_mtime)

                inspected += 1
                inspected_size += source_path.stat().st_size

                is_updated = False
                if is_copied := target_path.exists():
                    target_age = datetime.datetime.utcnow() - \
                                 datetime.datetime.fromtimestamp(target_path.stat().st_mtime)
                    if source_age < target_age:
                        is_updated = True

                is_old = (source_age.days >= self.config.older_than)

                should_process = not is_copied or is_updated and self.config.copy_files
                should_delete = is_old and is_copied and self.config.delete_files

                logger.info(f"{c.path(file):<85} age {c.num(source_age.days):>13} d, "
                            f"old: {format_boolean(is_old)} "
                            f"copied: {format_boolean(is_copied)} "
                            f"newer: {format_boolean(is_updated)} "
                            f"process: {format_boolean(should_process)}, "
                            f"delete: {format_boolean(should_delete)}")

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
                        logger.error(f"Processing failed: {e}")
                        process_failed += 1

                if should_delete:
                    try:
                        deleted_size += self.delete(source_path)
                        deleted += 1
                    except FileNotFoundError as e:
                        delete_failed += 1
                        raise e
                    except OSError as e:
                        logger.error(f"Deletion failed: {e}")
                        delete_failed += 1
            except FileNotFoundError as e:
                logger.error(f"File not found, skipping: {e}")

        logger.info(f"{c.num(inspected)} files ({c.num(f'{inspected_size / 2**20:6.0f}')} MB) inspected")
        logger.info(f"  - {c.num(processed)} ({c.num(f'{processed_size / 2**20:6.0f}')} MB) "
                    f"{'copied' if self.config.copy_files else 'to copy'} "
                    f"({(c.ok if process_failed == 0 else c.err)(process_failed)} failed)")
        logger.info(f"     - {c.num(f'{reclaimed_size / 2 ** 20:6.0f}')} MB reclaimed by reencoding")
        logger.info(f"  - {c.num(deleted)} ({c.num(f'{deleted_size / 2**20:6.0f}')} MB) "
                    f"{'to delete' if self.real_run else 'deleted'} "
                    f"({(c.ok if delete_failed == 0 else c.err)(delete_failed)} failed)")

        if not self.real_run:
            logger.info(f"This was a {c.warn('dry run')}, no files were actually copied or deleted")

        logger.info(f"Finished in {datetime.datetime.utcnow() - start}")

    def delete(self, path):
        """ Conditionally delete the specified file """
        self.processor.delete(path)

    def process(self, source, target):
        """ Conditionally process the specified file: convert the video and copy all other files """
        logger.debug(f"{'Processing' if self.config.copy_files else 'Would process'} file {c.path(str(source))}")

        if source.suffix == '.avi' and self.config.video.convert:
            return self.processor.convert_avi(source, target,
                                              codec=self.config.video.codec,
                                              pixel_format='gray')
        else:
            return self.processor.copy(source, target)
