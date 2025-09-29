# dutch_audio_generator.py

import os
import sys
import argparse
import time
import pandas as pd
from pydub import AudioSegment
from google import genai
from google.genai import types

# --- CONFIGURATION ---
OUTPUT_FOLDER = "output_audio"
VOICE_NAME = "Zephyr"
PAUSE_MULTIPLIER_REPEAT = 1.5
PAUSE_MULTIPLIER_NEXT = 2.5
API_CALLS_PER_MINUTE = 10
MAX_RETRIES = 10
RETRY_DELAY_SECONDS = 20
# --- END CONFIGURATION ---

api_call_timestamps = []

def generate_tts_audio(client: genai.Client, text: str, is_paragraph: bool, language: str) -> tuple[bytes | None, str | None]:
    """Generates audio using the Gemini API and returns the raw audio data and mime type."""
    global api_call_timestamps
    current_time = time.time()

    # Rate limiting
    api_call_timestamps = [t for t in api_call_timestamps if current_time - t < 60]
    if len(api_call_timestamps) >= API_CALLS_PER_MINUTE:
        oldest_call_time = api_call_timestamps[0]
        time_to_wait = (oldest_call_time + 60) - current_time
        if time_to_wait > 0:
            print(f"  - Proactively pausing for {time_to_wait:.1f} seconds to avoid hitting the rate limit...", flush=True)
            time.sleep(time_to_wait)
    api_call_timestamps.append(time.time())

    # Prepare the prompt
    if is_paragraph:
        prompt = f"Read this {language.capitalize()} passage in a clear, calm, and engaging storytelling voice: {text}"
    else:
        prompt = f"Speak this {language.capitalize()} sentence in clear, calm and engaging teacher's voice: {text}"

    print(f"  - Generating audio for: '{text[:50]}...'")

    # Retry loop
    for attempt in range(MAX_RETRIES):
        try:
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
                candidate = chunk.candidates[0]
                if not candidate.content or not candidate.content.parts:
                    if candidate.prompt_feedback and candidate.prompt_feedback.block_reason:
                        print(f"  - ERROR: Audio generation blocked. Reason: {candidate.prompt_feedback.block_reason.name}")
                        print("  - Stopping execution.")
                        sys.exit(1)
                    else:
                        continue
                part = candidate.content.parts[0]
                if part.inline_data:
                    if not mime_type:
                        mime_type = part.inline_data.mime_type
                    full_response_data += part.inline_data.data

            if not full_response_data:
                raise ValueError("API returned no audio data.")

            return full_response_data, mime_type

        except Exception as e:
            # Handle fatal quota errors immediately
            if "RESOURCE_EXHAUSTED" in str(e):
                print("\n  - FATAL ERROR: API quota limit reached (RESOURCE_EXHAUSTED).", flush=True)
                print("  - The API is reporting that a usage limit has been exceeded (e.g., requests per day).", flush=True)
                print("  - Please check your Google AI Platform dashboard for quota details.", flush=True)
                print("  - Stopping execution.", flush=True)
                sys.exit(1)

            print(f"  - WARNING: API call failed on attempt {attempt + 1} of {MAX_RETRIES}. Error: {e}", flush=True)
            if "API_KEY_INVALID" in str(e):
                print("\nERROR: Your Gemini API key is not valid. Please check your GEMINI_API_KEY environment variable.", flush=True)
                sys.exit(1)
            
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_SECONDS * (attempt + 1)
                print(f"  - Waiting for {delay} seconds before retrying...", flush=True)
                time.sleep(delay)
            else:
                print(f"  - ERROR: All {MAX_RETRIES} retry attempts failed.", flush=True)

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

        # Handle Paragraph type
        if audio_type == 'Paragraph':
            paragraph_text = row.get('NL_Sentence')
            if pd.notna(paragraph_text):
                paragraph_segment = get_or_generate_audio(paragraph_text, is_paragraph=True, language='nl')
                if paragraph_segment:
                    final_audio += paragraph_segment
                    final_audio += AudioSegment.silent(duration=2000)

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
    parser = argparse.ArgumentParser(description="Generate Dutch audio lessons from a CSV or TSV file.")
    parser.add_argument("input_file", help="Path to the input CSV or TSV file.")
    parser.add_argument("--test", action="store_true", help="Run in test mode: generates only the first sentence of the first new group.")
    args = parser.parse_args()

    # Check for API Key
    if "GEMINI_API_KEY" not in os.environ:
        print("ERROR: Please set the GEMINI_API_KEY environment variable.")
        sys.exit(1)

    # Determine separator from file extension
    if args.input_file.lower().endswith('.tsv'):
        separator = '\t'
    else:
        separator = ','

    # Check for input file and output folder
    if not os.path.exists(args.input_file):
        print(f"ERROR: Cannot find the input file: {args.input_file}")
        sys.exit(1)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Load and prepare data
    try:
        df = pd.read_csv(args.input_file, sep=separator, comment='#')
        df.columns = [c.strip() for c in df.columns] # Clean column names
        
        # Drop rows where File_Group is NaN to prevent processing invalid lines
        df.dropna(subset=['File_Group'], inplace=True)

        df['File_Group'] = df['File_Group'].astype(str).str.strip()
    except Exception as e:
        print(f"ERROR: Could not read or process CSV file. Make sure it has the correct columns. Details: {e}")
        sys.exit(1)

    grouped = df.groupby('File_Group')
    groups_to_process = []
    
    print("Checking for existing files...")
    for name, group in grouped:
        # Safeguard against processing the header row as data
        if name == 'File_Group':
            continue

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
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

    # Process each group
    start_time = time.time()
    for name, group, output_path in groups_to_process:
        process_group(name, group, client, output_path)
    
    end_time = time.time()
    print(f"\nDone! Process completed in {end_time - start_time:.2f} seconds.\n")


if __name__ == "__main__":
    main()
