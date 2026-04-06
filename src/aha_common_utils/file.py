import base64
import hashlib
import io
import mimetypes
import re
import shlex
import subprocess
from pathlib import Path
from typing import List, Literal, Union

import filetype
import numpy as np
from PIL import Image

try:
    import imagehash
except ImportError:  # pragma: no cover - optional dependency
    imagehash = None

try:
    import magic
except ImportError:  # pragma: no cover - optional dependency
    magic = None

FileType = Literal[
    "pdf",
    "audio",
    "image",
    "video",
    "word",
    "excel",
    "ppt",
    "subtitle",
    "markdown",
    "text",
    "unknown",
]

_FILE_TYPE_BY_EXTENSION: dict[str, FileType] = {
    ".pdf": "pdf",
    ".mp3": "audio",
    ".wav": "audio",
    ".m4a": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".aac": "audio",
    ".webm": "audio",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".bmp": "image",
    ".webp": "image",
    ".tif": "image",
    ".tiff": "image",
    ".mp4": "video",
    ".mov": "video",
    ".mkv": "video",
    ".avi": "video",
    ".wmv": "video",
    ".doc": "word",
    ".docx": "word",
    ".xls": "excel",
    ".xlsx": "excel",
    ".ppt": "ppt",
    ".pptx": "ppt",
    ".srt": "subtitle",
    ".vtt": "subtitle",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
}

_FILE_TYPE_BY_MIME: dict[str, FileType] = {
    "application/pdf": "pdf",
    "application/msword": "word",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "word",
    "application/vnd.ms-excel": "excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "ppt",
    "text/markdown": "markdown",
    "text/plain": "text",
    "text/srt": "subtitle",
    "application/x-subrip": "subtitle",
    "text/vtt": "subtitle",
}


