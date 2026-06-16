import cv2
import numpy as np
from PIL import Image
import imagehash
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ImageAnalyzer:
    """
    Local, deterministic Computer Vision module for JewelScope Research.
    Analyzes jewelry images to extract style and quality cues without external APIs.
    """

    def __init__(self):
        pass

    def _load_image(self, image_path):
        """
        Internal helper to load image safely.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")
        
        try:
            # Using PIL as a check for corrupted images
            with Image.open(image_path) as img:
                img.verify()
            
            # Re-open for actual processing with OpenCV
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"OpenCV failed to load image at {image_path}")
            return image
        except Exception as e:
            raise ValueError(f"Corrupted or invalid image: {e}")

    def extract_dominant_colors(self, image_path, k=5):
        """
        Uses OpenCV K-Means clustering to find the most prevalent colors.
        Returns them as a list of hex strings.
        """
        try:
            image = self._load_image(image_path)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            
            # Resize to speed up processing
            height, width = image.shape[:2]
            max_dim = 200
            if max(height, width) > max_dim:
                scale = max_dim / max(height, width)
                image = cv2.resize(image, (int(width * scale), int(height * scale)))

            pixels = image.reshape((-1, 3)).astype(np.float32)

            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)

            centers = np.uint8(centers)
            
            # Convert to hex
            hex_colors = []
            for color in centers:
                hex_colors.append('#{:02x}{:02x}{:02x}'.format(color[0], color[1], color[2]))
            
            return hex_colors
        except Exception as e:
            logger.error(f"Error extracting colors from {image_path}: {e}")
            return []

    def analyze_luster(self, image_path):
        """
        Implements a 'Sparkle Score' (0.0 to 1.0).
        Combines sharpness (Laplacian Variance) and specular highlights.
        """
        try:
            image = self._load_image(image_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # 1. Sharpness (Laplacian Variance)
            # Higher variance means sharper edges, often associated with high quality
            laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            
            # Normalize sharpness (heuristic: 1000+ is very sharp)
            sharpness_score = min(laplacian_var / 1000.0, 1.0)

            # 2. Specular Highlights (Sparkle)
            # Detect glints using a high-threshold mask
            _, glints = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY)
            
            # Calculate glint ratio (percentage of pixels that are glints)
            total_pixels = glints.shape[0] * glints.shape[1]
            glint_pixels = cv2.countNonZero(glints)
            
            # Heuristic: 0.5% to 5% of pixels being highlights is good for jewelry
            # We normalize this to a 0.0 - 1.0 score
            glint_ratio = (glint_pixels / total_pixels) * 100 # percentage
            glint_score = min(glint_ratio / 2.0, 1.0) # Assume 2% coverage is max sparkle

            # Combined Sparkle Score
            # Weighting: 40% sharpness, 60% glint detection
            sparkle_score = (sharpness_score * 0.4) + (glint_score * 0.6)
            
            return round(min(sparkle_score, 1.0), 3)
        except Exception as e:
            logger.error(f"Error analyzing luster for {image_path}: {e}")
            return 0.0

    def get_image_hash(self, image_path):
        """
        Generates a perceptual dHash of the image for deduplication.
        Returns the hash as a string.
        """
        try:
            if not os.path.exists(image_path):
                return None
            
            with Image.open(image_path) as img:
                hash_val = imagehash.dhash(img)
                return str(hash_val)
        except Exception as e:
            logger.error(f"Error generating hash for {image_path}: {e}")
            return None

    def classify_jewelry_type(self, image_path):
        """
        Simple rule-based classification based on aspect ratio and contour analysis.
        Distinguishes 'Ring', 'Necklace/Bracelet', 'Earrings'.
        """
        try:
            image = self._load_image(image_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            height, width = gray.shape[:2]
            aspect_ratio = width / float(height)

            # Basic thresholding to find the object
            _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return "Unknown"

            # Find the largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            
            # Rule 1: Rings are usually somewhat square-ish in bounding box
            if 0.8 <= aspect_ratio <= 1.2:
                return "Ring"
            
            # Rule 2: Necklaces are often very wide or very tall (U-shape)
            if aspect_ratio > 1.5 or aspect_ratio < 0.6:
                return "Necklace"
            
            # Rule 3: Earrings often come in pairs (multiple similar sized contours)
            if len([c for c in contours if cv2.contourArea(c) > area * 0.3]) >= 2:
                return "Earrings"

            return "General Jewelry"
        except Exception as e:
            logger.error(f"Error classifying jewelry for {image_path}: {e}")
            return "Unknown"

if __name__ == "__main__":
    # Quick manual test block
    import sys
    if len(sys.argv) > 1:
        path = sys.argv[1]
        analyzer = ImageAnalyzer()
        logger.info(f"Analyzing: {path}")
        print(f"Dominant Colors: {analyzer.extract_dominant_colors(path)}")
        print(f"Sparkle Score: {analyzer.analyze_luster(path)}")
        print(f"Classification: {analyzer.classify_jewelry_type(path)}")
    else:
        logger.info("Usage: python utils/vision_engine.py <image_path>")

