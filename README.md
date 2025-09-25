# Sentence Repetition Audio Generator

A language learning text-to-speech audio snippet generator for learning through sentence repetition, similar to the Glossika method.

This script automates the creation of Dutch audio lessons from a CSV file. It uses the Google Gemini API to generate text-to-speech audio, designed for practicing grammar and speaking. The script groups sentences, adds pauses for repetition, and handles different recording types like paragraphs and single sentences. I created it specifically for my Dutch language studies but it can easily be adapted for any language.

## How It Works

*   **Reads from CSV:** All lesson content is read from `dutch_notes.csv`, which defines the sentences, types, and grouping.
*   **Groups into MP3s:** Rows are grouped by the `File_Group` column. Each unique group is compiled into a single MP3 file in the `output_audio` folder.
*   **Skips Existing Files:** The script checks if an audio file for a group already exists and will not re-generate it, saving API usage.
*   **Handles Two Recording Types:**
    *   **`Paragraph`:** Reads a block of text with a natural, narrative voice.
    *   **`Repeat`:** Reads a single sentence slowly and clearly, automatically adding pauses after each repetition for the user to speak.
*   **Configurable Repetition:** The CSV allows specifying how many times a Dutch sentence should be repeated (defaults to 2). An optional `EN_Sentence` will be read once at the beginning.
*   **Test Mode:** A `--test` flag processes only the first sentence of the first new group for a quick sample.
*   **User Confirmation:** Before generating files, the script lists what will be created and prompts for confirmation.

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
    *   A CSV file named `dutch_notes.csv`.
    *   An empty folder named `output_audio`.

## Usage

### Generate All New Files
This command processes `dutch_notes.csv` and generates all missing audio files.
```bash
python dutch_audio_generator.py
```

### Generate a Test File
Use the `--test` flag to quickly generate a sample audio file from the first new sentence. The output file will have a `_TEST.mp3` suffix.
```bash
python dutch_audio_generator.py --test
```

## CSV Structure

The CSV is designed to be flexible. A common workflow is to have a `Paragraph` row containing a full block of text, followed by several `Repeat` rows, each containing a sentence from that paragraph. This allows you to first hear the full text, and then practice the individual sentences in any order you like.

The script requires the following column headers in `dutch_notes.csv`.

| NL_Sentence | EN_Sentence | Type | File_Group | Repetitions | Tense |
| :--- | :--- | :--- | :--- | :--- | :--- |
| *De kat zit...* |  | Paragraph | DeKatEnDeHond | | Present |
| De kat zit op de mat. | The cat sits on the mat. | Repeat | DeKatEnDeHond | 3 | Present |
| De hond slaapt. | The dog sleeps. | Repeat | DeKatEnDeHond | | Present |

**Note on Comments:** You can add comments to your CSV file by starting a line with `#` or `//`. These lines will be ignored by the script.

*   `NL_Sentence`: **(Required)** The Dutch text.
*   `EN_Sentence`: (Optional) English translation, read once at the start of a `Repeat` block. This is ignored for `Paragraph` type rows.
*   `Type`: **(Required)** `Paragraph` or `Repeat`.
*   `File_Group`: **(Required)** Groups rows into a single MP3 file.
*   `Repetitions`: (Optional) Number of times to repeat the Dutch audio. Defaults to 2.
*   `Tense`: (Optional) For personal notes; ignored by the script.

**Pro Tip:** For easy editing and management, you can maintain your notes in a Google Sheet and export it to CSV format.

## Script Configuration

Key variables like file paths and pause durations can be adjusted at the top of the Python script.

```python
# --- CONFIGURATION ---
CSV_FILE_PATH = "dutch_notes.csv"
OUTPUT_FOLDER = "output_audio"
VOICE_NAME = "Zephyr"
PAUSE_MULTIPLIER_REPEAT = 1.5
PAUSE_MULTIPLIER_NEXT = 2.5
# --- END CONFIGURATION ---
```
