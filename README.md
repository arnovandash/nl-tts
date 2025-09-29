# Sentence Repetition Audio Generator

A language learning text-to-speech audio snippet generator for learning through sentence repetition, similar to the Glossika method.

This script automates the creation of language lessons from a user-provided CSV or TSV file. It uses the Google Gemini API to generate text-to-speech audio, designed for practicing grammar and speaking. The script groups sentences, adds pauses for repetition, and handles different recording types.

## How It Works

*   **Reads from CSV or TSV:** All lesson content is read from the input file provided on the command line. The script automatically detects if the file is comma-separated or tab-separated based on the file extension (`.csv` or `.tsv`).
*   **Groups into OGGs:** Rows are grouped by the `File_Group` column. Each unique group is compiled into a single OGG audio file in the `output_audio` folder.
*   **Multi-Language Audio:** The script can generate audio for different languages within the same file, for instance, generating English audio for `EN_Sentence` and Dutch for `NL_Sentence`.
*   **In-Memory Caching:** To improve performance and reduce redundant API calls, the script maintains an in-memory cache of generated audio. If the same text is requested multiple times in a single run, the audio is reused from the cache.
*   **Robust API Calls:** The script includes a rate limiter to avoid exceeding the API's free tier limit (10 calls/minute). It also features a retry mechanism with exponential backoff, automatically retrying a failed API call up to 3 times before skipping.
*   **Skips Existing Files:** The script checks if an audio file for a group already exists and will not re-generate it, saving time and API usage.
*   **Test Mode:** A `--test` flag processes only the first sentence of the first new group for a quick sample.

## Setup

1.  **Install Prerequisites:** You need [Python 3.7+](https://www.python.org/) and [FFmpeg](https://ffmpeg.org/download.html) (required for audio processing).

2.  **Set API Key:** Your Google Gemini API key must be set as an environment variable.
    *   **macOS / Linux:** `export GEMINI_API_KEY="YOUR_API_KEY"`
    *   **Windows:** `set GEMINI_API_KEY="YOUR_API_KEY"`

3.  **Install Dependencies:**
    ```bash
    pip install google-genai pandas pydub audioop-lts
    ```

4.  **Create Project Files:** In your project directory, create:
    *   The python script (e.g., `dutch_audio_generator.py`).
    *   Your input file (e.g., `my_dutch_notes.csv`).
    *   An empty folder named `output_audio`.

## Usage

### Generate All New Files
Provide the path to your input file (CSV or TSV) as an argument.

```bash
# Using a CSV file
python dutch_audio_generator.py path/to/your/notes.csv

# Using a TSV file
python dutch_audio_generator.py path/to/your/notes.tsv
```

### Generate a Test File
Use the `--test` flag along with the input file path to quickly generate a sample audio file. The output file will have a `_TEST.ogg` suffix.

```bash
python dutch_audio_generator.py path/to/your/notes.csv --test
```

## Input File Structure

The input file is designed to be flexible. You can mix `Paragraph` and `Repeat` rows within the same `File_Group`. A common workflow is to have a `Paragraph` row containing a full block of text, followed by several `Repeat` rows for practicing the individual sentences. You can have multiple such paragraph/sentence blocks within a single audio file group.

The script requires the following column headers in the input file.

| NL_Sentence | EN_Sentence | Type | File_Group | Repetitions | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *De kat zit...* |  | Paragraph | DeKatEnDeHond | | Present tense |
| De kat zit op de mat. | The cat sits on the mat. | Repeat | DeKatEnDeHond | 3 | Present tense |
| De hond slaapt. | The dog sleeps. | Repeat | DeKatEnDeHond | | Present tense |

*   `NL_Sentence`: **(Required)** The primary language text to be spoken.
*   `EN_Sentence`: (Optional) A translation or secondary language text. If present, its audio will be generated and played once before the `NL_Sentence` repetitions.
*   `Type`: **(Required)** Can be `Paragraph` or `Repeat`. This changes the speaking style of the generated audio.
    *   `Paragraph`: Uses a prompt for a natural, engaging storytelling voice. Ideal for listening to a full text.
    *   `Repeat`: Uses a prompt for a slower, clearer voice specifically for language learners. This is better for focusing on and repeating individual sentences.
*   `File_Group`: **(Required)** Groups rows into a single OGG file.
*   `Repetitions`: (Optional) Number of times to repeat the `NL_Sentence` audio. Defaults to 2.
*   `Notes`: (Optional) For personal notes; ignored by the script.

## Script Configuration

Key variables can be adjusted at the top of the Python script.

```python
# --- CONFIGURATION ---
OUTPUT_FOLDER = "output_audio"
VOICE_NAME = "Zephyr"
PAUSE_MULTIPLIER_REPEAT = 1.5
PAUSE_MULTIPLIER_NEXT = 2.5
API_CALLS_PER_MINUTE = 10
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
# --- END CONFIGURATION ---
```
