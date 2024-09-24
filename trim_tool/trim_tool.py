import cv2
import numpy as np
import os

def compute_optimal_crop(image, target_aspect_ratio, face_cascade):
    height, width = image.shape[:2]

    # Initialize the saliency detector
    saliency = cv2.saliency.StaticSaliencyFineGrained_create()

    # Compute the saliency map
    (success, saliency_map) = saliency.computeSaliency(image)
    if not success:
        print("Error: Could not compute saliency.")
        return None

    # Initial crop area based on saliency map
    # Convert the saliency map to 8-bit grayscale
    saliency_map_uint8 = (saliency_map * 255).astype("uint8")

    # Thresholding to obtain salient regions
    threshold_value = 50  # You can adjust this value
    _, thresh_map = cv2.threshold(saliency_map_uint8, threshold_value, 255, cv2.THRESH_BINARY)

    # Find contours of salient regions
    contours, _ = cv2.findContours(thresh_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        salient_contours = np.vstack(contours)
        x, y, w, h = cv2.boundingRect(salient_contours)
    else:
        # If no salient regions, start with the whole image
        x, y, w, h = 0, 0, width, height

    # Adjust the bounding rectangle to match the target aspect ratio
    crop_aspect_ratio = w / h

    if crop_aspect_ratio > target_aspect_ratio:
        # Need to reduce width
        new_w = int(h * target_aspect_ratio)
        x += (w - new_w) // 2
        w = new_w
    elif crop_aspect_ratio < target_aspect_ratio:
        # Need to reduce height
        new_h = int(w / target_aspect_ratio)
        y += (h - new_h) // 2
        h = new_h

    # Ensure coordinates are within image boundaries
    x = max(0, min(x, width - w))
    y = max(0, min(y, height - h))

    # Face detection
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray_image,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30),
        flags=cv2.CASCADE_SCALE_IMAGE
    )

    # Adjust crop to include faces
    for (fx, fy, fw, fh) in faces:
        face_center_x = fx + fw / 2
        face_center_y = fy + fh / 2

        # Check if face center is outside the crop area
        if not (x <= face_center_x <= x + w and y <= face_center_y <= y + h):
            # Calculate shift needed to include the face
            dx = face_center_x - (x + w / 2)
            dy = face_center_y - (y + h / 2)

            # Shift the crop area
            x_new = x + dx
            y_new = y + dy

            # Ensure new crop is within image boundaries
            x_new = max(0, min(int(x_new), width - w))
            y_new = max(0, min(int(y_new), height - h))

            x, y = x_new, y_new

    # Ensure coordinates are integers
    x = int(x)
    y = int(y)
    w = int(w)
    h = int(h)

    # Final crop area
    top_left = (x, y)
    bottom_right = (x + w, y + h)
    return top_left, bottom_right, None  # No saliency score needed

def crop_and_save_image(image, top_left, bottom_right, output_path, target_dimensions):
    x1, y1 = top_left
    x2, y2 = bottom_right
    cropped_image = image[y1:y2, x1:x2]

    # Resize the image to the target dimensions (maintains aspect ratio)
    resized_image = cv2.resize(cropped_image, target_dimensions, interpolation=cv2.INTER_AREA)

    cv2.imwrite(output_path, resized_image)

def main():
    # Set this variable to True if you want to process logo asset types
    logo_mode = False  # Set to True for logo assets, False for non-logo assets

    input_dir = 'input_images'

    if not os.path.isdir(input_dir):
        print(f"Error: The input directory '{input_dir}' does not exist or is not a directory.")
        return

    # Supported image extensions
    supported_extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif')

    # Get list of image files in the input directory
    input_image_files = [
        f for f in os.listdir(input_dir)
        if f.lower().endswith(supported_extensions)
    ]

    if not input_image_files:
        print(f"No image files found in directory '{input_dir}'.")
        return

    if logo_mode:
        # Logo asset types
        asset_requirements = [
            {
                'asset_field_type': 'LOGO',
                'aspect_ratio': 1.0,
                'dimensions': (1200, 1200)
            },
            {
                'asset_field_type': 'LANDSCAPE_LOGO',
                'aspect_ratio': 4.0,  # 4/1 as a float
                'dimensions': (1200, 300)
            }
        ]
    else:
        # Non-logo asset types
        asset_requirements = [
            {
                'asset_field_type': 'MARKETING_IMAGE',
                'aspect_ratio': 1.91,  # Float value
                'dimensions': (1200, 628)
            },
            {
                'asset_field_type': 'SQUARE_MARKETING_IMAGE',
                'aspect_ratio': 1.0,
                'dimensions': (1200, 1200)
            },
            {
                'asset_field_type': 'PORTRAIT_MARKETING_IMAGE',
                'aspect_ratio': 0.8,  # 4/5 as a float
                'dimensions': (960, 1200)
            }
        ]

    # Load the face cascade classifier
    face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        print("Error: Could not load face cascade classifier. Ensure 'haarcascade_frontalface_default.xml' is in the script directory.")
        return

    # Create an output directory if it doesn't exist
    output_dir = 'output_images'
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for image_file in input_image_files:
        input_image_path = os.path.join(input_dir, image_file)
        image = cv2.imread(input_image_path)
        if image is None:
            print(f"Error: Could not load image '{input_image_path}'.")
            continue

        for asset in asset_requirements:
            asset_type = asset['asset_field_type']
            aspect_ratio = asset['aspect_ratio']
            dimensions = asset['dimensions']

            print(f"\nProcessing asset type: {asset_type} for image {input_image_path}")

            result = compute_optimal_crop(image, aspect_ratio, face_cascade)
            if result is None:
                print(f"Skipping {asset_type} for image {input_image_path} due to insufficient image size or no salient regions.")
                continue

            top_left, bottom_right, _ = result

            # Prepare output filename
            aspect_ratio_str = str(aspect_ratio).replace('.', '_')
            input_image_name = os.path.splitext(os.path.basename(input_image_path))[0]
            output_filename = f"{asset_type}_{input_image_name}_{dimensions[0]}x{dimensions[1]}_{aspect_ratio_str}.jpg"
            output_path = os.path.join(output_dir, output_filename)

            # Crop and save the image
            crop_and_save_image(image, top_left, bottom_right, output_path, dimensions)
            print(f"Saved {asset_type} to {output_path}")

    print("\nProcessing completed.")

if __name__ == "__main__":
    main()
