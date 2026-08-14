# 1Password reference template. Contains NO secrets — only vault pointers —
# so it is safe to commit. Generate a real .env from it with:
#
#   op inject -i .env.tpl -o .env
#
# Re-run that after a key rotates. .env itself stays gitignored.
#
# (Note: never write a literal reference URI in a comment here; op inject
# parses them anywhere in the file, comments included, and fails on prose.)
#
# All three credentials live on one item: the_tie_listings_ops in the
# dotenv_files vault, which is the listings-ops env bundle.

# Airtable Personal Access Token — required for the live Refresh feature.
AIRTABLE_TOKEN=op://dotenv_files/the_tie_listings_ops/AIRTABLE_API_KEY

# CoinGecko API key — optional; raises the rate limit. The plan below is set
# from an authenticated probe of the key, not assumed: see README.
COINGECKO_API_KEY=op://dotenv_files/the_tie_listings_ops/COINGECKO_API_KEY
COINGECKO_API_PLAN=demo

# CoinMarketCap API key — optional; enables the fallback lookup. The item
# carries two candidates, COINMARKETCAP_API_KEY (32 chars) and
# COINMARKETCAP_PRO_API_KEY (36-char UUID). The UUID one is the format CMC
# actually issues and is the one that authenticates; see README.
COINMARKETCAP_API_KEY=op://dotenv_files/the_tie_listings_ops/COINMARKETCAP_PRO_API_KEY

# --- background sweep (in-process, runs only while npm start is up) -------
# Minutes between sweeps. 0 disables the scheduler; Refresh still works.
SWEEP_INTERVAL_MINUTES=60
# Re-check companies whose most recent round is within this many months.
SWEEP_MAX_AGE_MONTHS=12
# Run one sweep immediately at startup instead of waiting a full interval.
SWEEP_ON_START=false
