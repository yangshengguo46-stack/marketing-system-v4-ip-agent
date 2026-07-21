# Douyin official metric collection

The IP Agent distribution contains a first-party adapter for Douyin's official
`POST https://open.douyin.com/api/apps/v1/video/query/` endpoint. It queries
current statistics for public videos owned by the authorized user and writes
the result as a post-level `snapshot` linked to the existing publish receipt.

This is not scraping. The official capability requires an enterprise developer
application, the `ma.video.bind` scope, approval for video-data query access and
user authorization. Only videos belonging to the access token's user can be
queried. Private or unreturned videos are stored as `unavailable`, never as
zero performance. Follow the current official documentation:

- <https://developer.open-douyin.com/docs/resource/zh-CN/mini-app/develop/server/basic-abilities/video-id-convert/user-video-data/video-data>
- <https://developer.open-douyin.com/capacity-center-page/capacity-detail/7448483112163590181>

## Normalization

| Douyin field | Personal-IP metric |
|---|---|
| `play_count` | `views` |
| `digg_count` | `likes` |
| `comment_count` | `comments` |
| `share_count` | `shares` |
| `download_count` | `downloads` |
| `forward_count` | `forwards` |

Views, likes, comments and shares determine whether the result is complete.
Optional download/forward counters are retained when returned. Provider log id,
scope, review/video status and missing fields stay in coverage metadata. The
collector classifies expired credentials, missing permission, quota, transient
and network failures without logging or returning the access token.

## Credentialed smoke test

For developer verification only:

```bash
export DOUYIN_ACCESS_TOKEN='...'
export DOUYIN_OPEN_ID='...'
export DOUYIN_ITEM_ID='...'
make douyin-metrics-smoke
```

The command never prints those credentials. It is not the production
credential path. Product OAuth callback, encrypted per-account token storage,
refresh and revocation UI remain pending; until they land, the Gateway does not
offer a public endpoint that accepts raw Douyin tokens.

The official capability is for data belonging to the authorizing user and must
not be repackaged as an external data service or unrestricted platform-wide
analytics product.
