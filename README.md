# Skip-DB

Builds one daily-updated `Skip-DB.json` containing Movie and TV skip timestamps indexed by TMDb ID.

## Setup

Add a GitHub Actions repository secret named:

`TMDB_TOKEN`

Use your TMDb API Read Access Token as its value.

Then run:

**Actions → Update Skip-DB → Run workflow**

The scheduled workflow also runs daily.

## Output

Only one public database file is generated:

`Skip-DB.json`

Top-level structure:

- `meta`
- `movies`
- `tv`

Timestamps are milliseconds.
