# dutch_audio_generator.py

import os
import sys
import argparse
import time
import pandas as pd
from pydub import AudioSegment
from google import genai
from google.genai import types
import io

# --- CONFIGURATION ---
CSV_FILE_PATH = "dutch_notes.csv"
OUTPUT_FOLDER = "output_audio"
VOICE_NAME = "Zephyr"

# Pause multipliers
# Pause after each repetition for you to speak
PAUSE_MULTIPLIER_REPEAT = 1.0
# Longer pause after all repetitions of a sentence are done
PAUSE_MULTIPLIER_NEXT = 1.5
# --- END CONFIGURATION ---

def generate_tts_audio(client: genai.Client, text: str, is_paragraph: bool, language: str = 'nl') -> tuple[bytes | None, str | None]:
    """Generates audio using the Gemini API and returns the raw audio data and mime type."""
    print(f"  - Generating audio for: '{text[:50]}...'")
    if language == 'nl':
        if is_paragraph:
            prompt = f"Read this Dutch passage in a clear, calm, and engaging storytelling voice: {text}"
        else:
            prompt = f"Read this Dutch passage in a clear, calm, and engaging voice like a teacher: {text}"
    else: # language == 'en'
        prompt = f"Read this English sentence in a clear, calm, and engaging voice: {text}"

    try:
        #model = "gemini-2.5-pro-preview-tts"
        model = "gemini-2.5-flash-preview-tts"
        contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]
        generate_content_config = types.GenerateContentConfig(
            response_modalities=["audio"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                )
            )
        )

        full_response_data = b""
        mime_type = None

        for chunk in client.models.generate_content_stream(
            model=model, contents=contents, config=generate_content_config
        ):
            if not chunk.candidates:
                continue
            part = chunk.candidates[0].content.parts[0]
            if part.inline_data:
                if not mime_type:
                    mime_type = part.inline_data.mime_type
                full_response_data += part.inline_data.data

        if not full_response_data:
            print("  - WARNING: API returned no audio data.")
            return None, None

        return full_response_data, mime_type

    except Exception as e:
        print(f"  - ERROR: An error occurred during API call: {e}")
        if "API_KEY_INVALID" in str(e):
            print("\nERROR: Your Gemini API key is not valid. Please check your GEMINI_API_KEY environment variable.")
            sys.exit(1)
        return None, None

def create_audio_segment(audio_data: bytes, mime_type: str) -> AudioSegment:
    """Creates a pydub AudioSegment from raw audio data."""
    
    rate = 24000 # Default
    for param in mime_type.split(';'):
        if 'rate=' in param:
            rate = int(param.split('=')[-1])

    return AudioSegment(
        data=audio_data,
        sample_width=2,  # 16 bits = 2 bytes
        frame_rate=rate,
        channels=1
    )

def process_group(group_name: str, group_df: pd.DataFrame, client: genai.Client, output_path: str):
    """Processes a group of rows from the CSV and generates a single audio file."""
    print(f"\nProcessing group: {group_name}...")
    final_audio = AudioSegment.empty()
    is_paragraph_processed = False
    audio_cache = {}

    def get_or_generate_audio(text: str, is_paragraph: bool, language: str = 'nl') -> AudioSegment | None:
        """Gets audio from cache or generates it if not present."""
        cache_key = (text, language)
        if cache_key in audio_cache:
            print(f"  - Using cached audio for: '{text[:50]}...' ({language})")
            return audio_cache[cache_key]
        
        audio_data, mime_type = generate_tts_audio(client, text, is_paragraph, language)
        if audio_data and mime_type:
            segment = create_audio_segment(audio_data, mime_type)
            audio_cache[cache_key] = segment
            return segment
        return None

    for _, row in group_df.iterrows():
        audio_type = row.get('Type', 'Repeat').strip()

        # Handle Paragraph type (only once per group)
        if audio_type == 'Paragraph' and not is_paragraph_processed:
            paragraph_text = row.get('NL_Sentence')
            if pd.notna(paragraph_text):
                paragraph_segment = get_or_generate_audio(paragraph_text, is_paragraph=True, language='nl')
                if paragraph_segment:
                    final_audio += paragraph_segment
                    final_audio += AudioSegment.silent(duration=2000)
                is_paragraph_processed = True

        # Handle Repeat type
        elif audio_type == 'Repeat':
            nl_text = row.get('NL_Sentence')
            en_text = row.get('EN_Sentence')
            try:
                repetitions = int(row.get('Repetitions', 2))
            except (ValueError, TypeError):
                repetitions = 2

            if not pd.notna(nl_text):
                continue # Skip if no Dutch sentence

            sentence_block = AudioSegment.empty()

            # 1. Add English sentence audio if it exists
            if pd.notna(en_text):
                en_segment = get_or_generate_audio(en_text, is_paragraph=False, language='en')
                if en_segment:
                    sentence_block += en_segment
                    sentence_block += AudioSegment.silent(duration=700) # Short pause after English

            # 2. Generate and loop Dutch sentence audio
            nl_segment = get_or_generate_audio(nl_text, is_paragraph=False, language='nl')
            if not nl_segment:
                print(f"  - SKIPPING sentence '{nl_text[:30]}...' due to audio generation failure.")
                continue

            nl_duration_ms = len(nl_segment)
            repetition_pause = AudioSegment.silent(duration=int(nl_duration_ms * PAUSE_MULTIPLIER_REPEAT))
            
            for i in range(repetitions):
                sentence_block += nl_segment
                if i < repetitions - 1: # Add pause after each repetition except the last one
                    sentence_block += repetition_pause
            
            # 3. Add longer pause for the next sentence
            next_sentence_pause = AudioSegment.silent(duration=int(nl_duration_ms * PAUSE_MULTIPLIER_NEXT))
            sentence_block += next_sentence_pause
            
            final_audio += sentence_block
    
    # Export the final combined audio file for the group
    if len(final_audio) > 0:
        print(f"  -> Exporting audio file: {output_path}")
        final_audio.export(output_path, format="ogg", parameters=["-q:a", "7"])
    else:
        print(f"  -> No audio was generated for group '{group_name}'. Skipping export.")