class FileHelper:
    """
    A class containing utility methods for file operations.
    """

    @staticmethod
    def get_file_extension(file_path: str) -> str:
        """
        Get the file extension from a file path.

        :param file_path: The path of the file.
        :return: The file extension.
        """
        return file_path.split(".")[-1] if "." in file_path else ""

    @staticmethod
    def get_file_name(file_path: str) -> str:
        """
        Get the file name without extension from a file path.

        :param file_path: The path of the file.
        :return: The file name without extension.
        """
        return file_path.split("/")[-1].split(".")[0] if "/" in file_path else ""

    @staticmethod
    def get_file_name_with_suffix(file_path: str) -> str:
        """
        Get the file name with suffix from a file path.

        :param file_path: The path of the file.
        :return: The file name with suffix.
        """
        return file_path.split("/")[-1] if "/" in file_path else ""

    @staticmethod
    def get_file_name_without_suffix(file_path: str) -> str:
        """
        Get the file name without suffix from a file path.

        :param file_path: The path of the file.
        :return: The file name without suffix.
        """
        return file_path.split("/")[-1].split(".")[0] if "/" in file_path else ""

    @staticmethod
    def get_file_name_without_suffix_and_dir(file_path: str) -> str:
        """
        Get the file name without suffix and directory from a file path.

        :param file_path: The path of the file.
        :return: The file name without suffix and directory.
        """
        return file_path.split("/")[-1].split(".")[0] if "/" in file_path else ""

    @staticmethod
    def get_mime_type(file_path: str) -> str:
        """
        Get the MIME type from a file path.

        :param file_path: The path of the file.
        :return: The MIME type.
        """
        mime_type = filetype.guess(file_path)
        if mime_type:
            return mime_type.mime
        guessed_mime_type, _ = mimetypes.guess_type(file_path)
        if guessed_mime_type:
            return guessed_mime_type
        if magic is not None:
            with open(file_path, "rb") as file:
                file_content = file.read(2048)
                return magic.from_buffer(file_content, mime=True) or "application/octet-stream"
        return "application/octet-stream"

    @staticmethod
    def get_file_type(file_path: str, mime_type: str | None = None) -> FileType:
        """Return a normalized high-level file type.

        Args:
            file_path: File path or filename.
            mime_type: Optional MIME type supplied by caller. When present, it has
                higher priority than probing the file from disk.

        Returns:
            Normalized file type category.
        """
        normalized_mime_type = FileHelper._normalize_mime_type(mime_type or "")
        suffix = Path(file_path).suffix.lower()
        if not normalized_mime_type and Path(file_path).exists():
            normalized_mime_type = FileHelper._normalize_mime_type(FileHelper.get_mime_type(file_path))

        if normalized_mime_type == "application/pdf":
            return "pdf"
        if normalized_mime_type.startswith("audio/"):
            return "audio"
        if normalized_mime_type.startswith("image/"):
            return "image"
        if normalized_mime_type.startswith("video/"):
            return "video"
        if normalized_mime_type in {"text/plain", "application/octet-stream"}:
            extension_type = _FILE_TYPE_BY_EXTENSION.get(suffix)
            if extension_type and extension_type != "text":
                return extension_type
        if normalized_mime_type in _FILE_TYPE_BY_MIME:
            return _FILE_TYPE_BY_MIME[normalized_mime_type]

        return _FILE_TYPE_BY_EXTENSION.get(suffix, "unknown")

    @staticmethod
    def is_pdf(file_path: str) -> bool:
        """
        Check if the file is a PDF.

        :param file_path: The path of the file.
        :return: True if the file is a PDF, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "pdf"

    @staticmethod
    def is_office(file_path: str) -> bool:
        return FileHelper.is_word(file_path) or FileHelper.is_excel(file_path) or FileHelper.is_ppt(file_path)

    @staticmethod
    def is_audio(file_path: str) -> bool:
        """
        Check if the file is an audio.

        :param file_path: The path of the file.
        :return: True if the file is an audio, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "audio"

    @staticmethod
    def is_image(file_path: str) -> bool:
        """
        Check if the file is an image.

        :param file_path: The path of the file.
        :return: True if the file is an image, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "image"

    @staticmethod
    def is_word(file_path: str) -> bool:
        """
        Check if the file is a Word document.

        :param file_path: The path of the file.
        :return: True if the file is a Word document, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "word"

    @staticmethod
    def is_excel(file_path: str) -> bool:
        """
        Check if the file is an Excel document.

        :param file_path: The path of the file.
        :return: True if the file is an Excel document, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "excel"

    @staticmethod
    def is_ppt(file_path: str) -> bool:
        """
        Check if the file is a PowerPoint document.

        :param file_path: The path of the file.
        :return: True if the file is a PowerPoint document, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "ppt"

    @staticmethod
    def get_width_height(file_path: str) -> tuple:
        """
        Get the width and height of an image file.

        :param file_path: The path of the image file.
        :return: A tuple containing the width and height of the image.
        """
        if FileHelper.is_image(file_path):
            with Image.open(file_path) as img:
                return img.size
        elif FileHelper.is_pdf(file_path):
            from PyPDF2 import PdfReader

            reader = PdfReader(file_path)
            page = reader.pages[0]
            return page.mediabox.width, page.mediabox.height
        else:
            raise ValueError("Unsupported file type for width and height extraction.")

    @staticmethod
    def get_image(src: Union[str, Image.Image, np.ndarray]) -> Image.Image:
        """
        Convert the input to a format suitable for OCR processing.

        This method can be overridden by subclasses to customize the image conversion process.

        Args:
            src: The input image, which can be a file path, PIL Image, OpenCV image, or base64 encoded string.
                 Base64 strings can be in format: 'data:image/png;base64,<data>' or raw base64 string.

        Returns:
            Image.Image: The converted PIL Image suitable for processing.
        """
        if isinstance(src, str):
            # Check if it's a base64 encoded image
            if src.startswith("data:image"):
                # Extract base64 data from data URL
                base64_data = re.sub(r"^data:image/\w+;base64,", "", src)
                image_data = base64.b64decode(base64_data)
                return Image.open(io.BytesIO(image_data))
            elif FileHelper._is_base64(src):
                # Try to decode as raw base64 string
                try:
                    image_data = base64.b64decode(src)
                    return Image.open(io.BytesIO(image_data))
                except Exception:
                    # If decoding fails, treat as file path
                    pass
            # Treat as file path
            return Image.open(src)
        elif isinstance(src, Image.Image):
            return src
        elif isinstance(src, np.ndarray):
            return Image.fromarray(src)
        raise ValueError(f"Unsupport src type of {type(src)}")

    @staticmethod
    def get_image_np(src: Union[str, Image.Image, np.ndarray]) -> np.ndarray:
        """
        Convert the input to a NumPy array suitable for OCR processing.
        This method can be overridden by subclasses to customize the image conversion process.
        Args:
            src: The input image, which can be a file path, PIL Image, OpenCV image, or base64 encoded string.
                 Base64 strings can be in format: 'data:image/png;base64,<data>' or raw base64 string.
        Returns:
            np.ndarray: The converted image suitable for OCR processing.
        """
        if isinstance(src, str):
            # Check if it's a base64 encoded image
            if src.startswith("data:image"):
                # Extract base64 data from data URL
                base64_data = re.sub(r"^data:image/\w+;base64,", "", src)
                image_data = base64.b64decode(base64_data)
                return np.array(Image.open(io.BytesIO(image_data)))
            elif FileHelper._is_base64(src):
                # Try to decode as raw base64 string
                try:
                    image_data = base64.b64decode(src)
                    return np.array(Image.open(io.BytesIO(image_data)))
                except Exception:
                    # If decoding fails, treat as file path
                    pass
            # Treat as file path
            return np.array(Image.open(src))
        elif isinstance(src, Image.Image):
            return np.array(src)
        elif isinstance(src, np.ndarray):
            return src
        raise ValueError(f"Unsupported src type of {type(src)}")

    @staticmethod
    def is_video(file_path: str) -> bool:
        """
        Check if the file is a video.

        :param file_path: The path of the file.
        :return: True if the file is a video, False otherwise.
        """
        return FileHelper.get_file_type(file_path) == "video"

    @staticmethod
    def get_file_sha256(file_path: str, chunk_size: int = 1024 * 1024) -> str:
        """Calculate SHA-256 for exact file deduplication.

        Args:
            file_path: Target file path.
            chunk_size: Read chunk size in bytes.

        Returns:
            Hex digest of the file content.
        """
        digest = hashlib.sha256()
        with open(file_path, "rb") as file:
            while chunk := file.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def get_audio_dedup_keys(file_path: str) -> dict[str, str]:
        """Build the recommended exact and content-level dedup keys for audio.

        Args:
            file_path: Audio file path.

        Returns:
            A dict containing exact byte hash and content fingerprint.
        """
        return {
            "file_sha256": FileHelper.get_file_sha256(file_path),
            "audio_fingerprint": FileHelper.get_audio_fingerprint(file_path),
        }

    @staticmethod
    def get_audio_fingerprint(
        file_path: str,
        *,
        sample_rate: int = 8000,
        window_seconds: float = 1.0,
        max_windows: int = 12,
        fingerprint_bits: int = 128,
    ) -> str:
        """Generate a content fingerprint for audio deduplication.

        The algorithm decodes audio into normalized mono PCM, samples windows across
        the full track, extracts frequency-band energy features, and compresses them
        into a stable bit fingerprint. It is more robust than raw file hashes when
        container, bitrate, or encoding changes.

        Args:
            file_path: Audio file path.
            sample_rate: Target PCM sample rate.
            window_seconds: Analysis window size.
            max_windows: Maximum sampled windows across the audio.
            fingerprint_bits: Size of the output fingerprint. Must be divisible by 4.

        Returns:
            Hexadecimal audio content fingerprint.
        """
        if fingerprint_bits <= 0 or fingerprint_bits % 4 != 0:
            raise ValueError("fingerprint_bits must be a positive multiple of 4")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_windows <= 0:
            raise ValueError("max_windows must be positive")
        if not FileHelper.is_audio(file_path):
            raise ValueError(f"File {file_path} is not an audio file.")

        samples = FileHelper._decode_audio_samples(file_path, sample_rate=sample_rate)
        window_size = max(int(sample_rate * window_seconds), 512)
        offsets = FileHelper._get_window_offsets(len(samples), window_size=window_size, max_windows=max_windows)
        if not offsets:
            offsets = [0]

        window_fn = np.hanning(window_size).astype(np.float32)
        band_features: list[np.ndarray] = []
        for offset in offsets:
            window = samples[offset : offset + window_size]
            if len(window) < window_size:
                window = np.pad(window, (0, window_size - len(window)))
            spectrum = np.abs(np.fft.rfft(window * window_fn))[1:]
            if spectrum.size == 0:
                continue
            bands = np.array_split(spectrum, fingerprint_bits)
            feature = np.array(
                [float(np.log1p(np.mean(np.square(band)))) if band.size else 0.0 for band in bands],
                dtype=np.float32,
            )
            band_features.append(feature)

        if not band_features:
            raise ValueError(f"Could not extract spectral features from audio file: {file_path}")

        aggregated = np.median(np.vstack(band_features), axis=0)
        threshold = float(np.median(aggregated))
        fingerprint = 0
        for index, is_high_energy in enumerate(aggregated > threshold):
            if bool(is_high_energy):
                fingerprint |= 1 << index

        return format(fingerprint, f"0{fingerprint_bits // 4}x")

    @staticmethod
    def compute_audio_hash_distance(hash1: str, hash2: str) -> int:
        """Calculate Hamming distance between two audio fingerprints."""
        return FileHelper._compute_hamming_distance(hash1, hash2)

    @staticmethod
    def is_same_audio(hash1: str, hash2: str, threshold: int = 40) -> bool:
        """Determine whether two audio fingerprints represent the same content."""
        distance = FileHelper.compute_audio_hash_distance(hash1, hash2)
        return distance <= threshold

    @staticmethod
    def get_phash(
        src: Union[str, Image.Image, np.ndarray],
        hash_size: int = 8,
        highfreq_factor: int = 4,
    ) -> str:
        """
        Calculate the perceptual hash (pHash) for an image.

        :param src: The input image (file path, PIL Image, or numpy array).
        :param hash_size: The size of the hash (default 8, resulting in 64-bit hash).
        :param highfreq_factor: The high frequency factor for DCT (default 4).
        :return: The perceptual hash as a hexadecimal string.
        """
        FileHelper._require_imagehash()
        image = FileHelper.get_image(src)
        phash = imagehash.phash(image, hash_size=hash_size, highfreq_factor=highfreq_factor)
        return str(phash)

    @staticmethod
    def get_video_phash(
        file_path: str,
        num_frames: int = 8,
        hash_size: int = 8,
        highfreq_factor: int = 4,
    ) -> List[str]:
        """
        Calculate perceptual hashes (pHash) for a video by extracting key frames.

        :param file_path: The path of the video file.
        :param num_frames: The number of frames to extract for hashing (default 8).
        :param hash_size: The size of the hash (default 8, resulting in 64-bit hash).
        :param highfreq_factor: The high frequency factor for DCT (default 4).
        :return: A list of perceptual hashes as hexadecimal strings.
        """
        import cv2

        if not FileHelper.is_video(file_path):
            raise ValueError(f"File {file_path} is not a video file.")

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {file_path}")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames <= 0:
                raise ValueError(f"Cannot determine frame count for video: {file_path}")

            # Calculate frame indices to sample evenly across the video
            frame_indices = [int(i * total_frames / num_frames) for i in range(num_frames)]

            phashes = []
            for frame_idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if ret:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(frame_rgb)
                    FileHelper._require_imagehash()
                    phash = imagehash.phash(image, hash_size=hash_size, highfreq_factor=highfreq_factor)
                    phashes.append(str(phash))

            return phashes
        finally:
            cap.release()

    @staticmethod
    def get_media_phash(
        file_path: str,
        num_frames: int = 8,
        hash_size: int = 8,
        highfreq_factor: int = 4,
    ) -> Union[str, List[str]]:
        """
        Calculate perceptual hash(es) for an image or video file.

        For images, returns a single hash string.
        For videos, returns a list of hash strings from sampled frames.

        :param file_path: The path of the media file (image or video).
        :param num_frames: The number of frames to extract for video hashing (default 8).
        :param hash_size: The size of the hash (default 8, resulting in 64-bit hash).
        :param highfreq_factor: The high frequency factor for DCT (default 4).
        :return: A single hash string for images, or a list of hash strings for videos.
        """
        if FileHelper.is_image(file_path):
            return FileHelper.get_phash(file_path, hash_size=hash_size, highfreq_factor=highfreq_factor)
        elif FileHelper.is_video(file_path):
            return FileHelper.get_video_phash(
                file_path,
                num_frames=num_frames,
                hash_size=hash_size,
                highfreq_factor=highfreq_factor,
            )
        else:
            raise ValueError(f"Unsupported file type for phash calculation: {file_path}")

    @staticmethod
    def get_video_combined_phash(
        file_path: str,
        frame_interval: int = 30,
        hash_size: int = 8,
        highfreq_factor: int = 4,
        simhash_bits: int = 128,
    ) -> str:
        """
        Calculate a combined perceptual hash for a video using Frame pHash + SimHash.

        This method provides a stable video fingerprint by:
        1. Extracting key frames at regular intervals (frame-level stability via pHash)
        2. Aggregating frame hashes using SimHash (temporal stability)

        The result is robust to:
        - Video re-encoding and compression
        - Resolution changes
        - Minor edits and cropping

        :param file_path: The path of the video file.
        :param frame_interval: Extract 1 frame every N frames (default 30, ~1 fps for 30fps video).
        :param hash_size: The size of the pHash (default 8, resulting in 64-bit hash).
        :param highfreq_factor: The high frequency factor for DCT (default 4).
        :param simhash_bits: The bit size for SimHash (default 128, recommended for stability).
        :return: A combined video fingerprint as a hexadecimal string.
        """
        import cv2

        if not FileHelper.is_video(file_path):
            raise ValueError(f"File {file_path} is not a video file.")

        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {file_path}")

        try:
            # Extract frame pHashes at regular intervals
            phash_values = []
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Sample frames at specified interval
                if frame_idx % frame_interval == 0:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(frame_rgb)
                    FileHelper._require_imagehash()
                    phash = imagehash.phash(image, hash_size=hash_size, highfreq_factor=highfreq_factor)
                    # Convert pHash to integer for SimHash aggregation
                    phash_values.append(int(str(phash), 16))

                frame_idx += 1

            if not phash_values:
                raise ValueError(f"Could not extract any frames from video: {file_path}")

            # Aggregate frame pHashes using SimHash
            video_simhash = FileHelper._simhash_aggregate(phash_values, simhash_bits)

            # Return as hexadecimal string
            hex_length = simhash_bits // 4
            return format(video_simhash, f"0{hex_length}x")
        finally:
            cap.release()

    @staticmethod
    def _is_base64(s: str) -> bool:
        """
        Check if a string is a valid base64 encoded string.

        :param s: The string to check.
        :return: True if the string appears to be base64 encoded.
        """
        # Base64 strings should be reasonably long and contain only valid base64 characters
        if len(s) < 50:  # Too short to be a meaningful image
            return False
        # Check if string contains only base64 characters
        base64_pattern = re.compile(r"^[A-Za-z0-9+/]+=*$")
        return bool(base64_pattern.match(s))

    @staticmethod
    def _simhash_aggregate(values: List[int], hashbits: int = 128) -> int:
        """
        Aggregate integer values using SimHash algorithm.

        This is the core SimHash aggregation: treats each value as a "token"
        and uses bit voting to produce a stable fingerprint.

        :param values: List of integer values to aggregate (e.g., frame pHashes).
        :param hashbits: The bit size of the output SimHash.
        :return: The aggregated SimHash value as an integer.
        """
        # Initialize bit voting vector
        v = [0] * hashbits

        # Vote on each bit position
        for value in values:
            for i in range(hashbits):
                bit = (value >> i) & 1
                v[i] += 1 if bit else -1

        # Generate final hash from majority votes
        fingerprint = 0
        for i in range(hashbits):
            if v[i] > 0:
                fingerprint |= 1 << i

        return fingerprint

    @staticmethod
    def compute_video_hash_distance(hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two video hashes.

        This measures how many bits differ between two video fingerprints.
        Recommended thresholds for 128-bit hashes:
        - ≤ 5: Almost certainly the same video
        - 6-10: Highly similar
        - > 10: Different videos

        :param hash1: First video hash (hexadecimal string).
        :param hash2: Second video hash (hexadecimal string).
        :return: Hamming distance (number of differing bits).
        """
        return FileHelper._compute_hamming_distance(hash1, hash2)

    @staticmethod
    def is_same_video(
        hash1: str,
        hash2: str,
        threshold: int = 5,
    ) -> bool:
        """
        Determine if two video hashes represent the same video.

        :param hash1: First video hash.
        :param hash2: Second video hash.
        :param threshold: Maximum Hamming distance to consider as same video (default 5 for 128-bit).
        :return: True if videos are considered the same.
        """
        distance = FileHelper.compute_video_hash_distance(hash1, hash2)
        return distance <= threshold

    @staticmethod
    def _normalize_mime_type(mime_type: str) -> str:
        return mime_type.strip().lower().split(";", 1)[0]

    @staticmethod
    def _run_subprocess(command: list[str], *, text: bool, timeout: int = 300) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=text,
                timeout=timeout,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or exc.stdout or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="ignore")
            rendered = " ".join(shlex.quote(part) for part in command)
            raise ValueError(f"Command failed: {rendered}\n{stderr.strip()}") from exc
        except subprocess.TimeoutExpired as exc:
            rendered = " ".join(shlex.quote(part) for part in command)
            raise ValueError(f"Command timed out: {rendered}") from exc

    @staticmethod
    def _decode_audio_samples(file_path: str, *, sample_rate: int) -> np.ndarray:
        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            file_path,
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-",
        ]
        result = FileHelper._run_subprocess(command, text=False)
        samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
        if samples.size == 0:
            raise ValueError(f"Decoded audio is empty: {file_path}")
        peak = float(np.max(np.abs(samples)))
        if peak > 0:
            samples /= peak
        return samples

    @staticmethod
    def _get_window_offsets(sample_count: int, *, window_size: int, max_windows: int) -> list[int]:
        if sample_count <= 0:
            return []
        if sample_count <= window_size:
            return [0]
        last_start = sample_count - window_size
        window_count = min(max_windows, max(1, sample_count // window_size))
        return [int(offset) for offset in np.linspace(0, last_start, num=window_count)]

    @staticmethod
    def _compute_hamming_distance(hash1: str, hash2: str) -> int:
        try:
            int1 = int(hash1, 16)
            int2 = int(hash2, 16)
        except ValueError as exc:
            raise ValueError("Invalid hexadecimal hash strings") from exc
        return bin(int1 ^ int2).count("1")

    @staticmethod
    def _require_imagehash() -> None:
        if imagehash is None:
            raise ImportError("imagehash is required for perceptual image/video hashing")

    # @staticmethod
    # def audio_chromaprint(audio_path: str) -> str:
    #     """
    #     计算音频文件的 Chromaprint 指纹。

    #     Args:
    #         audio_path: 音频文件路径

    #     Returns:
    #         Chromaprint 指纹字符串
    #     """
    #     duration, fingerprint = acoustid.fingerprint_file(audio_path)
    #     return hashlib.sha256(fingerprint.encode()).hexdigest()
