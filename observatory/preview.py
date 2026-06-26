import numpy as np
from PIL import Image
from io import BytesIO
import base64

# single preview image stored as downscaled and fullsize jpg
class CapturePreview():
    def __init__(self, name, img, timestamp):
        self.name = name
        self.timestamp = timestamp
        self.jpg = self._create_jpg(img)
        self.preview_jpg = self._create_jpg(img, max_width=640, jpeg_quality=70)

    def _create_jpg(self, img, max_width=None, jpeg_quality=100):
        # Work on a float copy; do not mutate original image
        img = np.asarray(img, dtype=np.float32)

        # Normalize to 8-bit grayscale
        img_min = np.nanmin(img)
        img_max = np.nanmax(img)

        img -= img_min
        scale = img_max - img_min

        if scale > 0:
            img = img / scale * 255
        else:
            img = np.zeros_like(img)

        img = np.clip(img, 0, 255).astype(np.uint8)

        img_pil = Image.fromarray(img, mode="L")

        if max_width is not None and img_pil.width > max_width:
            ratio = max_width / img_pil.width
            new_size = (max_width, int(img_pil.height * ratio))
            img_pil = img_pil.resize(new_size, resample=Image.BILINEAR)

        buffer = BytesIO()
        img_pil.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
        buffer.seek(0)

        return buffer

# buffer for last n pictures pushed to it, behaves like a deque
class CaptureBuffer():
    def __init__(self, maxlen=10):
        self.maxlen = maxlen
        # List of CapturePreview objects
        self.buffer = []

    def push(self, item: CapturePreview):
        if len(self.buffer) >= self.maxlen:
            self.buffer.pop(0)
        self.buffer.append(item)
    
    def get_last_n(self, n):
        return self.buffer[-n:]

    import base64

    def get_previews(self, n):
        previews = []

        for item in self.get_last_n(n):
            jpg_bytes = item.preview_jpg.getvalue()  # BytesIO -> bytes

            previews.append({
                "name": item.name,
                "timestamp": item.timestamp.isoformat() if hasattr(item.timestamp, "isoformat") else item.timestamp,
                "preview_jpg": base64.b64encode(jpg_bytes).decode("ascii"),
                "mime_type": "image/jpeg",
            })

        return previews
    
    def get_full_image(self, name):
        for item in self.buffer:
            if item.name == name:
                return item.jpg
        return None