def main():
    """Main function to run the audio generation script."""
    parser = argparse.ArgumentParser(description="Generate Dutch audio lessons from a CSV file.")
    parser.add_argument("--test", action="store_true", help="Run in test mode: generates only the first sentence of the first new group.")
    args = parser.parse_args()

    # Check for API Key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: The GEMINI_API_KEY environment variable is not set or is empty.")
        sys.exit(1)

    # Check for CSV and output folder
    if not os.path.exists(CSV_FILE_PATH):
        print(f"ERROR: Cannot find the input file: {CSV_FILE_PATH}")
        sys.exit(1)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Load and prepare data
    try:
        with open(CSV_FILE_PATH, 'r') as f:
            lines = f.readlines()
        
        filtered_lines = []
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line.startswith('#') and not stripped_line.startswith('//'):
                filtered_lines.append(line)

        csv_data = "".join(filtered_lines)
        df = pd.read_csv(io.StringIO(csv_data), skipinitialspace=True)

        df.columns = [c.strip() for c in df.columns] # Clean column names
        df['File_Group'] = df['File_Group'].astype(str).str.strip()
    except Exception as e:
        print(f"ERROR: Could not read or process CSV file. Make sure it has the correct columns. Details: {e}")
        sys.exit(1)

    grouped = df.groupby('File_Group')
    groups_to_process = []
    
    print("Checking for existing files...")
    for name, group in grouped:
        sanitized_name = "".join(x for x in name if x.isalnum() or x in "._-")
        output_path = os.path.join(OUTPUT_FOLDER, f"{sanitized_name}.ogg")
        if not os.path.exists(output_path):
            groups_to_process.append((name, group, output_path))
        else:
            print(f"  - Skipping '{name}' (file already exists).")

    if not groups_to_process:
        print("\nAll audio files are already up to date. Nothing to do.")
        sys.exit(0)

    # User Confirmation
    print("\nThe following new file groups will be generated:")
    for name, _, _ in groups_to_process:
        print(f"  - {name}")

    if args.test:
        print("\n--- RUNNING IN TEST MODE ---")
        # In test mode, select only the first row of the first group
        name, group, output_path = groups_to_process[0]
        first_row_group = group.head(1).copy()
        first_row_group.name = name # Preserve the group name
        groups_to_process = [(name, first_row_group, output_path.replace(".ogg", "_TEST.ogg"))]
    else:
        confirm = input("\nProceed with generating these files? (y/n): ")
        if confirm.lower() != 'y':
            print("Operation cancelled by user.")
            sys.exit(0)
    
    # Initialize API client
    client = genai.Client(api_key=api_key)

    # Process each group
    start_time = time.time()
    for name, group, output_path in groups_to_process:
        process_group(name, group, client, output_path)
    
    end_time = time.time()
    print(f"\nDone! Process completed in {end_time - start_time:.2f} seconds.\n")


if __name__ == "__main__":
    main()
