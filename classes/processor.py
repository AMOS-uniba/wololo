import shutil
import subprocess

from pathlib import Path

from utils import colour as c, logger

log = logger.setup(__name__)


class FileProcessor:
    def __init__(self, real_run: bool, *, ffmpeg_path: Path, debug: bool):
        self.real_run = real_run
        self.ffmpeg = ffmpeg_path
        self.debug = debug

    def correct_video_header(self, path):
        """ Inspect the video header for the faulty "Y16 " and if found, change it to "Y800" """

        with open(path, 'r+b') as file:
            file.seek(188)
            pixel_format = file.read(4)

            if pixel_format == b'Y16 ':
                if self.real_run:
                    log.warning(f"File {c.path(str(path))}: video header is {c.param('Y16 ')}, "
                                   f"correcting to {c.param('Y800')}")
                    file.seek(188)
                    file.write(b'Y800')
                else:
                    log.warning(f"File {c.path(str(path))}: video header is {c.param('Y16 ')}, not correcting")

    def delete(self, path: Path) -> int:
        """ Conditionally delete the specified file """
        log.info(f"{'Deleting' if self.real_run else 'Would delete'} file {c.path(str(path))}")
        if self.real_run:
            try:
                size = path.stat().st_size
                path.unlink()
                return size
            except OSError as e:
                log.error(f"Could not delete {str(path)}: {e.strerror}")
                raise e
        else:
            return 0

    def copy(self, source: Path, target: Path) -> 0:
        """ Conditionally copy the specified file <source> to <target> """
        log.info(f"{'Copying' if self.real_run else 'Would copy'} {c.path(source)} to {c.path(target)}")

        if self.real_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target)

        return 0

    def convert_avi(self, source, target, *,
                    codec: str = 'rawvideo',
                    pixel_format: str = 'gray') -> int:
        """ Conditionally convert the specified AVI file to the new format using ffmpeg """
        if not source.exists():
            return 0

        self.correct_video_header(source)
        target.parent.mkdir(parents=True, exist_ok=True)

        loglevel = 32 if self.debug else 24
        command = [
            self.ffmpeg,
            "-hide_banner",  # do not show config every time
            "-y",  # automatically answer "yes" to all questions
            "-i", str(source),  # input file
            "-loglevel", str(loglevel),  # do not show ffmpeg logs
            "-c:v", codec,  # output codec
        ]
        # For x264 we also need to set the quantization parameter to 0 for lossless
        if codec == 'libx264':
            command += ['-qp', '0']

        command += [
            "-pix_fmt", pixel_format,  # pixel format
            str(target),  # output file
        ]

        log.info(f"{'Converting' if self.real_run else 'Would convert'} {c.path(str(source))} to {c.path(target)}")

        if self.real_run:
            cp = subprocess.run(command)
            if cp.returncode != 0:
                raise OSError()

            return source.stat().st_size - target.stat().st_size
        else:
            log.info(f"Would run {' '.join(command)}")
            return 0
