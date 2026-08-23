# Apex Events Inbox

A drop box between the Apex Circle events scout and the app.

The scout runs as a Claude Code routine in Anthropic's cloud. That environment's
network policy blocks outbound connections to `app.apexcircle.club`, so the
scout cannot submit events directly. It can reach GitHub, so it writes here
instead, and the app's Cloudflare Worker reads this repo on its normal 30 minute
cron and publishes what passes its checks.

Nothing sensitive belongs in this repo. It holds event names, dates, addresses
and source links, all of which end up public on the app anyway. It is public on
purpose: a public raw URL means the Worker needs no credential to read it, which
is one fewer token to create, store and rotate.

## Files

    latest.json              what the relay reads, overwritten every run
    drops/events-<date>.json one file per run, kept as the scout's own memory

`latest.json` carries an `id`. The Worker records which ids it has published, so
re-reading the same file does nothing. To resubmit, change the id.

## Shape

```json
{
  "id": "2026-08-23-run1",
  "dryRun": true,
  "events": [
    {
      "name": "Cars and Coffee Somewhere",
      "organizer": "Somewhere Car Club",
      "venue": "The Lot",
      "address": "123 Main St, Somewhere, WA 98001",
      "city": "Somewhere", "state": "WA", "zip": "98001",
      "tz": "America/Los_Angeles",
      "date": "2026-09-12", "start": "08:00", "end": "11:00",
      "recurrence": "weekly",
      "type": "meet",
      "vehicle_category": "all_vehicles",
      "is_paid": false, "price_label": "Free",
      "ticket_url": null, "poster_url": null,
      "description": "One or two plain sentences.",
      "sources": ["https://organizer-page", "https://second-source"]
    }
  ]
}
```

With `"dryRun": true` the Worker runs every check and writes nothing, so a run
can be inspected before it reaches members. Remove it to publish for real.

## What the Worker checks

The scout is treated as untrusted. Everything here is re-checked before anything
is published:

- start time inside 12 hours to 120 days out
- epochs recomputed from the local time plus the IANA zone, so DST is right
- the address geocoded, and an event that will not geocode is refused
- deduped against what is already on the app, including recurring series
- **every source link opened, and the page has to actually mention the event,
  venue or organizer**

That last one is the reason this arrangement is safe. The scout cannot open web
pages at all, so it can find candidates but cannot confirm them, and every
other check above passes happily on a well formed event that was never real: a
plausible address geocodes, and an invented URL is still a valid URL. The
Worker has no such restriction, so it does the one check the scout cannot.

An unreachable link counts as unproven, not as permission. Plenty of real
venues answer a datacentre IP with a 403, so those events are held rather than
published on the benefit of the doubt.

Anything that fails is held with a reason rather than dropped silently.

`SCOUT_PROMPT.md` holds the prompt the routine runs.
