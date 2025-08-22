import os
import gzip
import shutil
from logging.handlers import RotatingFileHandler
from typing import Optional


class SmartRotatingFileHandler(RotatingFileHandler):
    """
    Enhanced rotating file handler with compression and archiving
    """

    def __init__(
            self,
            filename: str,
            max_bytes: int = 10 * 1024 * 1024,  # 10MB
            backup_count: int = 10,
            compress: bool = False,  # Disabled by default for Windows
            archive_dir: Optional[str] = None
    ):
        # Ensure directory exists
        dir_path = os.path.dirname(filename)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        # Initialize parent class with mode 'a' for append
        super().__init__(
            filename,
            mode='a',
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
            delay=False
        )

        self.compress = compress
        self.archive_dir = archive_dir

        if archive_dir:
            os.makedirs(archive_dir, exist_ok=True)

    def doRollover(self):
        """Override to add compression and archiving"""

        # Call parent rollover
        super().doRollover()

        # Compress the oldest backup if enabled
        if self.compress and self.backupCount > 0:
            oldest_backup = f"{self.baseFilename}.{self.backupCount}"
            if os.path.exists(oldest_backup):
                self._compress_file(oldest_backup)

        # Archive old compressed files
        if self.archive_dir:
            self._archive_old_logs()

    def _compress_file(self, filepath: str):
        """Compress a log file using gzip"""
        compressed_path = f"{filepath}.gz"

        try:
            with open(filepath, 'rb') as f_in:
                with gzip.open(compressed_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            # Remove original file after successful compression
            os.remove(filepath)

        except Exception as e:
            # Log error but don't fail
            print(f"Failed to compress log file {filepath}: {e}")

    def _archive_old_logs(self):
        """Move old compressed logs to archive directory"""
        import glob
        from datetime import datetime, timedelta

        # Archive logs older than 30 days
        cutoff_date = datetime.now() - timedelta(days=30)

        for compressed_file in glob.glob(f"{self.baseFilename}.*.gz"):
            try:
                file_mtime = datetime.fromtimestamp(os.path.getmtime(compressed_file))
                if file_mtime < cutoff_date:
                    archive_path = os.path.join(
                        self.archive_dir,
                        os.path.basename(compressed_file)
                    )
                    shutil.move(compressed_file, archive_path)
            except Exception as e:
                print(f"Failed to archive {compressed_file}: {e}")