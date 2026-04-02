# State schema

Top-level JSON object:

- `subscriptions`: array
- `seen_items`: object keyed by RSS guid
- `downloaded_items`: object keyed by RSS guid
- `processed_files`: object keyed by original incoming file path
- `metadata_cache`: object keyed by normalized title
- `history`: array

## Subscription

- `bangumi_id`
- `title`
- `page_url`
- `rss_url`
- `subgroup_id`
- `aliases`
- `season_num`
- `created_at`
- `active`

## Seen item

- `guid`
- `title`
- `bangumi_id`
- `published_at`
- `torrent_url`
- `episode`
- `first_seen_at`
- `last_checked_at`
- `queued`
- `queue_result`

## Downloaded item

- `guid`
- `title`
- `bangumi_id`
- `marked_at`
- `note`
- `target`

## Processed file

- `source`
- `target`
- `name`
- `show_title`
- `season`
- `episode`
- `bangumi_id`
- `processed_at`
- `related_guids`
- `dry_run`

## Metadata cache

Simple cached scraper result used to write NFO:

- `title`
- `title_english`
- `title_japanese`
- `year`
- `synopsis`
- `genres`
- `aired_from`
- `url`
