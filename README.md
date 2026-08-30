# Skip Timestamps DB

Verified against the current SkipDB dump schema.

## Setup
Add GitHub Actions repository secret `TMDB_TOKEN` with your TMDb API Read Access Token.
Then run **Actions → Update Timestamp DB → Run workflow**.

Outputs:
- `movie/{TMDB_ID}.json`
- `tv/{TMDB_ID}.json`

SkipDB segment types: `intro`, `recap`, `outro`, `preview`.
Times are stored in milliseconds.
