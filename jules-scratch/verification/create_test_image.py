from PIL import Image

# Create a simple red 200x200 image
img = Image.new('RGB', (200, 200), color = 'red')
img.save('jules-scratch/verification/test_logo.png')
print("Test image 'test_logo.png' created.")