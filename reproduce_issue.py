import os
import io
from google import genai
from google.genai import types
import PIL.Image

# Dummy key to trigger local client logic
os.environ['GEMINI_API_KEY'] = 'dummy'

def test_mirrored_structure():
    client = genai.Client(api_key='dummy')
    
    prompt = "Test prompt"
    
    # Create a dummy image
    img = PIL.Image.new('RGB', (10, 10), color='red')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_data = img_byte_arr.getvalue()
    
    # 1. Content Parts as List[types.Part] (what we fixed)
    content_parts = [types.Part.from_text(text=prompt)]
    content_parts.append(types.Part.from_bytes(data=img_data, mime_type='image/png'))
    
    # 2. Safety Settings as List[types.SafetySetting]
    safety_settings = [
        types.SafetySetting(
            category='HARM_CATEGORY_HARASSMENT',
            threshold='BLOCK_NONE'
        ),
        types.SafetySetting(
            category='HARM_CATEGORY_HATE_SPEECH',
            threshold='BLOCK_NONE'
        ),
        types.SafetySetting(
            category='HARM_CATEGORY_SEXUALLY_EXPLICIT',
            threshold='BLOCK_NONE'
        ),
        types.SafetySetting(
            category='HARM_CATEGORY_DANGEROUS_CONTENT',
            threshold='BLOCK_NONE'
        ),
    ]
    
    # 3. Generation Config
    generation_config = types.GenerateContentConfig(
        temperature=0.4,
        max_output_tokens=8192,
        safety_settings=safety_settings
    )
    
    print("Attempting generate_content with mirrored structure...")
    try:
        # This mirrors line 12268 in app.py
        client.models.generate_content(
            model='gemini-2.0-flash',
            contents=content_parts,
            config=generation_config
        )
        print("Call triggered (likely 401)")
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_mirrored_structure()
